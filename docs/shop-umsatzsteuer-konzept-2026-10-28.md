# babu für Shops — Umsatzsteueranmeldung für Shopify, Magento & Co.

Stand 28.10.2026. Alles auf den Ist-Zustand des Codes gemessen
(3289 Tests grün, App seit heute im App Store).

---

## 1. Ist-Zustand: Was babu heute ist (gemessen)

| Baustein | Stand |
|---|---|
| App | **Im App Store** (seit 28.10., 19 Länder; DE/EU wartet auf DSA-Trader-Verifizierung), TestFlight läuft parallel |
| Kern | Foto/PDF → Lesung → Gemma bucht (37 Kategorien, SKR04) → Belegbox (Git-Repo, versiegelt) |
| Branchen | Friseur, Barber (de/tr), Werkstatt — je eigenes Portal + Kompendium |
| Monatsabschluss | Umsatzsteuer-**Vorschau** (ustva als Bericht im Portal), BWA, „Bleibt dir" |
| Zahlungen | Kassenabgleich: **Salonkee, SumUp, Zettle, Stripe, Payone, Adyen, Mollie, Treatwell, Planity** … (`ERLOES_QUELLEN`) aus Kontoauszügen |
| Kanzlei | DATEV-Export (EXTF v12, 124 Spalten) mit Prüfbefund + Siegel; Kanzlei-Portal (Afflek, GKM) |
| Abo | Stripe live: Solo 39 / Salon 79 / Plus 149 €/Monat (netto) |
| Vertrieb | Ambassador-Programm (Codes, Provision 2×25 %), Warteliste, Apple-ID-Flow |
| Posteingang | Dienst gebaut (Mail → `POST /api/aufnahme`), **MX noch nicht in Betrieb** |
| ELSTER/CTAX | Im 0711-Verbund: CTAX (Rechenwerk, ELSTER-XSD-Validierung „Einz≠Sum", bmf-api :12015 als Rechenautorität) — **noch nicht mit babu verbunden** |

**Ehrliche Einordnung:** babu ist heute eine *Beleg- und Buchhaltungszentrale
für Service-Betriebe mit Steuervorschau* — die Anmeldung selbst macht die
Kanzlei aus dem DATEV-Stapel. Ein Shop-Bezug existiert im Code noch nicht
(gemessen: kein „Shopify/Magento" im Repository).

---

## 2. Warum ausgerechnet babu für Shops passt

Shops (Shopify, Magento, WooCommerce, Shopware) haben dasselbe Problem wie
Ninas Salon — nur in größerer Zahl und ohne Kassenzettel:

1. **Massenhaft Belege:** Lieferantenrechnungen (Ware, Versand, Ads,
   Software) kommen per **Mail** — der Posteingang-Dienst ist dafür gebaut.
2. **Ausgangsrechnungen:** die Bestellungs-Rechnungen stammen vom Shop
   selbst — die **Aussteller-Erkennung** (eigene Steuernummer oben =
   Ausgangsrechnung → Erlöskonto) funktioniert unverändert.
3. **Zahlungsströme:** Shopify Payments, PayPal, Klarna, Stripe schütten
   Payouts aufs Konto — exakt das Muster von `ERLOES_QUELLEN` (Stripe und
   Adyen und Payone und Mollie stehen **schon drin**). Was fehlt, sind
   Shop-namens-Varianten, keine neue Mechanik.
4. **Umsatzsteuer:** die USt-**Vorschau** existiert (Erlöse je Satz,
   Vorsteuer aus Belegen, Doppelzählungs-Abgleich). Shops brauchen genau
   das, plus Steuersätze aus Bestelldaten (19/7/0, reverse charge, OSS).

babu brächte also nicht „noch ein Buchhaltungstool", sondern die eine
Kette, die im Shop-Markt fehlt: **Bestellung → Beleg → gebucht → Vorschau
→ Kanzlei/ELSTER — mit Beleg-Beweis in der eigenen Box.**

---

## 3. Das Konzept in drei Ebenen

```
  Shopify / Magento / WooCommerce          Zahlungs-Dienste
  (Bestellungen, Rechnungen,              (Payouts, Gebühren,
   Gutschriften, Refunds)                  Refund-Ausgleich)
        │  REST-API, Webhooks                    │  CSV/API
        ▼                                        ▼
  ┌─────────────────────────────────────────────────────┐
  │  SHOP-CONNECTOR (neu, eigener kleiner Dienst)       │
  │  · Bestellungen → Ausgangsrechnung-Zeilen (Satz,   │
  │    Land, reverse charge)                            │
  │  · Payout-Berichte → auszuege/<monat>/umsaetze     │
  │  · Refunds → Gutschrift-Buchungen                  │
  │  · Rechnungs-PDFs vom Shop → Belegbox (Lesung)      │
  └───────────────────────┬─────────────────────────────┘
                          ▼
  ┌─────────────────────────────────────────────────────┐
  │  babu (besteht heute schon)                         │
  │  · Belegbox + Gemma-Buchung (Lieferanten-Belege)    │
  │  · Monatsabschluss: Erlöse je Steuersatz,           │
  │    Vorsteuer, Kassen-/Konto-Abgleich                │
  │  · USt-Vorschau je Monat/Quartal                    │
  └───────────────────────┬─────────────────────────────┘
                          ▼
     Weg A: DATEV-Stapel → Kanzlei (besteht, läu    ) │
     Weg B: ELSTER-Anmeldung über 0711-CTAX/bmf-api   │
           (Bausteine existieren, Verbindung fehlt)   │
```

### Ebene 1 — Connector (das Einzige wirklich Neue)

Ein kleiner Dienst je Plattform (Vorbild: `box-anleger.sh`-Cron-Prinzip,
kein Code im babu-web-Kern):

- **Shopify:** Admin-API (orders, refunds, payouts via
  `shopify_payments`), Webhooks auf `orders/paid`. Auth per Shop-Token.
- **Magento/WooCommerce:** REST, deutlich seltener SaaS — hier reicht
  oft der **CSV-Import** (Bestellungen + Rechnungen als PDF-Stapel).
- Ausgabe in die **bestehenden** babu-Strukturen: `auszuege/<monat>/
  *.umsaetze.json` für Payouts, `POST /api/aufnahme` (ergebnisJson mit
  dokumentklasse ausgangsrechnung) für Shop-Rechnungen, normale Lesung
  für Lieferanten-PDFs aus dem Posteingang.

### Ebene 2 — Buchhaltung & Vorschau (besteht, muss Shop-Fragen lernen)

- Gemma-Katalog um Shop-Kategorien erweitern („Wareneingang",
  „Versandkosten", „Werbeanzeigen", „Shop-Software", „Payment-Gebühren")
  — dieselbe Kompendium-Struktur wie Friseur/Barber/Werkstatt, also ein
  vierter Ordner `kompendium-shop` plus Portal `shop`.
- Steuersatz je Bestellung statt aus dem Beleg: der Connector liefert
  ihn mit (Shopify kennt 19/7/0, EU-Reverse-Charge, OSS-Länder).
  Die USt-Vorschau gruppiert danach — die Doppelzählungs-Abgleich-Regel
  (Rechnung ≠ Payout) existiert bereits.

### Ebene 3 — Die Anmeldung selbst (zwei Wege, bewusst)

- **Weg A (heute real): DATEV-Stapel an die Kanzlei.** Für jeden Shop,
  der einen Steuerberater hat — das ist der babu-Hebel: Kanzleien sind
  schon der Vertriebskanal (Afflek, GKM).
- **Weg B (möglich, muss gebaut werden): ELSTER direkt.** 0711 besitzt
  CTAX mit ELSTER-XSD-Validierung und die bmf-api als Rechenautorität.
  babu liefert die Beleg-Basis, CTAX rechnet und validiert („Einz≠Sum"),
  die Anmeldung geht als UStVA (und später Umsatzsteuererklärung,
  ggf. OSS-Zusammenfassung) ans Finanzamt. **Klarniveau:** alles vor
  dem Versand bleibt babu; der ELSTER-Versand ist eine eigene
  Freigabe-Instanz mit Prüfbericht.

---

## 4. Was fehlt (ehrlich, geordnet nach Aufwand)

| # | Baustein | Aufwand | Bemerkung |
|---|---|---|---|
| 1 | `ERLOES_QUELLEN` um Shopify Payments, PayPal, Klarna ergänzen | ~Stunden | nur Wörter |
| 2 | Shop-Kompendium + Portal (4. Branche) | Tage | Kopie des Musters |
| 3 | CSV-Import für Bestellungen + Rechnungen | Tage | ohne API auskommen |
| 4 | Shopify-Connector (API/Webhooks) | 1–2 Wochen | erster echter Connector |
| 5 | Posteingang in Betrieb (MX, Port 25, rDNS) | Betriebssache | Shop-Rechnungen kommen per Mail |
| 6 | Steuersatz/OSS-Logik in der USt-Vorschau | ~1 Woche | 19/7/0 + reverse charge; OSS als eigener Schritt |
| 7 | ELSTER-Versand über CTAX | Wochen | eigenes Tor mit Freigabe + Prüfbericht; CTAX-Sicherheitsstopp beachten |

## 5. Positionierung (warum nicht Lexoffice/sevDesk/Taxdoo noch eins)

- **Gegen Taxdoo/amavat (OSS-Automaten):** die konsumieren Shop-Daten und
  rechnen — babu hält zusätzlich den **Beleg-Beweis** je Buchung in der
  eigenen Box (GitChain-Verlässlichkeit), und die Kanzlei bleibt im Spiel
  (DATEV-Weg) oder geht über 0711-ELSTER. „Jede Zahl nachlesbar" ist das
  Verkaufsargument an Kanzleien.
- **Gegen Lexoffice/sevDesk (SMB-Buchhaltung):** die sind Formular-Kästen;
  babu ist **beleg-autonom** (Lesung + Buchung passiert ohne Tipparbeit)
  und branchen-fokussiert — Shops als vierte Branche neben Friseur,
  Barber, Werkstatt passt genau auf das Portal-Muster.
- **Preis** bleibt im Abo-Raster (39/79/149) — Shop-Plus-Paket für
  Bestellvolumen > X wäre ehrlich, sobald Ebene 2 steht.

## 6. Vertrieb über die vorhandenen Hebel

1. **Shopify-Agenturen als Ambassadorinnen** — eine Agentur mit 40
   Shop-Kunden ist der perfekte Code-Inhaber; Provision läuft über das
   bestehende Programm (2×25 %) unverändert weiter.
2. **Kanzleien (Weg A):** jede Kanzlei mit Shop-Mandanten bekommt sofort
   Wert:DATEV-Stapel aus Bestellungen statt Beleg-Chaos.
3. **Der App-Store-Eintrag** macht den ersten Klick frei (sobald DE live).

## 7. Empfohlener erster Schritt (Pilot statt Plattform)

Ein einziger echter Shop (am besten ein Shopify-Shop einer Kanzlei aus
dem Pilot-Umfeld), handschriftlich verbunden: Bestellungen als CSV in
`auszuege/`, Shop-Rechnungen als PDF in die Belegbox, Lieferanten-Mail
in den Posteingang. Dann ist der Monatsabschluss mit USt-Vorschau der
erste Shop-Beweis — und jedes Bauteil danach (Connector, OSS, ELSTER)
baut auf gemessenem Boden, nicht auf Vermutung.
