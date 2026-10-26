#!/usr/bin/env python3
"""
Synchronisiert die Fahrzeuge von mobile.de in die staticCars-Variable in index.html.

Quellen (--source):
  api    Offizielle mobile.de Search-API (services.mobile.de/search-api).
         Braucht MOBILE_API_USER, MOBILE_API_PASS, MOBILE_CUSTOMER_ID.
         Das ist die einzige Quelle, die automatisiert in GitHub Actions laeuft.

  html   Eine lokal gespeicherte Haendlerseite (home.mobile.de/TDAUTOMOBILE,
         im Browser mit Cmd+S gesichert). Fuer manuelle Updates ohne API-Zugang.
         Aufruf: --source html --file haendlerseite.html

  index  Baut data/cars.json aus dem aktuellen staticCars-Array in index.html
         neu auf. Noetig, wenn index.html von Hand bearbeitet wurde, damit die
         Plausibilitaetspruefung beim naechsten Sync nicht falsch anschlaegt.

Sicherheitsnetz: schlaegt der Abruf fehl oder liefert er auffaellig wenige
Fahrzeuge, bricht das Script ohne Aenderung an index.html ab (Exit 0) -
die alten Daten bleiben online stehen.

Direktes Scrapen von home.mobile.de ist bewusst NICHT implementiert: mobile.de
sitzt hinter Akamai Bot Manager und beantwortet Server-Requests mit HTTP 403
("Zugriff verweigert"). Diesen Schutz zu umgehen waere ein Verstoss gegen die
Nutzungsbedingungen und technisch nicht dauerhaft haltbar.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"
CARS_JSON = REPO_ROOT / "data" / "cars.json"
SITEMAP_XML = REPO_ROOT / "sitemap.xml"

API_BASE = "https://services.mobile.de/search-api/search"
API_ACCEPT = "application/vnd.de.mobile.api+json"
PAGE_SIZE = 100
IMAGE_RULE = "mo-1600"  # gleiche Bildgroesse wie bisher im Code

# Wenn ein Lauf weniger als dieser Anteil der zuletzt bekannten Fahrzeuge
# liefert, gehen wir von einem kaputten Abruf aus und fassen index.html nicht an.
MIN_RATIO_OF_PREVIOUS = 0.5


# ──────────────────────────────────────────────────────────────────────
#  Mappings mobile.de -> Deutsch (so wie es bisher im staticCars-Array steht)
# ──────────────────────────────────────────────────────────────────────

FUEL = {
    "PETROL": "Benzin",
    "DIESEL": "Diesel",
    "ELECTRICITY": "Elektro",
    "HYBRID": "Hybrid",
    "HYBRID_DIESEL": "Hybrid (Diesel)",
    "LPG": "Autogas (LPG)",
    "CNG": "Erdgas (CNG)",
    "ETHANOL": "Ethanol",
    "HYDROGENIUM": "Wasserstoff",
    "OTHER": "Sonstige",
}

GEARBOX = {
    "MANUAL_GEAR": "Schaltgetriebe",
    "AUTOMATIC_GEAR": "Automatik",
    "SEMIAUTOMATIC_GEAR": "Halbautomatik",
}

CATEGORY = {
    "EstateCar": "KOMBI",
    "Limousine": "LIMOUSINE",
    "Saloon": "LIMOUSINE",
    "SmallCar": "KLEINWAGEN",
    "OffRoad": "SUV",
    "SUV": "SUV",
    "Cabrio": "CABRIO",
    "SportsCar": "SPORTWAGEN",
    "Van": "VAN",
    "TransporterVan": "TRANSPORTER",
    "OtherCar": "SONSTIGE",
}

COLOR = {
    "BLACK": "Schwarz",
    "WHITE": "Weiß",
    "SILVER": "Silber",
    "GREY": "Grau",
    "GRAY": "Grau",
    "BLUE": "Blau",
    "RED": "Rot",
    "GREEN": "Grün",
    "YELLOW": "Gelb",
    "ORANGE": "Orange",
    "BROWN": "Braun",
    "BEIGE": "Beige",
    "GOLD": "Gold",
    "PURPLE": "Violett",
    "BRONZE": "Bronze",
}

INTERIOR_TYPE = {
    "CLOTH": "Stoff",
    "PART_LEATHER": "Teilleder",
    "FULL_LEATHER": "Leder",
    "LEATHER": "Leder",
    "VELOUR": "Velours",
    "ALCANTARA": "Alcantara",
    "OTHER_INTERIOR_TYPE": "Sonstige",
}

DOORS = {
    "TWO_OR_THREE": "3",
    "FOUR_OR_FIVE": "5",
    "SIX_OR_SEVEN": "7",
}

EMISSION = {
    "EURO1": "Euro1",
    "EURO2": "Euro2",
    "EURO3": "Euro3",
    "EURO4": "Euro4",
    "EURO5": "Euro5",
    "EURO6": "Euro6",
    "EURO6C": "Euro6c",
    "EURO6D_TEMP": "Euro6d-TEMP",
    "EURO6D": "Euro6d",
}


# mobile.de liefert Marken in Grossbuchstaben (MERCEDES-BENZ, ALFA_ROMEO).
# Reines .capitalize() wuerde aus BMW ein "Bmw" machen – daher Sonderfaelle.
MAKE_CASE = {
    "BMW": "BMW", "VW": "VW", "MINI": "MINI", "SEAT": "SEAT", "KIA": "Kia",
    "MG": "MG", "DS": "DS", "SsangYong": "SsangYong", "SSANGYONG": "SsangYong",
    "MERCEDES-BENZ": "Mercedes-Benz", "ALFA_ROMEO": "Alfa Romeo",
    "ALFA ROMEO": "Alfa Romeo", "LAND_ROVER": "Land Rover",
    "LAND ROVER": "Land Rover", "ASTON_MARTIN": "Aston Martin",
    "ROLLS_ROYCE": "Rolls-Royce", "MCLAREN": "McLaren", "SKODA": "Škoda",
    "CITROEN": "Citroën", "SMART": "smart", "GMC": "GMC", "RAM": "RAM",
    "BYD": "BYD",
}


def pretty_make(make: str) -> str:
    raw = make.strip()
    if raw.upper() in MAKE_CASE:
        return MAKE_CASE[raw.upper()]
    if not raw.isupper():
        return raw  # kommt schon lesbar an
    parts = re.split(r"([ _-])", raw.replace("_", " "))
    return "".join(p if p in " -" else p.capitalize() for p in parts)


def log(msg: str) -> None:
    print(f"[sync_cars] {msg}", flush=True)


# ──────────────────────────────────────────────────────────────────────
#  Quelle 0: Haendlerseite home.mobile.de (serverseitig gerendert)
# ──────────────────────────────────────────────────────────────────────

DEALER_URL = "https://home.mobile.de/TDAUTOMOBILE"
MAX_PAGES = 10

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

# Marken, die im Anzeigentitel vorkommen koennen – laengste zuerst, damit
# "Mercedes-Benz" nicht als "Mercedes" endet.
MAKES = [
    "Mercedes-Benz", "Mercedes", "Alfa Romeo", "Land Rover", "Aston Martin",
    "Rolls-Royce", "Volkswagen", "Mitsubishi", "Chevrolet", "SsangYong",
    "Maserati", "Lamborghini", "Porsche", "Peugeot", "Renault", "Hyundai",
    "Infiniti", "Chrysler", "Cadillac", "Daihatsu", "Suzuki", "Subaru",
    "Citroen", "Citroën", "Toyota", "Nissan", "Lancia", "Jaguar", "Bentley",
    "Ferrari", "McLaren", "Lexus", "Skoda", "Škoda", "Dacia", "Honda",
    "Smart", "Tesla", "Volvo", "Mazda", "Opel", "Ford", "Fiat", "Jeep",
    "Mini", "Seat", "Audi", "BMW", "Kia", "VW", "DS", "MG",
]

# Grobe Typ-Erkennung aus dem Titel – die Uebersichtsseite liefert keine
# Fahrzeugklasse. Gematcht wird auf Wortgrenzen, sonst macht "Advantage" aus
# einem 1er BMW einen Van. Reihenfolge = Prioritaet; kein Treffer = leer, und
# leer ist besser als falsch.
TYPE_HINTS = [
    ("CABRIO", ("cabrio", "cabriolet", "roadster", "convertible", "spyder",
                "mx-5", "z4", "slk", "slc", "boxster")),
    ("KOMBI", ("kombi", "touring", "avant", "variant", "sports tourer",
               "sportstourer", "shooting brake", "t-modell", "estate",
               "turnier", "sw", "st sw")),
    ("TRANSPORTER", ("transporter", "transit", "sprinter", "vito", "crafter",
                     "ducato", "boxer", "jumper", "kasten", "kangoo", "caddy",
                     "berlingo", "doblo", "partner", "rapid", "express")),
    ("VAN", ("van", "touran", "sharan", "zafira", "picasso", "scenic",
             "galaxy", "s-max", "c-max", "combo life", "verso")),
    ("SUV", ("suv", "tiguan", "touareg", "t-roc", "t-cross", "taigo", "kuga",
             "mokka", "grandland", "crossland", "sportage", "tucson",
             "qashqai", "juke", "kodiaq", "karoq", "kamiq", "x-trail",
             "captur", "duster", "ateca", "arona", "tarraco", "countryman",
             "x1", "x2", "x3", "x4", "x5", "x6", "x7", "q2", "q3", "q5",
             "q7", "q8", "gla", "glb", "glc", "gle", "gls", "evoque",
             "discovery", "tiguan allspace", "ecosport", "puma")),
    ("SPORTWAGEN", ("coupe", "coupé", "gti", "gtd", "amg", "911", "m2", "m3",
                    "m4", "m5", "rs3", "rs4", "rs5", "rs6", "rs7")),
    # Bewusst keine Zwei-Zeichen-Kuerzel wie "up", "ka" oder "gt": die treffen
    # Fliesstext im Titel ("Head UP" machte aus einem 530d einen Kleinwagen).
    ("KLEINWAGEN", ("polo", "corsa", "fiesta", "adam", "aygo", "i10",
                    "i20", "picanto", "panda", "twingo", "micra",
                    "swift", "yaris", "clio", "modus", "c30", "mii",
                    "citigo", "fabia", "ibiza")),
    ("LIMOUSINE", ("limousine", "lim.", "stufenheck", "saloon", "berlina")),
]

AUTOMATIC_HINTS = (
    "automatik", "automat", "dsg", "s tronic", "s-tronic", "tiptronic",
    "steptronic", "multitronic", "pdk", "xtronic", "edc", "g-tronic",
    "7g-tronic", "9g-tronic", "powershift", "eat8", "eat6", "aut.",
)


def fetch_dealer_pages(url: str = DEALER_URL) -> list[str]:
    """Laedt alle Seiten der Haendleruebersicht und gibt deren HTML zurueck."""
    pages: list[str] = []
    page = 1
    total_pages = 1

    while page <= min(total_pages, MAX_PAGES):
        target = url if page == 1 else f"{url}?pageNumber={page}"
        req = urllib.request.Request(target, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=45) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        if "Zugriff verweigert" in html or "Access denied" in html:
            raise PermissionError(
                "mobile.de hat den Abruf blockiert (Bot-Schutz). "
                "Siehe scripts/README.md – dann ueber --source api gehen."
            )

        pages.append(html)

        if page == 1:
            # "1/2" in der Pagination verraet die Gesamtzahl der Seiten
            match = re.search(r">\s*1\s*/\s*(\d+)\s*<", html)
            if match:
                total_pages = int(match.group(1))
            log(f"Haendlerseite: {total_pages} Seite(n), "
                f"{_total_count(html) or '?'} Fahrzeuge gemeldet")
        page += 1

    return pages


def _total_count(html: str) -> int | None:
    match = re.search(r'srp-header-title[^>]*>\s*(\d+)\s*Pkw', html)
    return int(match.group(1)) if match else None


def parse_dealer_page(html: str) -> list[dict]:
    """Zieht die Fahrzeuge aus dem gerenderten Markup der Haendlerseite.

    Verankert wird auf den data-testid-Attributen, nicht auf CSS-Klassen –
    die Klassennamen sind gehasht und aendern sich bei jedem mobile.de-Deploy.
    Die oben eingeblendete "Unsere Empfehlung" wird uebersprungen, weil sie
    ein Duplikat eines Eintrags aus der Liste ist.
    """
    markers = [
        (m.start(), m.group(1))
        for m in re.finditer(r'data-testid="listing-(\d+)"', html)
    ]
    listings: list[dict] = []

    for idx, (start, num) in enumerate(markers):
        end = markers[idx + 1][0] if idx + 1 < len(markers) else len(html)
        seg = html[start:end]

        title = _tag_text(seg, rf'data-testid="listing-{num}-title"')
        if not title:
            continue

        price_raw = re.search(r'data-testid="price-label"[^>]*>([^<]+)<', seg)
        image = re.search(r'src="(https://img\.classistatic\.de/[^"]+)"', seg)
        ad_id = re.search(r"adId=(\d+)", seg)
        attrs = re.search(
            r'data-testid="listing-details-attributes"(.*?)</section>', seg, re.S
        )

        listings.append({
            "title": _unescape(title),
            "priceRaw": price_raw.group(1) if price_raw else "",
            "imageUrl": image.group(1) if image else "",
            "adId": ad_id.group(1) if ad_id else "",
            "attrs": _strip_tags(attrs.group(1)) if attrs else "",
        })

    return listings


def _tag_text(segment: str, anchor: str) -> str:
    match = re.search(anchor + r"(.*?)</div>", segment, re.S)
    if not match:
        return ""
    inner = re.search(r"<h\d[^>]*>(.*?)</h\d>", match.group(1), re.S)
    return _strip_tags(inner.group(1) if inner else match.group(1))


def _strip_tags(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.replace("\u00a0", " ").split()).lstrip("> ").strip()


def _unescape(text: str) -> str:
    for a, b in (("&amp;", "&"), ("&quot;", '"'), ("&#x27;", "'"),
                 ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")):
        text = text.replace(a, b)
    return text.strip()


# Badges, die mobile.de dem Titel voranstellt
TITLE_BADGES = ("NEU", "NEUWAGEN", "TOP", "AKTION", "REDUZIERT")

# Zweites Titel-Token, das noch zum Modellnamen gehoert
MODEL_SUFFIXES = {
    "st", "gt", "gti", "gtd", "sw", "ST", "countryman", "clubman", "cooper",
    "avant", "touring", "variant", "rapid", "coupe", "sportback", "allspace",
    "cross", "allroad", "tourer", "active", "scout", "van", "kasten",
    "cabrio", "roadster", "express", "combi", "plus",
}
ROMAN = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"}


def split_make_model(title: str) -> tuple[str, str, str]:
    """Teilt den Anzeigentitel in Marke, Modell und Zusatz.

    mobile.de-Titel sind freier Text vom Haendler, keine strukturierten Felder –
    das hier ist bewusst eine Heuristik. Lieber ein kurzes, richtiges Modell
    ("BMW 118") als ein langes, falsches ("BMW 118 1").
    """
    cleaned = title.strip()
    for badge in TITLE_BADGES:
        if cleaned.upper().startswith(badge + " "):
            cleaned = cleaned[len(badge):].strip()

    for make in MAKES:
        if cleaned.lower().startswith(make.lower()):
            rest = cleaned[len(make):].strip(" -,|")
            tokens = rest.split()
            if not tokens:
                return pretty_make(make), "", ""
            model_tokens = [tokens[0]]
            if len(tokens) > 1 and _is_model_continuation(tokens[0], tokens[1]):
                model_tokens.append(tokens[1])
            model = " ".join(model_tokens)
            variant = rest[len(model):].strip(" -,|;*#")
            return pretty_make(make), model, variant

    tokens = cleaned.split()
    return (
        pretty_make(tokens[0]) if tokens else "",
        tokens[1] if len(tokens) > 1 else "",
        " ".join(tokens[2:]),
    )


def _is_model_continuation(first: str, second: str) -> bool:
    """Gehoert `second` noch zum Modellnamen?"""
    low = second.lower().strip(",;*#|")
    if low in ROMAN:                      # Golf VII
        return True
    if len(low) == 1 and low.isalpha():   # Corsa E, 530 d
        return True
    if low in MODEL_SUFFIXES:             # Leon ST, Cooper Countryman
        return True
    if re.fullmatch(r"\d+", low):         # E 250, GLE 350 – aber nicht "118 1"
        return not re.fullmatch(r"\d+", first)
    return False


def guess_type(title: str) -> str:
    tokens = set(re.findall(r"[a-z0-9äöüß.-]+", title.lower()))
    joined = " " + " ".join(re.findall(r"[a-z0-9äöüß.-]+", title.lower())) + " "
    for label, hints in TYPE_HINTS:
        for hint in hints:
            if " " in hint:
                if f" {hint} " in joined:
                    return label
            elif hint in tokens:
                return label
    return ""


def short_fuel(raw: str) -> str:
    """Kurzes Label fuer den Kraftstoff.

    mobile.de schreibt "Hybrid (Diesel/Elektro)" – der Filter auf der Website
    vergleicht exakt, deshalb braucht es ein einheitliches kurzes Label.
    """
    low = raw.lower()
    if "hybrid" in low:
        return "Hybrid"
    for label in ("Benzin", "Diesel", "Elektro", "Autogas", "Erdgas", "Wasserstoff"):
        if label.lower() in low:
            return label
    return raw.strip()


def normalize_live(raw: dict, index: int) -> dict | None:
    """Baut aus einem geparsten Uebersichtseintrag einen staticCars-Eintrag.

    Die Uebersichtsseite liefert nur Titel, Preis, EZ, km, Leistung, Kraftstoff,
    Unfallfreiheit und ein Bild. Alles andere bleibt leer – die Website blendet
    leere Felder aus, statt sie mit erfundenen Werten zu fuellen.
    """
    title = raw.get("title", "").strip()
    price = _to_int(raw.get("priceRaw", "").replace(".", ""))
    if not title or price <= 0:
        return None

    attrs = raw.get("attrs", "")
    ez = re.search(r"EZ\s*(\d{2})/(\d{4})", attrs)
    km = re.search(r"([\d.]+)\s*km", attrs)
    power = re.search(r"(\d+)\s*kW\s*\((\d+)\s*PS\)", attrs)
    # Die Attributzeile endet immer mit dem Kraftstoff, der auch
    # "Hybrid (Diesel/Elektro)" heissen kann – darum das letzte Segment nehmen
    # statt gegen eine Whitelist zu pruefen.
    parts = [p.strip() for p in attrs.split("•") if p.strip()]
    fuel = short_fuel(parts[-1]) if parts and not parts[-1].endswith("km") else ""

    make, model, variant = split_make_model(title)
    image = raw.get("imageUrl", "")
    if image:
        image = f"{image.split('?')[0]}?rule={IMAGE_RULE}"

    ad_id = raw.get("adId", "")
    link = (
        f"https://suchen.mobile.de/fahrzeuge/details.html?id={ad_id}"
        if ad_id else DEALER_URL
    )

    low = title.lower()
    return {
        "id": index,
        "make": make,
        "model": model,
        "name": f"{make} {model}".strip(),
        "variant": variant,
        "type": guess_type(title),
        "year": int(ez.group(2)) if ez else 0,
        "ez": f"{ez.group(1)}/{ez.group(2)}" if ez else "",
        "km": _to_int(km.group(1).replace(".", "")) if km else 0,
        "ps": _to_int(power.group(2)) if power else 0,
        "kw": _to_int(power.group(1)) if power else 0,
        "fuel": fuel,
        "gear": "Automatik" if any(h in low for h in AUTOMATIC_HINTS) else "",
        "price": price,
        "condition": "Gebraucht",
        "unfallfrei": "Ja" if "Unfallfrei" in attrs else "",
        "hubraum": "",
        "schadstoff": "",
        "scheckheft": "",
        "nichtraucher": "",
        "vorbesitzer": 0,
        "tueren": "",
        "sitzplaetze": 0,
        "aussenfarbe": "",
        "innenfarbe": "",
        "polsterung": "",
        "imageUrl": image,
        "link": link,
        "guarantee": False,
        "adId": ad_id,
    }


# ──────────────────────────────────────────────────────────────────────
#  Quelle 1: offizielle Search-API
# ──────────────────────────────────────────────────────────────────────

def fetch_from_api(user: str, password: str, customer_id: str) -> list[dict]:
    """Holt alle Anzeigen des Haendlers ueber die mobile.de Search-API."""
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    ads: list[dict] = []
    page = 1

    while True:
        query = urllib.parse.urlencode(
            {
                "customerId": customer_id,
                "page.size": PAGE_SIZE,
                "page.number": page,
            }
        )
        req = urllib.request.Request(
            f"{API_BASE}?{query}",
            headers={
                "Authorization": f"Basic {token}",
                "Accept": API_ACCEPT,
                "User-Agent": "autohausdilltal.de-sync/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.load(resp)

        batch = payload.get("ads") or payload.get("searchResult", {}).get("ads") or []
        if isinstance(batch, dict):  # manche Formate verschachteln nochmal
            batch = batch.get("ad", [])
        ads.extend(batch)

        max_pages = payload.get("maxPages") or payload.get("pageCount") or 1
        log(f"Seite {page}/{max_pages} – {len(batch)} Anzeigen")
        if page >= max_pages or not batch:
            break
        page += 1

    return ads


# ──────────────────────────────────────────────────────────────────────
#  Quelle 2: lokal gespeicherte Haendlerseite
# ──────────────────────────────────────────────────────────────────────

def fetch_from_saved_html(path: Path) -> list[dict]:
    """Zieht die eingebetteten Anzeigen-Objekte aus einer gespeicherten HTML-Seite.

    mobile.de rendert die Haendlerseite aus einem JSON-Blob im Markup. Wir
    suchen jedes Objekt, das nach einer Fahrzeuganzeige aussieht.
    """
    html = path.read_text(encoding="utf-8", errors="replace")
    ads: list[dict] = []
    seen: set[str] = set()

    # Alle JSON-Objekte aus <script>-Bloecken einsammeln und rekursiv durchsuchen.
    for script in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
        for match in re.finditer(r"\{", script):
            obj = _try_json_object(script, match.start())
            if obj is None:
                continue
            found_here = False
            for ad in _walk_for_ads(obj):
                key = str(ad.get("mobileAdId") or ad.get("adId") or ad.get("id") or "")
                if key and key not in seen:
                    seen.add(key)
                    ads.append(ad)
                    found_here = True
            if found_here:
                break  # dieser Script-Block war der State-Blob, naechster Block

    return ads


def _try_json_object(text: str, start: int):
    """Versucht ab `start` ein balanciertes JSON-Objekt zu lesen."""
    depth, in_str, esc = 0, False, False
    for i in range(start, min(len(text), start + 8_000_000)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _walk_for_ads(node):
    """Findet rekursiv alle Dicts, die wie eine Fahrzeuganzeige aussehen."""
    if isinstance(node, dict):
        if ("make" in node or "makeName" in node) and (
            "price" in node or "mileage" in node
        ):
            yield node
        for value in node.values():
            yield from _walk_for_ads(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_for_ads(value)


# ──────────────────────────────────────────────────────────────────────
#  Normalisierung: mobile.de-Anzeige -> staticCars-Eintrag
# ──────────────────────────────────────────────────────────────────────

def _first(node, *keys, default=None):
    for key in keys:
        if isinstance(node, dict) and node.get(key) not in (None, "", []):
            return node[key]
    return default


def _to_int(value, default=0) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^0-9]", "", str(value).split(",")[0].split(".")[0])
    return int(digits) if digits else default


def _price(ad) -> int:
    price = ad.get("price")
    if isinstance(price, dict):
        raw = _first(
            price,
            "consumerPriceGross",
            "grossAmount",
            "amount",
            "consumerPriceNet",
            default=0,
        )
        if isinstance(raw, dict):
            raw = _first(raw, "amount", "value", default=0)
        return _to_int(raw)
    return _to_int(price)


def _image_url(ad) -> str:
    """Erste classistatic-Bild-URL aus beliebiger Bildstruktur, auf mo-1600 normiert."""
    found: list[str] = []

    def walk(node):
        if found:
            return
        if isinstance(node, str):
            if "img.classistatic.de" in node and "/images/" in node:
                found.append(node)
        elif isinstance(node, dict):
            # bevorzugt grosse Varianten, sonst irgendeine
            for key in ("xxxl", "xxl", "xl", "l", "ref", "url", "uri", "src"):
                if key in node:
                    walk(node[key])
                    if found:
                        return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(ad.get("images") or ad.get("image") or ad.get("pictures"))
    if not found:
        walk({k: v for k, v in ad.items() if k not in ("seller", "dealer")})
    if not found:
        return ""

    url = found[0]
    if url.startswith("//"):
        url = "https:" + url
    base = url.split("?")[0]
    return f"{base}?rule={IMAGE_RULE}"


def _year(ad) -> int:
    raw = str(_first(ad, "firstRegistration", "firstRegistrationDate", default="") or "")
    match = re.search(r"(19|20)\d{2}", raw)
    return int(match.group(0)) if match else 0


def _yes_no(value, invert: bool = False) -> str:
    if value is None:
        return "Ja" if invert else "Nein"
    truthy = bool(value) if not isinstance(value, str) else value.lower() in (
        "true",
        "yes",
        "ja",
        "1",
    )
    if invert:
        truthy = not truthy
    return "Ja" if truthy else "Nein"


def _de_thousands(number: int) -> str:
    return f"{number:,}".replace(",", ".")


def normalize(ad: dict, index: int) -> dict | None:
    make = str(_first(ad, "make", "makeName", default="")).strip()
    model = str(_first(ad, "model", "modelName", default="")).strip()
    if not make:
        return None

    make = pretty_make(make)

    power_kw = _to_int(_first(ad, "power", "powerKw", default=0))
    ps = round(power_kw * 1.35962) if power_kw else _to_int(_first(ad, "ps", default=0))
    cc = _to_int(_first(ad, "cubicCapacity", "cubicCapacityCcm", default=0))
    price = _price(ad)
    if price <= 0:
        return None

    category = str(_first(ad, "category", "vehicleCategory", default="") or "")
    variant = str(_first(ad, "modelDescription", "description", default="") or "").strip()

    return {
        "id": index,
        "make": make,
        "model": model,
        "name": f"{make} {model}".strip(),
        "variant": variant,
        "type": CATEGORY.get(category, "SONSTIGE"),
        "year": _year(ad),
        "km": _to_int(_first(ad, "mileage", "mileageKm", default=0)),
        "ps": ps,
        "fuel": FUEL.get(str(_first(ad, "fuel", default="")), "Sonstige"),
        "gear": GEARBOX.get(str(_first(ad, "gearbox", default="")), "Schaltgetriebe"),
        "price": price,
        "condition": "Neu" if str(_first(ad, "condition", default="USED")).upper() == "NEW" else "Gebraucht",
        "unfallfrei": _yes_no(_first(ad, "accidentDamaged", "damageUnrepaired", default=False), invert=True),
        "hubraum": f"{_de_thousands(cc)} cm³" if cc else "",
        "schadstoff": EMISSION.get(str(_first(ad, "emissionClass", default="")), ""),
        "scheckheft": _yes_no(_first(ad, "fullServiceHistory", default=None)),
        "nichtraucher": _yes_no(_first(ad, "nonSmokerVehicle", default=None)),
        "vorbesitzer": _to_int(_first(ad, "numberOfPreviousOwners", default=0)),
        "tueren": DOORS.get(str(_first(ad, "doors", default="")), str(_first(ad, "doors", default="5"))),
        "sitzplaetze": _to_int(_first(ad, "seats", default=5), default=5),
        "aussenfarbe": COLOR.get(str(_first(ad, "exteriorColor", default="")), ""),
        "innenfarbe": COLOR.get(str(_first(ad, "interiorColor", default="")), ""),
        "polsterung": INTERIOR_TYPE.get(str(_first(ad, "interiorType", default="")), ""),
        "imageUrl": _image_url(ad),
        "link": str(_first(ad, "detailPageUrl", "url", default="https://home.mobile.de/TDAUTOMOBILE")),
        "guarantee": bool(_first(ad, "warranty", "hasWarranty", default=False)),
    }


# ──────────────────────────────────────────────────────────────────────
#  index.html schreiben
# ──────────────────────────────────────────────────────────────────────

FIELD_ORDER = [
    "id", "make", "model", "name", "variant", "type", "year", "ez", "km",
    "ps", "kw", "fuel", "gear", "price", "condition", "unfallfrei", "hubraum",
    "schadstoff", "scheckheft", "nichtraucher", "vorbesitzer", "tueren",
    "sitzplaetze", "aussenfarbe", "innenfarbe", "polsterung", "imageUrl",
    "link", "guarantee", "adId",
]


def js_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
    return f"'{escaped}'"


def render_static_cars(cars: list[dict]) -> str:
    lines = ["const staticCars=["]
    for car in cars:
        fields = ",".join(f"{key}:{js_value(car.get(key, ''))}" for key in FIELD_ORDER)
        lines.append(f"  {{{fields}}},")
    lines.append("];")
    return "\n".join(lines)


def render_options(values) -> str:
    options = "".join(f"<option>{v}</option>" for v in values)
    return f"<option>Alle</option>{options}"


def filter_options(cars: list[dict]) -> dict[str, str]:
    """Baut alle Filter-Dropdowns aus dem tatsaechlichen Bestand.

    Hartkodierte Optionen laufen bei einem Live-Bestand sofort ins Leere –
    Marken verschwinden, Baujahre kommen hinzu. Dropdowns, fuer die es keine
    Daten gibt (z.B. Getriebe, wenn mobile.de es nicht mitliefert), bekommen
    nur "Alle" und werden vom Frontend ausgeblendet.
    """
    makes = sorted({c["make"] for c in cars if c.get("make")}, key=_sortkey)
    fuels = sorted({c["fuel"] for c in cars if c.get("fuel")}, key=_sortkey)
    gears = sorted({c["gear"] for c in cars if c.get("gear")}, key=_sortkey)
    years = sorted({c["year"] for c in cars if c.get("year")})
    return {
        "fMarke": render_options(makes),
        "fKraftstoff": render_options(fuels),
        "fGetriebe": render_options(gears),
        "fJahr": render_options(years),
    }


def _sortkey(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def patch_index_html(html: str, cars: list[dict]) -> str:
    new_block = render_static_cars(cars)
    patched, count = re.subn(
        r"const staticCars=\[.*?\n\];",
        lambda _: new_block,
        html,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("staticCars-Block in index.html nicht gefunden – Abbruch.")

    # Filter-Dropdowns mitziehen (kommen im Markup ggf. mehrfach vor)
    for select_id, options in filter_options(cars).items():
        patched = re.sub(
            rf'(<select class="filter-select" id="{select_id}">)(.*?)(</select>)',
            lambda m, o=options: m.group(1) + o + m.group(3),
            patched,
            flags=re.S,
        )
    return patched


# ──────────────────────────────────────────────────────────────────────

def read_cars_from_index() -> list[dict]:
    """Liest das aktuelle staticCars-Array aus index.html zurueck.

    Dient dazu, data/cars.json wieder auf den Stand der Website zu bringen,
    wenn index.html von Hand bearbeitet wurde.
    """
    html = INDEX_HTML.read_text(encoding="utf-8")
    block = re.search(r"const staticCars=\[(.*?)\n\];", html, re.S)
    if not block:
        raise RuntimeError("staticCars-Block in index.html nicht gefunden.")

    cars = []
    for line in block.group(1).strip().splitlines():
        line = line.strip().rstrip(",")
        if not (line.startswith("{") and line.endswith("}")):
            continue
        car = {}
        for key, raw in re.findall(
            r"(\w+):('(?:[^'\\]|\\.)*'|true|false|-?\d+(?:\.\d+)?)", line
        ):
            if raw.startswith("'"):
                car[key] = raw[1:-1].replace("\\'", "'").replace("\\\\", "\\")
            elif raw in ("true", "false"):
                car[key] = raw == "true"
            else:
                car[key] = int(raw) if raw.lstrip("-").isdigit() else float(raw)
        cars.append(car)
    return cars


def load_previous() -> list[dict]:
    if CARS_JSON.exists():
        try:
            return json.loads(CARS_JSON.read_text(encoding="utf-8")).get("cars", [])
        except (json.JSONDecodeError, AttributeError):
            return []
    return []


def update_sitemap_lastmod() -> None:
    """Setzt <lastmod> in sitemap.xml auf heute.

    Der Fahrzeugbestand ist der einzige Teil der Seite, der sich regelmaessig
    aendert. Ohne diesen Schritt meldet die Sitemap dauerhaft ein altes Datum,
    und Suchmaschinen crawlen die Seite seltener, als sie sich tatsaechlich
    aktualisiert. Fehler hier duerfen den Sync nicht abbrechen.
    """
    if not SITEMAP_XML.exists():
        return
    try:
        xml = SITEMAP_XML.read_text(encoding="utf-8")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        patched, n = re.subn(
            r"<lastmod>\d{4}-\d{2}-\d{2}</lastmod>",
            f"<lastmod>{today}</lastmod>",
            xml,
        )
        if n and patched != xml:
            SITEMAP_XML.write_text(patched, encoding="utf-8")
            log(f"sitemap.xml: lastmod auf {today} gesetzt.")
    except OSError as exc:
        log(f"Warnung: sitemap.xml nicht aktualisiert ({exc}).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--source",
        choices=["live", "api", "html", "index"],
        default="live",
        help="live = Haendlerseite home.mobile.de abrufen (Standard), "
             "api = mobile.de Search-API, html = gespeicherte Haendlerseite, "
             "index = data/cars.json aus dem aktuellen index.html neu aufbauen",
    )
    parser.add_argument("--file", type=Path, help="Pfad zur gespeicherten HTML-Seite (--source html)")
    parser.add_argument("--dry-run", action="store_true", help="nichts schreiben, nur berichten")
    args = parser.parse_args()

    previous = load_previous()
    log(f"Bisher bekannt: {len(previous)} Fahrzeuge")

    try:
        if args.source == "live":
            raw_ads = []
            for html_page in fetch_dealer_pages():
                raw_ads.extend(parse_dealer_page(html_page))

        elif args.source == "api":
            user = os.environ.get("MOBILE_API_USER", "")
            password = os.environ.get("MOBILE_API_PASS", "")
            customer_id = os.environ.get("MOBILE_CUSTOMER_ID", "")
            if not (user and password and customer_id):
                log("MOBILE_API_USER / MOBILE_API_PASS / MOBILE_CUSTOMER_ID fehlen – "
                    "kein Abruf moeglich, index.html bleibt unveraendert.")
                return 0
            raw_ads = fetch_from_api(user, password, customer_id)

        elif args.source == "html":
            if not args.file or not args.file.exists():
                log("--file fehlt oder existiert nicht.")
                return 0
            raw_ads = fetch_from_saved_html(args.file)

        else:  # index
            raw_ads = []

    except PermissionError as exc:
        log(str(exc))
        log("Abruf blockiert – alte Daten bleiben stehen.")
        return 0
    except urllib.error.HTTPError as exc:
        body = exc.read()[:300].decode(errors="replace")
        log(f"HTTP {exc.code} von mobile.de: {body}")
        log("Abruf fehlgeschlagen – alte Daten bleiben stehen.")
        return 0
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        log(f"Abruf fehlgeschlagen ({exc.__class__.__name__}: {exc}) – alte Daten bleiben stehen.")
        return 0

    if args.source == "index":
        cars = read_cars_from_index()
    else:
        mapper = normalize_live if args.source == "live" else normalize
        cars = []
        seen_ads: set[str] = set()
        for ad in raw_ads:
            car = mapper(ad, len(cars) + 1)
            if not car:
                continue
            # "Unsere Empfehlung" oben auf der Seite ist ein Duplikat
            key = car.get("adId") or f"{car['name']}|{car['price']}|{car['km']}"
            if key in seen_ads:
                continue
            seen_ads.add(key)
            car["id"] = len(cars) + 1
            cars.append(car)

    log(f"Abgerufen: {len(raw_ads)} Anzeigen -> {len(cars)} verwertbare Fahrzeuge")

    if not cars:
        log("Keine Fahrzeuge erkannt – index.html bleibt unveraendert.")
        return 0

    if previous and len(cars) < len(previous) * MIN_RATIO_OF_PREVIOUS:
        log(f"Nur {len(cars)} statt zuvor {len(previous)} Fahrzeuge – sieht nach "
            f"kaputtem Abruf aus, index.html bleibt unveraendert.")
        return 0

    without_image = [c["name"] for c in cars if not c["imageUrl"]]
    if without_image:
        log(f"Hinweis: {len(without_image)} Fahrzeuge ohne Bild ({', '.join(without_image[:3])} …)")

    html = INDEX_HTML.read_text(encoding="utf-8")
    patched = patch_index_html(html, cars)

    if args.dry_run:
        log("--dry-run: nichts geschrieben.")
        print(render_static_cars(cars)[:2000])
        return 0

    if patched == html:
        log("Keine Aenderung – index.html ist aktuell.")
        return 0

    INDEX_HTML.write_text(patched, encoding="utf-8")
    CARS_JSON.parent.mkdir(parents=True, exist_ok=True)
    CARS_JSON.write_text(
        json.dumps(
            {
                "syncedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": args.source,
                "count": len(cars),
                "cars": cars,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    update_sitemap_lastmod()
    log(f"index.html aktualisiert – {len(cars)} Fahrzeuge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
