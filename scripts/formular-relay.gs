/**
 * Formular-Relay für autohausdilltal.de
 * ---------------------------------------------------------------------------
 * Nimmt die Anfragen der drei Formulare (Ankauf, Termin, Kontakt) entgegen,
 * schreibt jede Anfrage in eine Google-Tabelle und schickt sie per Mail weiter.
 *
 * Warum selbst gehostet: Der vorher genutzte Dienst FormSubmit war am
 * 04.11.2026 über Stunden komplett ausgefallen (HTTP 522) – Anfragen gingen
 * verloren. Dieses Relay läuft im eigenen Google-Konto und hat keine fremde
 * Abhängigkeit. Zusätzlich landet jede Anfrage in der Tabelle: Selbst wenn der
 * Mailversand einmal klemmt, ist der Lead nicht weg.
 *
 * Einrichtung: siehe scripts/FORMULAR-SETUP.md
 */

var EMPFAENGER   = 'autohausdilltal@web.de';
var KOPIE        = 'nicoklein@nkzs.de';
var TABELLEN_NAME = 'Anfragen autohausdilltal.de';

var TITEL = {
  ankauf:  'Fahrzeugankauf-Anfrage über autohausdilltal.de',
  termin:  'Terminanfrage über autohausdilltal.de',
  kontakt: 'Kontaktanfrage über autohausdilltal.de'
};

/** Aufruf im Browser – zum Prüfen, ob die Bereitstellung steht. */
function doGet() {
  return HtmlService.createHtmlOutput(
    '<h2>Formular-Relay autohausdilltal.de</h2>' +
    '<p>Läuft. Anfragen werden an ' + EMPFAENGER + ' zugestellt.</p>'
  );
}

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) return antwort({ ok: false, fehler: 'leere Anfrage' });

    var d      = JSON.parse(e.postData.contents);
    var art    = String(d.art || 'kontakt').toLowerCase();
    var felder = Array.isArray(d.felder) ? d.felder : [];
    if (!felder.length) return antwort({ ok: false, fehler: 'keine Felder' });

    // Honeypot: echte Besucher füllen das Feld nie aus.
    if (d.honey) return antwort({ ok: true });

    var betreff = TITEL[art] || 'Anfrage über autohausdilltal.de';

    // 1) Erst protokollieren. Dieser Schritt ist die eigentliche Absicherung:
    //    Steht die Zeile in der Tabelle, kann die Anfrage nicht mehr verschwinden.
    var protokolliert = false;
    try { inTabelleSchreiben(art, felder); protokolliert = true; } catch (fehler) { /* Mail trotzdem versuchen */ }

    // 2) Dann die Mail.
    var anhaenge = [];
    (d.anhaenge || []).forEach(function (a) {
      try {
        anhaenge.push(Utilities.newBlob(Utilities.base64Decode(a.data), a.type || 'application/octet-stream', a.name || 'anhang'));
      } catch (fehler) {}
    });

    var optionen = {
      to:       EMPFAENGER,
      subject:  betreff,
      htmlBody: mailText(art, felder, d.fotosGesamt || 0, anhaenge.length),
      name:     'Autohaus Dilltal Website'
    };
    if (KOPIE) optionen.cc = KOPIE;
    var absender = adresseSuchen(felder);
    if (absender) optionen.replyTo = absender;
    if (anhaenge.length) optionen.attachments = anhaenge;

    MailApp.sendEmail(optionen);
    return antwort({ ok: true, protokolliert: protokolliert });

  } catch (fehler) {
    return antwort({ ok: false, fehler: String(fehler) });
  }
}

/* ---------------------------------------------------------------- Helfer */

function antwort(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function adresseSuchen(felder) {
  for (var i = 0; i < felder.length; i++) {
    var wert = String(felder[i][1] || '');
    if (wert.indexOf('@') > 0 && wert.indexOf('.') > 0 && wert.indexOf(' ') < 0) return wert;
  }
  return '';
}

function mailText(art, felder, fotosGesamt, anhaenge) {
  var zeilen = felder.map(function (f) {
    return '<tr><td style="padding:6px 14px 6px 0;color:#6E6A64;white-space:nowrap;vertical-align:top">' +
           escape_(f[0]) + '</td><td style="padding:6px 0;font-weight:600">' +
           escape_(f[1]).replace(/\n/g, '<br>') + '</td></tr>';
  }).join('');

  var hinweis = '';
  if (fotosGesamt > anhaenge) {
    hinweis = '<p style="color:#A8501A"><b>Hinweis:</b> Der Kunde hat ' + fotosGesamt +
              ' Foto(s) ausgewählt, davon sind ' + anhaenge +
              ' angehängt. Der Rest war zu groß – ggf. beim Kunden nachfragen.</p>';
  }

  return '<div style="font-family:system-ui,sans-serif;font-size:15px;color:#15202B">' +
         '<h2 style="margin:0 0 4px">' + escape_(TITEL[art] || 'Anfrage') + '</h2>' +
         '<p style="color:#6E6A64;margin:0 0 18px">Eingegangen am ' +
         Utilities.formatDate(new Date(), 'Europe/Berlin', 'dd.MM.yyyy \'um\' HH:mm') + ' Uhr</p>' +
         '<table style="border-collapse:collapse">' + zeilen + '</table>' + hinweis +
         '<p style="color:#95908A;font-size:13px;margin-top:22px">' +
         'Diese Mail kann direkt beantwortet werden – die Antwort geht an den Kunden.</p></div>';
}

function escape_(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function inTabelleSchreiben(art, felder) {
  var eigen = PropertiesService.getScriptProperties();
  var id    = eigen.getProperty('TABELLE_ID');
  var datei = null;

  if (id) { try { datei = SpreadsheetApp.openById(id); } catch (fehler) { datei = null; } }
  if (!datei) {
    datei = SpreadsheetApp.create(TABELLEN_NAME);
    eigen.setProperty('TABELLE_ID', datei.getId());
    datei.getActiveSheet().appendRow(['Zeitpunkt', 'Art', 'Anfrage']);
    datei.getActiveSheet().setFrozenRows(1);
  }

  var text = felder.map(function (f) { return f[0] + ': ' + f[1]; }).join('\n');
  datei.getSheets()[0].appendRow([
    Utilities.formatDate(new Date(), 'Europe/Berlin', 'dd.MM.yyyy HH:mm'), art, text
  ]);
}

/** Einmal von Hand ausführen, um die Zustellung zu prüfen. */
function testMail() {
  doPost({ postData: { contents: JSON.stringify({
    art: 'kontakt',
    felder: [['Name', 'Testlauf Relay'], ['E-Mail', 'nicoklein@nkzs.de'], ['Nachricht', 'Wenn diese Mail ankommt, funktioniert der Versand.']]
  }) } });
}
