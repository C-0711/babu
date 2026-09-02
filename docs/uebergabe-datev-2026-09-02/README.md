# Übergabe DATEV-Sitzung, 02.09.2026

Die Sitzung brach um 18:28 mitten im Planungsmodus ab. Dieser Ordner hält fest,
was aus dem Transkript gerettet wurde, damit die Planung ohne Neuanfang weitergeht.

## Was bereits auf main liegt (deployt, Suite 1608 grün)

- `ac0bf64` 19:45 — Buchungsstapel trägt beide Seiten (Kassenblätter als
  Tageseinnahmen, Geldtransit 1460, Kleinunternehmerin 4184); 183 Automatikkonten
  aus dem SKR04-PDF (`skr04_automatik.py`), kein BU-Schlüssel auf AV/AM-Konten.
- `39b14c6` 19:55 — Einlesen netto statt brutto, alte Historie-Stände werden aus
  den Originalen nachgelesen. Erster Fremdtest: Ninas Kanzlei-Stapel April 2026.
- `d163ac6` 20:11 — ganzer SKR04 2026 als `skr04_konten.py` (1.516 Konten) plus
  Test `test_skr04_konten.py`.

## Der offene Auftrag (18:15, `00-auftrag.md`)

1. SKR04-Konten komplett auslesen und als Embeddings im Kontext verfügbar machen.
2. Alle DATEV-Themen im Frontend und Backend hochladen, sortiert, in den Kontext
   (Chat und Buchungs-Prompt).
3. Pro-Zugang für Steuerberater, die im Backend hunderte Mandanten verwalten.
   Nachgeschoben: Postgres deployen falls nötig, alles in Docker.
4. 26 Portal-Befunde, Reihenfolge laut Auftrag: 1+2+3, dann 4, dann 6, dann 5,
   dann der Rest.

## Stand der Planung

- Drei Erkundungen sind fertig (`01`–`03`): Kompendium-Format samt harter
  Invariante (Zeilen in `atome.jsonl` == Zeilen in `vektoren.npy`, sonst schweigt
  das Kompendium), alle Ein-Box-Annahmen im Rollenmodell, Code-Stellen hinter den
  P0/P1-Befunden.
- Drei Planaufträge (`10`–`12`) waren gestartet, als die Sitzung abbrach. Ihre
  Ergebnisse existieren nicht. Nächster Schritt: die drei Aufträge erneut an
  Planungsagenten geben und daraus einen Gesamtplan bauen.

Die Erkundungen sind Agenten-Ausgaben mit Zeilennummern vom Stand `d163ac6`.
