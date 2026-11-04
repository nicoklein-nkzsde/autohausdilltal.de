# Formularversand einrichten (einmalig, ca. 3 Minuten)

Die Formulare schicken ihre Anfragen an ein eigenes kleines Programm im
Google-Konto des Autohauses. Das ersetzt den Fremddienst FormSubmit, der am
04.11.2026 stundenlang ausgefallen ist.

**Was das Relay macht:** jede Anfrage geht auf drei Wegen raus — als Zeile in
eine Google-Tabelle, als Mail an `autohausdilltal@web.de` (Kopie an
`nicoklein@nkzs.de`) und als WhatsApp-Nachricht an Tamo. Fällt einer der Wege
aus, ist die Anfrage trotzdem da. Die Website meldet nur dann Erfolg, wenn
mindestens ein Weg bestätigt hat.

## 1. Programm anlegen

1. <https://script.google.com> öffnen (mit dem Google-Konto anmelden, das die
   Mails verschicken soll)
2. **Neues Projekt**
3. Den Inhalt von `scripts/formular-relay.gs` komplett in das Code-Fenster
   kopieren — der vorhandene Beispielcode wird dabei ersetzt
4. Oben rechts **Speichern**, dem Projekt einen Namen geben
   (z. B. „Formulare autohausdilltal.de")

## 2. Zustellung testen, bevor irgendetwas live geht

1. Oben die Funktion **`testMail`** auswählen → **Ausführen**
2. Google fragt einmalig nach der Erlaubnis, Mails zu senden:
   **Berechtigungen prüfen** → Konto wählen → **Erweitert** →
   **„… (unsicher)" öffnen** → **Zulassen**
   (Die Warnung erscheint bei jedem selbst geschriebenen Script, das ist normal.)
3. **Jetzt im Postfach `autohausdilltal@web.de` nachsehen.**
   Kommt die Testmail nicht an, ist etwas falsch — dann nicht weitermachen.

## 3. Veröffentlichen

1. Oben rechts **Bereitstellen** → **Neue Bereitstellung**
2. Zahnrad neben „Typ auswählen" → **Web-App**
3. Einstellen:
   - *Ausführen als:* **Ich**
   - *Zugriff:* **Jeder** ← wichtig, sonst kann die Website nichts senden
4. **Bereitstellen** → die angezeigte **Web-App-URL** kopieren
   (sie endet auf `/exec`)

## 4. URL in die Website eintragen

In `index.html` die Zeile

```js
const RELAY_URL='';   // <-- hier die /exec-URL aus Apps Script eintragen
```

ausfüllen:

```js
const RELAY_URL='https://script.google.com/macros/s/AKfyc.../exec';
```

Dann committen und pushen. Nach ein paar Minuten ist es live.

## 5. WhatsApp-Backup einschalten

Zwei Wege, unterschiedlich zuverlässig. **Weg A läuft sofort und kostet nichts**,
Weg B ist die Automatik und hat einen Haken.

### A) Kunde schickt die Anfrage mit einem Tipp zusätzlich per WhatsApp

Ist bereits aktiv, nichts einzurichten. Nach dem Absenden erscheint neben der
Bestätigung ein Knopf **„Anfrage zusätzlich per WhatsApp schicken"** — die
komplette Anfrage ist darin schon vorgeschrieben, der Kunde tippt nur auf
Senden. Bei Fotos heißt der Knopf **„Jetzt die Fotos per WhatsApp senden"**,
und das ist ohnehin der einzige Weg, die Bilder in voller Auflösung zu bekommen.

Das hängt an einem Tipp des Kunden — aber es funktioniert heute, braucht kein
Konto und kann nicht ausfallen.

### B) Automatisch bei jeder Anfrage (CallMeBot)

Der Code dafür steht im Relay, es fehlen nur zwei Einträge. **Aber:**

> - CallMeBot schreibt auf seiner Seite: *„The Free API is only for personal
>   use."* Für die Leads eines Autohauses ist das streng genommen gewerblich.
> - Der Bot nimmt **derzeit keine neuen Nummern an** („currently full"), die
>   Kontaktnummer ist deshalb gerade nicht einmal veröffentlicht.

Wenn wieder Plätze frei sind, steht die aktuelle Nummer auf
<https://www.callmebot.com/blog/free-api-whatsapp-messages/> — **immer von dort
holen, die Nummer ändert sich.** Dann:

1. Tamo speichert die dort genannte Nummer als WhatsApp-Kontakt
2. und schickt ihr genau diesen Text: `I allow callmebot to send me messages`
3. Zurück kommt ein **API-Schlüssel** (bis zu 2 Minuten; kommt keiner,
   erst nach 24 h erneut versuchen)
4. Im Apps-Script-Projekt: Zahnrad (**Projekteinstellungen**) → unten
   **Skripteigenschaften** → zweimal **hinzufügen**:

   | Eigenschaft | Wert |
   |---|---|
   | `WHATSAPP_NUMMER` | `+4915168410570` (Tamos Nummer, mit Ländervorwahl) |
   | `WHATSAPP_APIKEY` | der Schlüssel aus Schritt 3 |

5. **Speichern**, dann Funktion **`testWhatsApp`** ausführen — auf Tamos Handy
   muss eine Testnachricht ankommen.

Die Schlüssel stehen bewusst nur dort und nicht im Code — das Repo ist
öffentlich. Ohne die beiden Einträge überspringt das Relay den Weg einfach,
Tabelle und Mail laufen normal weiter.

**Soll WhatsApp garantiert und gewerblich sauber automatisch laufen**, führt
kein Weg an einem bezahlten Anbieter vorbei (Twilio oder textmebot, Centbeträge
pro Nachricht). Dafür reicht es, in `perWhatsApp()` die URL auszutauschen.

## 6. Abnahme — erst danach gilt es als repariert

Auf <https://autohausdilltal.de> das Kontaktformular mit einer echten Adresse
absenden und prüfen:

- [ ] grüne Bestätigung auf der Website
- [ ] Mail liegt in `autohausdilltal@web.de`
- [ ] neue Zeile in der Google-Tabelle „Anfragen autohausdilltal.de"
- [ ] der Knopf „Anfrage zusätzlich per WhatsApp schicken" erscheint und
      öffnet WhatsApp mit der fertigen Anfrage

Erst wenn alle Haken sitzen, ist der Versand bestätigt.

## Änderungen am Code später

Nach jeder Änderung an `formular-relay.gs`:
**Bereitstellen → Bereitstellungen verwalten → Stift → Version „Neu" → Bereitstellen.**
Die URL bleibt dabei gleich.

## Grenzen

- Google erlaubt einem normalen Konto **100 Mails pro Tag** — für ein Autohaus
  reichlich. Die Tabelle hat kein Limit.
- Anhänge sind auf **8 MB pro Anfrage** begrenzt. Wählt ein Kunde mehr Fotos
  aus, werden die ersten angehängt und in der Mail steht ein Hinweis, wie viele
  fehlen.
- Die Mail kommt vom Google-Konto, nicht von `web.de`. Antwortet Tamo direkt
  auf die Mail, geht die Antwort an den Kunden (Reply-To ist gesetzt).
