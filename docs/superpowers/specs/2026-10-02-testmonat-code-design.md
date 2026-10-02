# Testmonat per Ambassador-Code — Entwurf

Stand 02.10.2026. Auftraggeber: „mach alles alleine" — Entscheidungen unten sind
im Gespräch gefallen (Zugang sofort, Tag 31 nur ansehen, voller Umfang,
öffentlicher TestFlight-Link) oder von mir gesetzt und so markiert.

## Ziel

Ein Salon, der einen Ambassador-Link öffnet, hat **sofort** einen eigenen Zugang
mit eigener Ablage und 30 Tagen babu in vollem Umfang — ohne Handgriff von Nina.
Ab Tag 31 kann er alles ansehen und herunterladen, aber nichts mehr erfassen oder
ändern, bis Nina ihn auf „gezeichnet" setzt (oder verlängert). Die Ambassadorin
sieht je Salon „testet (N Tage übrig)" / „Test abgelaufen".

## Befunde, die den Entwurf bestimmen

1. Eine eigene Ablage entsteht nur für eine `mandant`-Zeile (der Box-Anleger liest
   `mandant.status='box_ausstehend'`), und `mandant.kanzlei_id` ist Pflicht.
2. `POST /api/warteliste/einrichten` legt Salon-Konten mit `nutzer.box=1` und ohne
   Mandant an → `_hat_ablage`/`box_mitglied` lösen auf die **Default-Box** auf, also
   in die Ablage eines anderen Betriebs (dieselbe Fehlerart wie der Vorfall
   16.–27.09.). Bisher nie ausgelöst (keine Zeile `eingerichtet`).
3. Die App zeigt beim Buchen (`/api/buchung/einschaetzung`) den `fehler`-Text des
   Servers; ein Upload mit 403 wird als „keine Ablage" gewertet und nicht endlos
   wiederholt. Deshalb kommt der Testmonat **ohne App-Update** aus.
4. Der DATEV-Export ist schon heute nur für Kanzlei/Admin — ein Light-Modus mit
   Exportsperre würde bei Direktkunden nichts sperren. Darum voller Umfang.

## Entwurf

**Hauskanzlei „babu direkt".** Direktkunden (Code-Test und Ninas Warteliste) werden
Mandanten einer festen Kanzlei, angelegt beim ersten Bedarf
(`testmonat.direkt_kanzlei`). Inhaber ist `BABU_DIREKT_INHABER` (Konto, das die
Direktkunden im Kanzlei-Cockpit betreuen soll); ohne Variable ein Platzhalter
`babu-direkt` ohne Anmeldung — dann verwaltet nur die Verwaltung. Damit gelten
Trennung der Ablagen, Box-Anleger, Einladungsmail, Cockpit unverändert.

**Datenfeld.** `mandant.test_bis TEXT` (ISO-Datum, letzter Testtag). `NULL` = kein
Test (alle Kanzlei-Mandanten, Bestand, gezeichnete Salons). Inline in
`mandanten.schema` (SQLite, `ALTER` mit Fang) und als `migrations/0010_testmonat.sql`.

**Modul `testmonat.py`** (rein + kleine DB-Helfer):
- `TAGE = 30`, `stand(test_bis, heute) -> {bis, tage_uebrig, vorbei}`
- `starten(mandant_id, c, heute)`, `voll(mandant_id, c)`, `verlaengern(mandant_id, tage, c, heute)`
- `vorbei(mandant_id) -> bool` (für die Wache), `direkt_kanzlei(c) -> id`

**Einlösen** `POST /api/ambassador/einloesen {code, salon, email}` — öffentlich,
nur wenn `BABU_TESTMONAT=1` (sonst 404 und die Landing bleibt beim Wartelisten-Weg):
- Origin-Prüfung, IP-Bremse (30 s, wie Warteliste), Mail gültig, Salonname Pflicht.
- Code muss aktiv sein (sonst 404, gleiche Seite wie heute).
- Grenzen *(von mir gesetzt)*: je Code 5 Einlösungen am Tag
  (`BABU_TEST_JE_CODE_TAG`), insgesamt 20 neue Testmonate am Tag
  (`BABU_TEST_JE_TAG`) → 429 mit freundlichem Satz.
- Gibt es das Konto schon: dieselbe freundliche Antwort, kein neuer Test, Mail
  „du hast schon einen Zugang" (kein Konto-Orakel).
- Sonst: Konto (`box=False`, kein Passwort sichtbar) → Mandant unter „babu direkt"
  (SKR04) → `test_bis = heute + 29` (30 Kalendertage inkl. heute) →
  `ambassador_salon` (`testet`) → Willkommensmail mit Passwort-Link, Startguide,
  App-Weg (`BABU_TESTFLIGHT_LINK` gesetzt: öffentlicher Link; sonst der heutige
  Apple-ID-Absatz) → Kopie an `BABU_SUPPORT_MAIL` → Audit.

**Tag 31 — nur ansehen.** In `_box_wache`: aktiver Mandant mit abgelaufenem
`test_bis`, Methode nicht GET/HEAD/OPTIONS, Pfad nicht `/api/rueckmeldung…`,
Rolle nicht admin → **403** `{"fehler": "Dein Testmonat ist vorbei …",
"testmonat_vorbei": true}`. Lesen und Herunterladen bleiben; Termine/Team/Konto
(`_api_wache`) bleiben unberührt *(von mir gesetzt: nur Ablage, Belege, Kasse,
Zahlen werden gesperrt)*.

**Gezeichnet / Verlängern.** `POST /api/ambassador/meilenstein` mit `gezeichnet`
setzt zusätzlich `test_bis = NULL` für den Direkt-Mandanten dieser Adresse. Neu
`POST /api/ambassador/verlaengern {email, tage}` (Verwaltung, 1–60 Tage, Standard
14) setzt `test_bis = max(test_bis, heute) + tage`.

**Anzeigen.** `/api/ambassador/me` und `/liste` liefern je Salon `testmonat`
(`stand(...)` oder `null`). `/api/ich` liefert für Salon-Konten mit Test
`testmonat`. Portal: Ambassador-Tabelle zeigt „testet (N Tage übrig)" / „Test
abgelaufen"; Verwaltung zusätzlich „+14 Tage"; „Heute" zeigt einen Hinweis über
den Testmonat.

**Warteliste reparieren.** `einrichten` für `art=salon` legt das Konto mit
`box=False` an und dazu einen Mandanten unter „babu direkt" **ohne** Testmonat
(Pilot bleibt kostenlos). Antwort unverändert (Startpasswort einmal).

## Nicht im Umfang

Bezahlung/Abo, automatische Provision, App-Anzeige des Testmonats (nur
Server-Text), Light-Sperren, E-Mail-Erinnerungen vor Ablauf, Rechte von
Kanzlei-Konten in der Verwaltung (`darf_verwalten` lässt jede Kanzlei zu — eigener
Befund, eigene Aufgabe).

## Prüfung

Tests: Einlösen legt Konto+Mandant+Test an und schreibt NICHT in die Default-Box;
Schalter aus → 404; inaktiver Code → 404; Grenzen → 429; bestehendes Konto → keine
zweite Zeile; Tag 31: POST auf Beleg-Route 403 mit `testmonat_vorbei`, GET 200,
Rückmeldung erlaubt, Kanzlei-Mandant ohne Test unberührt; gezeichnet → wieder
offen; verlängern; `/api/ich`, `/me`, `/liste` liefern `testmonat`; Warteliste
`einrichten` → eigener Mandant, `_hat_ablage` erst mit Box; Schema-Gleichheit
inline/Migration; Routen-Fixture.
