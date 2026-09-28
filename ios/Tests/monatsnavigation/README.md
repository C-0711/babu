# Monatsnavigation Fix für Issue #85

## Problem
Nina konnte in der Dokumentenansicht nicht zwischen Monaten blättern, um zum Beispiel in den Januar zu springen.

## Ursache
Der Monatsname war nur ein Text-Element, kein interaktiver Button. Um vom aktuellen Monat (z.B. September) zu einem weit entfernten Monat (z.B. Januar) zu gelangen, musste Nina 8 Mal auf den linken Pfeil tippen. Das war mühsam und nicht intuitiv.

## Lösung
Der Monatsname ist jetzt ein Menu-Button, der beim Antippen alle verfügbaren Monate anzeigt. Nina kann jetzt:

1. **Direkt zu einem Monat springen**, indem sie auf den Monatsnamen tippt und aus der Liste wählt
2. **Weiterhin die Pfeile nutzen**, um schrittweise zu blättern (für benachbarte Monate)

Das Menu zeigt:
- Alle verfügbaren Monate in chronologischer Reihenfolge (neueste zuerst)
- Ein Häkchen beim aktuell ausgewählten Monat
- "Ohne Datum" als letzte Option, wenn es Belege ohne Datum gibt

## Änderungen
- `ios/Beleg/Beleg/ListeView.swift`: Monatsname von `Text` zu `Menu` geändert
- Der Menu enthält Buttons für jeden Monat in der `monate`-Liste
- Beim Antippen wird `gewaehlterMonat` gesetzt, was die View neu rendert

## Tests
- `main.swift`: Logik-Test für die Monatsnavigation
- `test_menu.swift`: Dokumentation der Menu-Funktionalität
- Build-Test erfolgreich: Die App kompiliert ohne Fehler
