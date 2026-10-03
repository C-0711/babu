"""Der Begleiter der Ambassadorin — was heute zu tun ist (seit 03.10.2026).

babu schaut nach jedem Salon, den sie eingeladen hat, und entscheidet, ob
heute eine Nachricht dran ist. Die Nachricht ist fertig formuliert; die
Ambassadorin tippt auf einen Knopf, WhatsApp öffnet sich auf IHREM Telefon
mit Nummer und Text (wa.me-Link). babu verschickt nichts selbst — das wäre
die WhatsApp-Business-Schnittstelle mit Metas Freischaltung, genehmigten
Vorlagen und Einwilligung der Empfängerin (Variante B, nicht gebaut).

Reine Regeln, keine Datenbank: `aufgabe(kontakt, heute)` bekommt den Stand
eines Kontakts und sagt, was zu tun ist. Die Reihenfolge der Prüfungen ist
die Wichtigkeit — wer kurz vor Testende steht, geht vor, wer noch nicht
angefangen hat, kommt zuletzt.

Grenzen (gegen Belästigung, Entscheidung 03.10.2026): höchstens eine
Nachricht alle drei Tage je Kontakt; in derselben Lage höchstens drei, für
„Test vorbei" und „Danke" nur eine. Eine neue Lage zählt neu.
"""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import quote

#: Die Lagen, in der Reihenfolge ihrer Wichtigkeit.
ARTEN = ("test_endet", "test_vorbei", "kein_beleg", "inaktiv",
         "nicht_gestartet", "danke")

ABSTAND_TAGE = 3
HOECHSTENS = {"test_vorbei": 1, "danke": 1}
HOECHSTENS_SONST = 3

#: Was auf dem Knopf steht — die Handlung, nicht der Kanal.
KNOEPFE = {
    "nicht_gestartet": "Erinnern",
    "kein_beleg": "Beim Start helfen",
    "inaktiv": "Hilfe anbieten",
    "test_endet": "Nachfragen",
    "test_vorbei": "Letzte Nachricht",
    "danke": "Danke sagen",
}

#: Die Nachrichten. Alltagssprache, kein Fachwort, Gruß mit ihrem Namen.
_TEXTE = {
    "einladung": ("Hallo {person}, ich mache meine Belege jetzt mit babu: Foto "
                  "machen, fertig. Probier es 30 Tage kostenlos aus, ohne "
                  "Vertrag: {link}\nLiebe Grüße, {ambassadorin}"),
    "nicht_gestartet": ("Hallo {person}, hast du meine Nachricht gesehen? Hier "
                        "geht es los, dauert zwei Minuten: {link}\nLiebe "
                        "Grüße, {ambassadorin}"),
    "kein_beleg": ("Hallo {person}, schön, dass du babu ausprobierst! "
                   "Fotografier einfach den nächsten Kassenbon mit der App, den "
                   "Rest macht babu. Soll ich es dir kurz zeigen?\nLiebe "
                   "Grüße, {ambassadorin}"),
    "inaktiv": ("Hallo {person}, alles gut bei dir? Seit ein paar Tagen sind "
                "keine Belege mehr reingekommen. Soll ich dir kurz zeigen, wie "
                "es am schnellsten geht?\nLiebe Grüße, {ambassadorin}"),
    "test_endet": ("Hallo {person}, wie läuft es mit babu? Dein Test läuft "
                   "noch {tage} Tage. Wenn du weitermachen willst, antworte "
                   "einfach mit Ja, dann kümmere ich mich darum.\nLiebe "
                   "Grüße, {ambassadorin}"),
    "test_vorbei": ("Hallo {person}, dein Test mit babu ist vorbei. Deine "
                    "Belege bleiben gespeichert. Wenn du weitermachen willst, "
                    "sag mir einfach Bescheid.\nLiebe Grüße, {ambassadorin}"),
    "danke": ("Hallo {person}, schön, dass du bei babu bleibst! Wenn du "
              "Fragen hast, schreib mir jederzeit.\nLiebe Grüße, {ambassadorin}"),
}

#: Mit Abo-Weg (seit 03.10.2026, `BABU_ABO=1`): der Salon schließt selbst ab —
#: die Nachricht trägt den Link zur Seite „Weitermachen" statt „sag mir Bescheid".
_TEXTE_MIT_WEG = {
    "test_endet": ("Hallo {person}, wie läuft es mit babu? Dein Test läuft "
                   "noch {tage} Tage. Wenn du weitermachen willst, geht das "
                   "hier in zwei Minuten: {weiter}\nLiebe Grüße, {ambassadorin}"),
    "test_vorbei": ("Hallo {person}, dein Test mit babu ist vorbei. Deine "
                    "Belege bleiben gespeichert. Weitermachen geht hier: "
                    "{weiter}\nLiebe Grüße, {ambassadorin}"),
}


# ---------------------------------------------------------------------------
# Handynummer und WhatsApp-Link
# ---------------------------------------------------------------------------

def nummer(roh: str | None) -> str | None:
    """Eine Handynummer international, nur Ziffern („491712345678").

    Deutsche Schreibweisen (0171 …, +49 …, 0049 …) werden zu 49…; eine
    führende 0 ohne Ländervorwahl gilt als deutsch. Was danach nicht 10 bis
    15 Ziffern hat, ist keine Nummer."""
    if not roh:
        return None
    s = str(roh).strip()
    plus = s.startswith("+")
    ziffern = re.sub(r"\D", "", s)
    if not plus:
        if ziffern.startswith("00"):
            ziffern = ziffern[2:]
        elif ziffern.startswith("0"):
            ziffern = "49" + ziffern[1:]
    if not 10 <= len(ziffern) <= 15:
        return None
    return ziffern


def anzeige(n: str) -> str:
    """Zum Lesen: +49 171 2345678 (deutsche Handynummern), sonst +<Ziffern>."""
    if n.startswith("49") and len(n) >= 11:
        return f"+49 {n[2:5]} {n[5:]}"
    return "+" + n


def whatsapp(roh_oder_nummer: str, text: str) -> str | None:
    """Der Link, der WhatsApp mit Nummer und Text öffnet — auf dem Telefon
    der Ambassadorin, gesendet wird von ihr."""
    n = nummer(roh_oder_nummer)
    if n is None:
        return None
    return f"https://wa.me/{n}?text={quote(text, safe='')}"


def nachricht(art: str, *, person: str, ambassadorin: str, link: str = "",
              tage: int | None = None, weiter: str | None = None) -> str:
    """Der Text für WhatsApp. `weiter`: Link zur Seite „Weitermachen" — dann
    sagen die Test-Lagen, wo der Salon selbst abschließt."""
    vorlage = (_TEXTE_MIT_WEG[art] if weiter and art in _TEXTE_MIT_WEG
               else _TEXTE[art])
    return vorlage.format(person=person or "du", ambassadorin=ambassadorin,
                          link=link, tage=tage if tage is not None else "",
                          weiter=weiter or "")


# ---------------------------------------------------------------------------
# Die Regeln
# ---------------------------------------------------------------------------

def _tage(von: dt.date | None, heute: dt.date) -> int | None:
    return None if von is None else (heute - von).days


def aufgabe(k: dict, heute: dt.date) -> dict | None:
    """Was ist heute für diesen Kontakt zu tun? `None`: nichts.

    `k` trägt: telefon, eingeladen_am, eingeloest_am, test (testmonat.stand
    oder None), meilenstein (None vor dem Einlösen, sonst testet/gezeichnet/
    gehalten), gezeichnet_am, belege, letzter_beleg, erinnert_am,
    erinnerungen, erinnert_art, weiter_am (Tag, an dem sie „will
    weitermachen" gemeldet hat).
    """
    if not k.get("telefon"):
        return None
    seit_erinnert = _tage(k.get("erinnert_am"), heute)
    if seit_erinnert is not None and seit_erinnert < ABSTAND_TAGE:
        return None
    art, grund = _lage(k, heute)
    if art is None:
        return None
    if k.get("erinnert_art") == art and \
            (k.get("erinnerungen") or 0) >= HOECHSTENS.get(art, HOECHSTENS_SONST):
        return None
    return {"art": art, "grund": grund, "knopf": KNOEPFE[art],
            "weitermachen": art in ("test_endet", "test_vorbei")}


def _lage(k: dict, heute: dt.date) -> tuple[str | None, str]:
    test = k.get("test")
    meilenstein = k.get("meilenstein")
    eingeloest = k.get("eingeloest_am") is not None
    testet = eingeloest and meilenstein == "testet"
    macht_mit = meilenstein in ("gezeichnet", "gehalten")
    belege = k.get("belege") or 0
    if k.get("weiter_am") and not macht_mit:
        return None, ""          # Nina ist dran — bis sie bucht, ist Ruhe.
    if testet and test and not test["vorbei"] and test["tage_uebrig"] <= 7:
        n = test["tage_uebrig"]
        return "test_endet", ("Heute ist der letzte Testtag" if n <= 1
                              else f"Test läuft noch {n} Tage")
    if testet and test and test["vorbei"]:
        return "test_vorbei", "Test ist vorbei"
    if eingeloest and (testet or macht_mit) and belege == 0 \
            and (_tage(k.get("eingeloest_am"), heute) or 0) >= 3:
        return "kein_beleg", "Noch kein Beleg hochgeladen"
    seit_beleg = _tage(k.get("letzter_beleg"), heute)
    if (testet or macht_mit) and belege > 0 and seit_beleg is not None \
            and seit_beleg >= 3:
        return "inaktiv", f"Seit {seit_beleg} Tagen kein Beleg"
    if not eingeloest:
        seit = _tage(k.get("eingeladen_am"), heute) or 0
        if seit >= 2:
            return "nicht_gestartet", f"Hat seit {seit} Tagen nicht angefangen"
        return None, ""
    if macht_mit and k.get("gezeichnet_am") is not None \
            and (_tage(k["gezeichnet_am"], heute) or 99) <= 7:
        return "danke", "Macht mit"
    return None, ""


def zaehlen(art_bisher: str | None, anzahl_bisher: int, art_neu: str) -> int:
    """Wie viele Nachrichten in dieser Lage, nachdem eine weitere raus ist."""
    return (anzahl_bisher or 0) + 1 if art_bisher == art_neu else 1


def aktiv_satz(eingeloest: bool, belege: int, letzter: dt.date | None,
               heute: dt.date) -> tuple[str, str]:
    """Ein Satz zur Aktivität und wie er wirkt (gut / warnung / neutral)."""
    if not eingeloest:
        return "Hat noch nicht angefangen", "neutral"
    if belege == 0:
        return "Noch kein Beleg", "neutral"
    seit = _tage(letzter, heute)
    if seit is not None and seit >= 3:
        return f"Seit {seit} Tagen kein Beleg", "warnung"
    wann = ("heute" if seit == 0 else "gestern" if seit == 1
            else f"am {letzter.strftime('%d.%m.')}" if letzter else "")
    wort = "Beleg" if belege == 1 else "Belege"
    return (f"{belege} {wort} hochgeladen, zuletzt {wann}" if wann
            else f"{belege} {wort} hochgeladen"), "gut"
