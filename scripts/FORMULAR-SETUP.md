# Formularversand einrichten (einmalig, ca. 3 Minuten)

Die Formulare schicken ihre Anfragen an ein eigenes kleines Programm im
Google-Konto des Autohauses. Das ersetzt den Fremddienst FormSubmit, der am
04.11.2026 stundenlang ausgefallen ist.

**Was das Relay macht:** jede Anfrage als Mail an `autohausdilltal@web.de`
(Kopie an `nicoklein@nkzs.de`) **und** zusätzlich als Zeile in einer
Google-Tabelle. Selbst wenn der Mailversand einmal klemmt, ist die Anfrage
dann nicht verloren.

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

## 5. Abnahme — erst danach gilt es als repariert

Auf <https://autohausdilltal.de> das Kontaktformular mit einer echten Adresse
absenden und prüfen:

- [ ] grüne Bestätigung auf der Website
- [ ] Mail liegt in `autohausdilltal@web.de`
- [ ] neue Zeile in der Google-Tabelle „Anfragen autohausdilltal.de"

Erst wenn alle drei Haken sitzen, ist der Versand bestätigt.

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
