"""Provision der Ambassadorinnen — gebucht, sobald der Salon bezahlt (seit 03.10.2026).

Regel des Auftraggebers (03.10.2026): je 25 % von zwölf Netto-Monatspreisen,
einmal bei der ERSTEN bezahlten Rechnung („gezeichnet") und noch einmal bei
der DRITTEN („gehalten"). 25 % × 12 = 3 Monatspreise, also ganze Euro:

    Solo 39 €  → 117 €     Salon 79 € → 237 €     Salon Plus 149 € → 447 €

Gebucht wird über `buchen()` — vom Stripe-Ereignis UND vom Handweg der
Verwaltung, damit beide dieselbe Regel haben. Doppelt gebucht wird nie:
`ambassador_buchung` trägt einen eindeutigen Schlüssel (code, email,
meilenstein), und nur wenn die Zeile wirklich neu ist, wächst das Guthaben.
Das hält auch, wenn der tägliche Lauf (zweiter Prozess) dasselbe Ereignis
noch einmal einspielt.

Selbstwerbung zählt nicht: wer mit dem eigenen Code den eigenen Salon
anmeldet, bekommt dafür keine Provision.
"""
from __future__ import annotations

import abo

ANTEIL_PROZENT = 25
MONATE = 12

#: Welche bezahlte Monatsrechnung welchen Meilenstein auslöst.
MEILENSTEIN_MONAT = {1: "gezeichnet", 3: "gehalten"}

#: Was vorher stehen muss, damit ein Meilenstein gebucht werden kann.
VORHER = {"gezeichnet": "testet", "gehalten": "gezeichnet"}


def betrag(paket: str | None) -> int:
    """Provision je Meilenstein in ganzen Euro (netto)."""
    p = abo.PAKETE.get(paket or "")
    if not p:
        return 0
    return p["netto_cent"] * MONATE * ANTEIL_PROZENT // (100 * 100)


def meilenstein_fuer(monat_nr: int | None) -> str | None:
    return MEILENSTEIN_MONAT.get(monat_nr or 0)


def ust_cent(netto_cent: int, steuerstatus: str | None) -> int:
    """Umsatzsteuer auf eine Gutschrift — nur bei umsatzsteuerpflichtigen
    Ambassadorinnen (`ust`); Kleinunternehmerin und Privatperson: 0."""
    if steuerstatus != "ust":
        return 0
    return (netto_cent * abo.UST_PROZENT + 50) // 100


def ambassadorin_von(email: str, c) -> dict | None:
    """Über welchen Code kam dieser Salon? Bei mehreren zählt der erste."""
    z = c.execute("SELECT s.code, s.meilenstein, s.salon, a.email "
                  "FROM ambassador_salon s JOIN ambassador a ON a.code = s.code "
                  "WHERE s.email=? ORDER BY s.eingelöst, s.code", (email,)).fetchone()
    if not z:
        return None
    return {"code": z[0], "meilenstein": z[1], "salon": z[2], "email": z[3]}


def buchen(c, *, email: str, meilenstein: str, betrag_eur: int, paket: str | None,
           quelle: str, heute: str, code: str | None = None,
           rechnung: str | None = None) -> dict:
    """Einen Meilenstein buchen. Rückgabe `{ok, grund, code, betrag}`.

    `grund` bei `ok=False`: keine_ambassadorin, selbst, stand (der Salon steht
    nicht auf dem Vor-Meilenstein), schon_gebucht. Ruft NICHT audit und nimmt
    KEIN Schloss — der Aufrufer hält `_DB_LOCK` und schreibt danach ins Log.
    """
    if code:
        z = c.execute("SELECT s.code, s.meilenstein, s.salon, a.email "
                      "FROM ambassador_salon s JOIN ambassador a ON a.code = s.code "
                      "WHERE s.code=? AND s.email=?", (code, email)).fetchone()
        amb = ({"code": z[0], "meilenstein": z[1], "salon": z[2], "email": z[3]}
               if z else None)
    else:
        amb = ambassadorin_von(email, c)
    if amb is None:
        return {"ok": False, "grund": "keine_ambassadorin", "code": None, "betrag": 0}
    if (amb["email"] or "").strip().lower() == email.strip().lower():
        return {"ok": False, "grund": "selbst", "code": amb["code"], "betrag": 0}
    if amb["meilenstein"] != VORHER[meilenstein]:
        grund = ("schon_gebucht" if amb["meilenstein"] in (meilenstein, "gehalten")
                 else "stand")
        return {"ok": False, "grund": grund, "code": amb["code"], "betrag": 0,
                "stand": amb["meilenstein"]}
    neu = c.execute(
        """INSERT INTO ambassador_buchung
           (code, email, salon, meilenstein, betrag, datum, stripe_rechnung,
            quelle, paket)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT (code, email, meilenstein) DO NOTHING""",
        (amb["code"], email, amb["salon"], meilenstein, betrag_eur, heute,
         rechnung, quelle, paket)).rowcount
    if neu != 1:
        return {"ok": False, "grund": "schon_gebucht", "code": amb["code"], "betrag": 0}
    # Addiert, nicht gesetzt: bis 03.10.2026 überschrieb „gehalten" hier den
    # Betrag von „gezeichnet" — die Salonzeile zeigte 237 statt 474 €.
    c.execute(f"""UPDATE ambassador_salon SET meilenstein=?,
                  verdienst = COALESCE(verdienst, 0) + ?, {meilenstein}_am=?
                  WHERE code=? AND email=?""",
              (meilenstein, betrag_eur, heute, amb["code"], email))
    c.execute("UPDATE ambassador SET verdient = verdient + ? WHERE code=?",
              (betrag_eur, amb["code"]))
    return {"ok": True, "grund": None, "code": amb["code"], "betrag": betrag_eur}


def stornieren(c, *, email: str, meilenstein: str, heute: str,
               rechnung: str | None = None) -> dict:
    """Eine gebuchte Provision zurücknehmen (Rücklastschrift, Erstattung).

    Einmal je Meilenstein: eine Gegenbuchung `storno_<meilenstein>` mit
    negativem Betrag. Sie wird mit späteren Auszahlungen verrechnet; der
    Meilenstein des Salons bleibt als Verlauf stehen."""
    z = c.execute("SELECT code, salon, betrag, paket FROM ambassador_buchung "
                  "WHERE email=? AND meilenstein=?", (email, meilenstein)).fetchone()
    if not z:
        return {"ok": False, "grund": "nicht_gebucht", "code": None, "betrag": 0}
    code, salon, betrag_eur, paket = z
    neu = c.execute(
        """INSERT INTO ambassador_buchung
           (code, email, salon, meilenstein, betrag, datum, stripe_rechnung,
            quelle, paket)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT (code, email, meilenstein) DO NOTHING""",
        (code, email, salon, f"storno_{meilenstein}", -int(betrag_eur), heute,
         rechnung, "stripe", paket)).rowcount
    if neu != 1:
        return {"ok": False, "grund": "schon_storniert", "code": code, "betrag": 0}
    c.execute("UPDATE ambassador_salon SET verdienst = COALESCE(verdienst, 0) - ? "
              "WHERE code=? AND email=?", (int(betrag_eur), code, email))
    c.execute("UPDATE ambassador SET verdient = verdient - ? WHERE code=?",
              (int(betrag_eur), code))
    return {"ok": True, "grund": None, "code": code, "betrag": -int(betrag_eur)}
