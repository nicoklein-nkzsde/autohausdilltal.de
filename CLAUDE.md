# Autohaus Dilltal
Website eines Gebrauchtwagenhaendlers in Eschenburg (Domain autohausdilltal.de, siehe CNAME).

## Aufbau
- index.html (~190 KB, alles inline; nur per Suche bearbeiten)
- data/cars.json: Fahrzeugbestand, wird automatisch ueberschrieben
- .github/workflows/sync-cars.yml: synchronisiert alle 6 h Fahrzeuge von mobile.de und committet cars.json (Handlauf mit dry_run moeglich)
- fonts/ lokal gehostet (Archivo, Inter), hero.mp4 Hero-Video, sitemap.xml, robots.txt

## Regeln
- cars.json nicht von Hand aendern, der Workflow ueberschreibt sie.
- Vor dem Push erst git pull, weil der Bot Commits macht.

## Konventionen
- Sprache: Deutsch. Keine Build-Schritte, Aenderungen direkt in der Datei testen (Doppelklick oder lokaler Server).
- Nur gezielt lesen: grosse Dateien per Suche/Zeilenbereich oeffnen, nicht komplett laden.
- Deployment: Push auf main, GitHub Pages.
