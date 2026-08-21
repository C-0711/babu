"""Das Fallwissen des Chats: alles, was babu über diesen Salon weiß.

Der Chat sah bisher nur Belege und schnitt bei 12.000 Zeichen ab. Je voller
die Box, desto weniger passte hinein — und was fehlte, merkte niemand.
Jetzt wird AUSGEWÄHLT statt abgeschnitten: was zur Frage passt, kommt rein.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wissen  # noqa: E402


def beleg(lieferant="dm Drogerie", brutto=26.0, monat="2026-08", **kw):
    grund = {"stamm": "s-" + lieferant[:4], "lieferant": lieferant, "brutto": brutto,
             "netto": brutto / 1.19, "ust": brutto - brutto / 1.19, "monat": monat,
             "datum": "05.08.2026", "belegart": "Verbrauchsmaterial",
             "konto_skr04": "6850", "status": "geprüft", "offen": []}
    grund.update(kw)
    return grund


WELT = {
    "einstellungen": {"betrieb_name": "Salon Nina", "rechtsform": "Einzelunternehmen",
                      "kleinunternehmer": "Nein", "finanzamt": "Stuttgart",
                      "versteuerung": "ist"},
    "belege": [beleg(), beleg("Friseur Großhandel Wagner", 141.0)],
    "kassenblaetter": [{"datum": "2026-08-17", "einnahmenBar": 412.5,
                        "ecZahlungen": 388.0}],
    "vertraege": [{"art_name": "Mietvertrag", "partner": "Hausverwaltung Sonnenberg",
                   "betrag_monat": 1250.0, "laufzeit_bis": "2026-12-31",
                   "kuendigungsfrist": "3 Monate zum Quartalsende"}],
    "rechnungen": [{"nummer": "2026-0001", "empfaenger": {"name": "Jana Allgaier"},
                    "brutto": 535.5, "datum": "2026-08-21", "bezahlt_am": None}],
    "team": [{"name": "Jana", "kosten_monat": 2400.0, "aktiv": True}],
    "fristen": [{"art": "ustva", "name": "Umsatzsteuer August 2026",
                 "faellig": "2026-09-10"}],
    "dokumente": [{"titel": "Bescheid Finanzamt", "art": "behoerde",
                   "erklaerung": {"einfach": "Du musst nichts tun.",
                                  "bis_wann": None}}],
}


# ————— Was überhaupt drinsteht —————

def test_der_betrieb_ist_immer_dabei():
    """Wer babu fragt, bekommt Antworten für SEINEN Salon — der Rahmen gilt immer."""
    text = wissen.kontext("Was habe ich für Ware ausgegeben?", WELT)
    assert "Salon Nina" in text
    assert "Einzelunternehmen" in text


def test_belege_kommen_bei_einer_belegfrage():
    text = wissen.kontext("Was habe ich bei dm gekauft?", WELT)
    assert "dm Drogerie" in text


def test_vertraege_kommen_bei_einer_vertragsfrage():
    text = wissen.kontext("Was zahle ich für die Miete?", WELT)
    assert "Sonnenberg" in text
    assert "1250" in text.replace(".", "").replace(",", "")


def test_kasse_kommt_bei_einer_umsatzfrage():
    text = wissen.kontext("Wie lief der Umsatz diesen Monat?", WELT)
    assert "412" in text.replace(",", ".") or "800" in text.replace(",", ".")


def test_rechnungen_kommen_bei_einer_rechnungsfrage():
    text = wissen.kontext("Wer schuldet mir noch Geld?", WELT)
    assert "Jana Allgaier" in text
    assert "2026-0001" in text


def test_fristen_kommen_bei_einer_terminfrage():
    text = wissen.kontext("Wann muss ich die Umsatzsteuer abgeben?", WELT)
    assert "10.09.2026" in text or "2026-09-10" in text


def test_team_kommt_bei_einer_personalfrage():
    text = wissen.kontext("Was kostet mich mein Personal?", WELT)
    assert "Jana" in text


def test_post_kommt_bei_einer_amtsfrage():
    text = wissen.kontext("Was wollte das Finanzamt von mir?", WELT)
    assert "Bescheid" in text


# ————— Auswählen statt abschneiden —————

def test_das_budget_wird_eingehalten():
    viele = {**WELT, "belege": [beleg(f"Laden {i}", 10.0 + i) for i in range(400)]}
    text = wissen.kontext("Was habe ich ausgegeben?", viele, budget=4000)
    assert len(text) <= 4000


def test_bei_platzmangel_gewinnt_das_passende():
    """Eine Vertragsfrage darf nicht von 400 Belegen verdrängt werden."""
    viele = {**WELT, "belege": [beleg(f"Laden {i}", 10.0 + i) for i in range(400)]}
    text = wissen.kontext("Wann kann ich den Mietvertrag kündigen?", viele,
                          budget=2500)
    assert "Sonnenberg" in text


def test_ohne_daten_kein_erfundener_kontext():
    leer = {"einstellungen": {}, "belege": [], "kassenblaetter": [], "vertraege": [],
            "rechnungen": [], "team": [], "fristen": [], "dokumente": []}
    text = wissen.kontext("Was habe ich ausgegeben?", leer)
    assert "noch nichts" in text.lower() or text.strip() == "" or len(text) < 400


def test_allgemeine_frage_bekommt_trotzdem_den_rahmen():
    """„Was ist die Kleinunternehmerregelung?" — keine Belegfrage, aber die
    Antwort hängt davon ab, ob SIE Kleinunternehmerin ist."""
    text = wissen.kontext("Was ist die Kleinunternehmerregelung?", WELT)
    assert "Kleinunternehmer" in text


# ————— Themen erkennen —————

def test_themen_werden_erkannt():
    assert "vertrag" in wissen.themen("Wann kann ich die Versicherung kündigen?")
    assert "rechnung" in wissen.themen("Hat Jana ihre Rechnung bezahlt?")
    assert "kasse" in wissen.themen("Wie viel Umsatz hatte ich gestern?")
    assert "team" in wissen.themen("Was kostet meine Angestellte?")
    assert "frist" in wissen.themen("Wann ist die Voranmeldung fällig?")
    assert "beleg" in wissen.themen("Wo ist die Quittung vom Großhandel?")


def test_frage_ohne_thema_ist_kein_fehler():
    """„Wie werde ich meine Chefin los" — babu muss trotzdem antworten können."""
    assert isinstance(wissen.themen("Mir wächst alles über den Kopf"), set)


def test_alltagsfrage_gilt_nicht_als_belegfrage():
    """Nicht jede Frage ist eine Steuerfrage — der Chat soll auch beraten."""
    t = wissen.themen("Wie sage ich einer Kundin ab, ohne sie zu verlieren?")
    assert "beleg" not in t and "frist" not in t
