# Fahrzeug-Sync von mobile.de

Hält das `staticCars`-Array in `index.html` automatisch auf dem Stand des
mobile.de-Bestands von **TDAUTOMOBILE**.

## Wichtig zuerst: Scraping funktioniert nicht

`home.mobile.de/TDAUTOMOBILE` liegt hinter **Akamai Bot Manager**. Jeder
Server-Request bekommt HTTP **403 „Zugriff verweigert"** zurück — getestet am
05.09.2026, sowohl für `home.mobile.de` als auch `suchen.mobile.de`, mit
aktuellem Browser-User-Agent. Aus GitHub-Actions-Runnern (Rechenzentrums-IPs)
wird das eher strenger, nicht lockerer.

Deshalb läuft der Sync über die **offizielle mobile.de Search-API**. Die ist für
Händler kostenlos freischaltbar, liefert saubere strukturierte Daten und bricht
nicht bei jedem Redesign der Website.

## Einrichtung

### 1. API-Zugang bei mobile.de anfordern

Tamo (als Inhaber des Händler-Accounts) fordert bei mobile.de den Zugang zur
**Search-API** an — entweder im Händlerbereich unter den Schnittstellen-
Einstellungen oder per Mail an den mobile.de-Händlersupport. Formulierung:

> Wir möchten unseren Fahrzeugbestand automatisiert auf unserer eigenen Website
> autohausdilltal.de anzeigen. Bitte schalten Sie uns die Search-API frei und
> senden Sie uns die Zugangsdaten sowie unsere Kundennummer (customerId).

Zurück kommen drei Dinge:

| Wert | Beispiel | wofür |
|---|---|---|
| API-Benutzername | `api_tdautomobile` | Basic-Auth |
| API-Passwort | `…` | Basic-Auth |
| customerId / Kundennummer | `1234567` | filtert auf genau euren Bestand |

### 2. Secrets in GitHub eintragen

Im Repo `nicoklein-nkzsde/autohausdilltal.de`:

**Settings → Secrets and variables → Actions → New repository secret**

Drei Secrets anlegen:

| Name | Wert |
|---|---|
| `MOBILE_API_USER` | API-Benutzername |
| `MOBILE_API_PASS` | API-Passwort |
| `MOBILE_CUSTOMER_ID` | Kundennummer |

Oder per CLI:

```bash
gh secret set MOBILE_API_USER    --repo nicoklein-nkzsde/autohausdilltal.de
gh secret set MOBILE_API_PASS    --repo nicoklein-nkzsde/autohausdilltal.de
gh secret set MOBILE_CUSTOMER_ID --repo nicoklein-nkzsde/autohausdilltal.de
```

### 3. Ein GitHub-Token brauchst du NICHT

Der Workflow pusht mit dem eingebauten `GITHUB_TOKEN`, das Actions bei jedem Lauf
automatisch bereitstellt. Dafür genügt der Block

```yaml
permissions:
  contents: write
```

im Workflow — der ist schon drin. Zusätzlich muss einmalig unter
**Settings → Actions → General → Workflow permissions** die Option
**„Read and write permissions"** aktiv sein.

Ein eigener Personal Access Token wäre nur nötig, wenn der Push einen weiteren
Workflow auslösen soll — das ist hier nicht der Fall. Der GitHub-Pages-Build
startet nach dem Push trotzdem.

### 4. Testen

**Actions → „Fahrzeuge von mobile.de synchronisieren" → Run workflow**,
`dry_run` auf `true` — dann wird nichts committet, aber du siehst im Log, was
gefunden wurde.

## Lokale Nutzung

```bash
# Testlauf gegen die API, ohne zu schreiben
MOBILE_API_USER=… MOBILE_API_PASS=… MOBILE_CUSTOMER_ID=… \
  python3 scripts/sync_cars.py --source api --dry-run
```

### Ohne API: Händlerseite von Hand speichern

Solange die API-Zugangsdaten noch nicht da sind, geht es auch manuell:

1. `https://home.mobile.de/TDAUTOMOBILE` im Browser öffnen, ganz nach unten
   scrollen, bis alle Fahrzeuge geladen sind
2. Seite sichern (`Cmd+S`, „Webseite, komplett" oder „nur HTML")
3. ```bash
   python3 scripts/sync_cars.py --source html --file ~/Downloads/haendlerseite.html
   ```
4. `git add -A && git commit && git push`

### Nach Handarbeit an index.html

Wenn du das `staticCars`-Array direkt im Code änderst, danach einmal

```bash
python3 scripts/sync_cars.py --source index
```

damit `data/cars.json` wieder zum Website-Stand passt.

## Was das Script sonst noch macht

- schreibt `data/cars.json` als Protokoll des letzten erfolgreichen Syncs
- aktualisiert das Marken-Dropdown (`#fMarke`) passend zum neuen Bestand,
  damit der Filter nicht ins Leere läuft
- rechnet kW in PS um, übersetzt die mobile.de-Codes ins Deutsche und normiert
  die Bild-URLs auf `?rule=mo-1600` (gleiche Größe wie bisher)

## Sicherheitsnetze

Der Sync fasst `index.html` **nicht** an, wenn:

- die Secrets fehlen
- mobile.de einen Fehler oder Timeout liefert
- gar keine Fahrzeuge erkannt wurden
- weniger als die Hälfte der zuletzt bekannten Fahrzeuge zurückkommt
  (Schwelle: `MIN_RATIO_OF_PREVIOUS` in `sync_cars.py`)

In all diesen Fällen endet der Lauf mit Exit-Code 0 und einer Warnung im
Actions-Log — die Website bleibt mit den alten Daten online.
