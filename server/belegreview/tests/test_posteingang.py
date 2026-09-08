"""Der Posteingang: nimmt er das Richtige an, weist er das Falsche ab?

Alles ohne Netz. Der SMTP-Handler bekommt `session` und `envelope`
durchgereicht und liest daran nur `peer`, `rcpt_tos` und `content` — die
Attrappen unten reichen dafür, und damit misst die Suite den eigenen Code
statt aiosmtpd. Ein einziger Test fährt zusätzlich einen echten
Controller auf 127.0.0.1 und schickt eine Mail hindurch; er wird
übersprungen, wenn `aiosmtpd` im venv fehlt (`pip install aiosmtpd`).

babu-web wird als Attrappe gestellt: dieser Dienst DARF nichts anderes tun
als HTTP zu rufen, und genau das wird hier festgenagelt. Ein Test, der
gegen ein laufendes babu-web liefe, könnte nicht zeigen, dass der
Mailserver die Belegbox nie selbst anfasst.

Die Routen auf der babu-web-Seite (`postadresse`, `/api/posteingang/…`)
stehen am Ende der Datei — sie sind die zweite Hälfte derselben Sache.
"""
import asyncio
import email.message
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER.parent.parent / "posteingang"))

import postadresse  # noqa: E402
import posteingang as pe  # noqa: E402

DOMAENE = "post.babu.0711.io"
LOKAL_A = "k7mq-3rtx-9wpd-2fhn"
LOKAL_B = "4bvc-8xnp-2kdq-7wsr"


# ---------------------------------------------------------------------------
# Attrappen
# ---------------------------------------------------------------------------

class BabuAttrappe(pe.Babu):
    """babu-web als Buch: was hätte der Dienst wohin geschickt?"""

    def __init__(self, adressen: dict[str, int], kaputt: bool = False):
        super().__init__(url="http://attrappe", pat="pat", token="tok")
        self.adressen = adressen
        self.kaputt = kaputt
        self.belege: list[tuple[int, str, bytes]] = []
        self.dokumente: list[tuple[int, str, bytes, str]] = []

    def aufloesen(self, lokal):
        if self.kaputt:
            raise pe.BabuFehler("babu-web nicht erreichbar")
        return self.adressen.get(lokal)

    def beleg(self, mandant_id, name, daten):
        self.belege.append((mandant_id, name, daten))
        return {"ok": True, "datei": f"docs/2026-09/{name}"}

    def dokument(self, mandant_id, name, daten, titel, art="post"):
        self.dokumente.append((mandant_id, name, daten, titel))
        return {"ok": True, "pfad": f"dokumente/2026-09/{name}"}


class Sitzung:
    def __init__(self, ip="203.0.113.7"):
        self.peer = (ip, 41234)


class Umschlag:
    def __init__(self, von="lieferant@example.org", inhalt=b""):
        self.mail_from = von
        self.rcpt_tos: list[str] = []
        self.content = inhalt


def _mail(betreff="Ihre Rechnung", text="Guten Tag,\n\nanbei die Rechnung.",
          anhaenge=(), von="Buchhaltung <rechnung@example.org>") -> bytes:
    m = email.message.EmailMessage()
    m["From"] = von
    m["To"] = f"{LOKAL_A}@{DOMAENE}"
    m["Subject"] = betreff
    m["Date"] = "Mon, 07 Sep 2026 09:12:00 +0200"
    m.set_content(text)
    for name, daten, haupt, unter in anhaenge:
        m.add_attachment(daten, maintype=haupt, subtype=unter, filename=name)
    return m.as_bytes()


def _handler(adressen=None, kaputt=False, **grenzen) -> pe.Posteingang:
    babu = BabuAttrappe(adressen if adressen is not None else {LOKAL_A: 2},
                        kaputt=kaputt)
    return pe.Posteingang(babu=babu, grenzen=pe.Grenzen(**grenzen),
                          domaene=DOMAENE)


def _rcpt(h: pe.Posteingang, adresse: str, umschlag=None, sitzung=None) -> str:
    umschlag = umschlag if umschlag is not None else Umschlag()
    return asyncio.run(h.handle_RCPT(None, sitzung or Sitzung(), umschlag,
                                     adresse, []))


def _zustellen(h: pe.Posteingang, rohdaten: bytes, adresse=None,
               sitzung=None) -> tuple[str, Umschlag]:
    """Der volle Weg: RCPT, dann DATA — so wie ein echter Absender es tut."""
    adresse = adresse or f"{LOKAL_A}@{DOMAENE}"
    sitzung = sitzung or Sitzung()
    umschlag = Umschlag(inhalt=rohdaten)
    antwort = asyncio.run(h.handle_RCPT(None, sitzung, umschlag, adresse, []))
    if not antwort.startswith("250"):
        return antwort, umschlag
    return asyncio.run(h.handle_DATA(None, sitzung, umschlag)), umschlag


# ---------------------------------------------------------------------------
# 1. Der gute Fall
# ---------------------------------------------------------------------------

def test_pdf_anhang_landet_ueber_die_api_im_richtigen_betrieb():
    h = _handler({LOKAL_A: 2})
    roh = _mail(anhaenge=[("rechnung.pdf", b"%PDF-1.4 test", "application", "pdf")])
    antwort, _ = _zustellen(h, roh)
    assert antwort.startswith("250")
    assert h.babu.belege == [(2, "rechnung.pdf", b"%PDF-1.4 test")]


def test_der_mailtext_wird_abgelegt_auch_ohne_anhang():
    """Der Text SELBST ist Schriftverkehr — eine Kündigung steht selten im
    Anhang. Absender, Betreff und Datum müssen darin stehen."""
    h = _handler({LOKAL_A: 2})
    antwort, _ = _zustellen(h, _mail(betreff="Kündigung zum 31.12.",
                                     text="Hiermit kündigen wir fristgerecht."))
    assert antwort.startswith("250")
    assert h.babu.belege == []
    assert len(h.babu.dokumente) == 1
    mandant_id, name, daten, titel = h.babu.dokumente[0]
    text = daten.decode()
    assert mandant_id == 2
    assert name.endswith(".txt")
    assert "Kündigung zum 31.12." in titel
    assert "rechnung@example.org" in text
    assert "Betreff: Kündigung zum 31.12." in text
    assert "07 Sep 2026" in text
    assert "Hiermit kündigen wir fristgerecht." in text


def test_das_protokoll_nennt_jeden_anhang():
    h = _handler({LOKAL_A: 2})
    roh = _mail(anhaenge=[("bon.jpg", b"\xff\xd8jpeg", "image", "jpeg"),
                          ("liste.exe", b"MZ binaer", "application",
                           "octet-stream")])
    _zustellen(h, roh)
    text = h.babu.dokumente[0][2].decode()
    assert "bon.jpg" in text
    assert "liste.exe" in text and ".exe" in text


def test_eine_mail_die_nur_aus_dem_pdf_besteht():
    """Manche Scanner und Faxdienste schicken einteilige Mail: kein Text,
    der Körper IST das PDF. `iter_attachments()` findet dort nichts."""
    m = email.message.EmailMessage()
    m["From"] = "scanner@example.org"
    m["To"] = f"{LOKAL_A}@{DOMAENE}"
    m["Subject"] = "Scan"
    m["Date"] = "Mon, 07 Sep 2026 09:12:00 +0200"
    m.set_content(b"%PDF-1.4 scan", maintype="application", subtype="pdf",
                  filename="scan.pdf", disposition="attachment")
    h = _handler({LOKAL_A: 2})
    antwort, _ = _zustellen(h, m.as_bytes())
    assert antwort.startswith("250")
    assert h.babu.belege == [(2, "scan.pdf", b"%PDF-1.4 scan")]


def test_unteradressierung_zeigt_auf_denselben_betrieb():
    h = _handler({LOKAL_A: 2})
    antwort, _ = _zustellen(h, _mail(), adresse=f"{LOKAL_A}+rechnung@{DOMAENE}")
    assert antwort.startswith("250")
    assert h.babu.dokumente[0][0] == 2


def test_grossschreibung_im_empfaenger_stoert_nicht():
    h = _handler({LOKAL_A: 2})
    assert _rcpt(h, f"{LOKAL_A.upper()}@{DOMAENE.upper()}").startswith("250")


# ---------------------------------------------------------------------------
# 2. Kein Relay
# ---------------------------------------------------------------------------

def test_unbekannte_adresse_wird_mit_550_abgewiesen_und_nichts_abgelegt():
    h = _handler({LOKAL_A: 2})
    antwort, umschlag = _zustellen(h, _mail(), adresse=f"{LOKAL_B}@{DOMAENE}")
    assert antwort.startswith("550")
    assert umschlag.rcpt_tos == []
    assert h.babu.belege == [] and h.babu.dokumente == []


def test_fremde_domaene_ist_kein_relay():
    """Der klassische offene Relay: Post an irgendwen weiterreichen. Hier
    fällt sie schon an der Domäne, ohne dass babu-web gefragt wird."""
    h = _handler({LOKAL_A: 2})
    assert _rcpt(h, f"{LOKAL_A}@example.com").startswith("550")
    assert _rcpt(h, "opfer@fremde-firma.de").startswith("550")


def test_ein_name_statt_eines_zufallsworts_kommt_nicht_durch():
    h = _handler({LOKAL_A: 2})
    assert _rcpt(h, f"nina@{DOMAENE}").startswith("550")


def test_stillgelegte_adresse_wird_abgewiesen():
    """`postadresse.aufloesen` findet nur aktive Zeilen — die Attrappe
    bildet das ab, indem sie die Adresse nicht mehr kennt."""
    h = _handler({})
    assert _rcpt(h, f"{LOKAL_A}@{DOMAENE}").startswith("550")


def test_handle_data_ohne_rcpt_legt_nichts_ab():
    """Wer den Umschlag von Hand füllt, umgeht die Prüfung nicht."""
    h = _handler({LOKAL_A: 2})
    umschlag = Umschlag(inhalt=_mail())
    umschlag.rcpt_tos.append(f"{LOKAL_B}@{DOMAENE}")
    antwort = asyncio.run(h.handle_DATA(None, Sitzung(), umschlag))
    assert antwort.startswith("250")
    assert h.babu.belege == [] and h.babu.dokumente == []


# ---------------------------------------------------------------------------
# 3. Zwei Betriebe
# ---------------------------------------------------------------------------

def test_zwei_betriebe_bekommen_nie_die_post_des_anderen():
    h = _handler({LOKAL_A: 2, LOKAL_B: 19})
    _zustellen(h, _mail(betreff="für A",
                        anhaenge=[("a.pdf", b"%PDF a", "application", "pdf")]),
               adresse=f"{LOKAL_A}@{DOMAENE}")
    _zustellen(h, _mail(betreff="für B",
                        anhaenge=[("b.pdf", b"%PDF b", "application", "pdf")]),
               adresse=f"{LOKAL_B}@{DOMAENE}")
    assert h.babu.belege == [(2, "a.pdf", b"%PDF a"), (19, "b.pdf", b"%PDF b")]
    assert [z[0] for z in h.babu.dokumente] == [2, 19]
    # Und keine Zeile des einen Betriebs trägt Inhalt des anderen.
    fuer_a = [d for d in h.babu.dokumente if d[0] == 2][0][2].decode()
    assert "für A" in fuer_a and "für B" not in fuer_a


# ---------------------------------------------------------------------------
# 4. Grenzen
# ---------------------------------------------------------------------------

def test_zu_grosse_sendung_wird_abgewiesen():
    h = _handler({LOKAL_A: 2}, sendung_max=2000)
    roh = _mail(anhaenge=[("gross.pdf", b"x" * 5000, "application", "pdf")])
    antwort, _ = _zustellen(h, roh)
    assert antwort.startswith("552")
    assert h.babu.belege == [] and h.babu.dokumente == []


def test_zu_grosser_anhang_wird_verworfen_und_benannt():
    """Die Sendung darf durch — sie kann Text tragen, der zählt. Nur der
    Anhang bleibt draußen, und der Mailtext sagt warum."""
    h = _handler({LOKAL_A: 2}, anhang_max=1024)
    roh = _mail(anhaenge=[("klein.pdf", b"%PDF klein", "application", "pdf"),
                          ("gross.pdf", b"x" * 4096, "application", "pdf")])
    antwort, _ = _zustellen(h, roh)
    assert antwort.startswith("250")
    assert [n for _, n, _ in h.babu.belege] == ["klein.pdf"]
    assert "gross.pdf" in h.babu.dokumente[0][2].decode()


def test_exe_anhang_wird_benannt_und_verworfen():
    h = _handler({LOKAL_A: 2})
    roh = _mail(anhaenge=[("rechnung.exe", b"MZ\x90\x00", "application",
                           "octet-stream")])
    antwort, _ = _zustellen(h, roh)
    assert antwort.startswith("250")
    assert h.babu.belege == [], "eine .exe darf nie in die Belegbox"
    text = h.babu.dokumente[0][2].decode()
    assert "Nicht übernommen" in text and "rechnung.exe" in text


def test_zu_viele_anhaenge_werden_gedeckelt():
    h = _handler({LOKAL_A: 2}, anhaenge_max=2)
    roh = _mail(anhaenge=[(f"b{i}.pdf", b"%PDF", "application", "pdf")
                          for i in range(5)])
    _zustellen(h, roh)
    assert len(h.babu.belege) == 2
    assert "b4.pdf" in h.babu.dokumente[0][2].decode()


def test_zu_viele_empfaenger_werden_abgewiesen():
    h = _handler({LOKAL_A: 2, LOKAL_B: 19}, empfaenger_max=1)
    umschlag = Umschlag()
    assert _rcpt(h, f"{LOKAL_A}@{DOMAENE}", umschlag).startswith("250")
    assert _rcpt(h, f"{LOKAL_B}@{DOMAENE}", umschlag).startswith("452")


def test_ein_pfad_im_anhangsnamen_wird_unschaedlich():
    h = _handler({LOKAL_A: 2})
    roh = _mail(anhaenge=[("../../etc/passwd.pdf", b"%PDF", "application", "pdf")])
    _zustellen(h, roh)
    assert h.babu.belege[0][1] == "passwd.pdf"


# ---------------------------------------------------------------------------
# 5. Rate-Limit
# ---------------------------------------------------------------------------

def test_rate_limit_je_ip_greift():
    h = _handler({LOKAL_A: 2, LOKAL_B: 19}, rate_ip=3)
    sitzung = Sitzung("198.51.100.5")
    for _ in range(3):
        assert _rcpt(h, f"{LOKAL_A}@{DOMAENE}", sitzung=sitzung).startswith("250")
    vierter = _rcpt(h, f"{LOKAL_B}@{DOMAENE}", sitzung=sitzung)
    assert vierter.startswith("451"), "4xx, nicht 5xx — die Mail soll wiederkommen"
    # Eine andere IP hat ihr eigenes Kontingent.
    assert _rcpt(h, f"{LOKAL_A}@{DOMAENE}",
                 sitzung=Sitzung("198.51.100.6")).startswith("250")


def test_rate_limit_je_adresse_greift_ueber_ips_hinweg():
    """Ein Botnetz kommt aus vielen IPs — die Adresse hat ihr eigenes Maß."""
    h = _handler({LOKAL_A: 2}, rate_adresse=2)
    for i in range(2):
        assert _rcpt(h, f"{LOKAL_A}@{DOMAENE}",
                     sitzung=Sitzung(f"198.51.100.{i}")).startswith("250")
    assert _rcpt(h, f"{LOKAL_A}@{DOMAENE}",
                 sitzung=Sitzung("198.51.100.99")).startswith("451")


def test_rate_fenster_laeuft_ab():
    r = pe.Rate(hoechstens=2, fenster=60)
    assert r.erlaubt("x", jetzt=1000.0)
    assert r.erlaubt("x", jetzt=1001.0)
    assert not r.erlaubt("x", jetzt=1002.0)
    assert r.erlaubt("x", jetzt=1100.0), "nach dem Fenster wieder frei"


# ---------------------------------------------------------------------------
# 6. Wenn babu-web nicht da ist
# ---------------------------------------------------------------------------

def test_babu_weg_gibt_4xx_und_nicht_550():
    """Der Unterschied, an dem echte Post hängt: ein 550 wäre endgültig."""
    h = _handler({LOKAL_A: 2}, kaputt=True)
    antwort = _rcpt(h, f"{LOKAL_A}@{DOMAENE}")
    assert antwort.startswith("4"), antwort


def test_fehler_beim_ablegen_gibt_4xx():
    h = _handler({LOKAL_A: 2})

    def kaputt(*_a, **_k):
        raise pe.BabuFehler("500 vom Portal")

    h.babu.beleg = kaputt
    antwort, _ = _zustellen(
        h, _mail(anhaenge=[("r.pdf", b"%PDF", "application", "pdf")]))
    assert antwort.startswith("4"), antwort


# ---------------------------------------------------------------------------
# 7. Der volle Weg über einen echten SMTP-Server
# ---------------------------------------------------------------------------

def _freier_port() -> int:
    """aiosmtpd 1.4.6 kann Port 0 nicht — es verbindet sich nach dem Start
    selbst auf die angegebene Nummer, und die ist dann noch 0. Also vorher
    einen freien holen."""
    import socket  # noqa: PLC0415

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_echter_smtp_server_nimmt_die_mail_an():
    pytest.importorskip("aiosmtpd", reason="pip install aiosmtpd")
    import smtplib  # noqa: PLC0415

    h = _handler({LOKAL_A: 2})
    c = pe.controller(h, host="127.0.0.1", port=_freier_port())
    c.start()
    try:
        with smtplib.SMTP(c.hostname, c.port, timeout=10) as s:
            with pytest.raises(smtplib.SMTPRecipientsRefused):
                s.sendmail("wer@example.org", [f"{LOKAL_B}@{DOMAENE}"], _mail())
            s.sendmail("wer@example.org", [f"{LOKAL_A}@{DOMAENE}"],
                       _mail(anhaenge=[("r.pdf", b"%PDF echt", "application",
                                        "pdf")]))
    finally:
        c.stop()
    assert h.babu.belege == [(2, "r.pdf", b"%PDF echt")]
    assert len(h.babu.dokumente) == 1


# ---------------------------------------------------------------------------
# 8. Die Adressen in babu-web
# ---------------------------------------------------------------------------

def test_zufallswort_ist_nicht_erratbar():
    woerter = {postadresse.neues_lokal() for _ in range(200)}
    assert len(woerter) == 200, "zweimal dasselbe Wort in 200 Versuchen"
    for wort in woerter:
        assert postadresse.LOKAL_RE.match(wort), wort
        assert len(wort.replace("-", "")) == 16
        # Keine verwechselbaren Zeichen — die Adresse wird abgetippt.
        assert not set(wort) & set("ilo01")


def test_normieren_schneidet_domaene_und_zusatz_weg():
    assert postadresse.normieren(f"{LOKAL_A}@{DOMAENE}") == LOKAL_A
    assert postadresse.normieren(f"{LOKAL_A}+rechnung@{DOMAENE}") == LOKAL_A
    assert postadresse.normieren(LOKAL_A.upper()) == LOKAL_A
    assert postadresse.normieren("nina") == "nina"
    assert postadresse.normieren("") == ""
    assert postadresse.normieren("../etc") == ""
    assert postadresse.normieren("a") == ""


def _mandant(c, name="SupremeStudio", un="nina@example.org") -> int:
    import mandanten  # noqa: PLC0415
    c.execute("INSERT INTO nutzer (email, name, salon, rolle, pw, aktiv, "
              "angelegt, box) VALUES (?,?,?,?,?,1,?,1)",
              (un, name, name, "salon", "x", "2026-09-07"))
    kanzlei_id = mandanten.kanzlei_anlegen("Kanzlei Afflek", "afflek@0711.io", c=c)
    return mandanten.mandant_anlegen(kanzlei_id, name, un, c=c)


def test_adresse_loest_auf_den_richtigen_betrieb_auf(tmp_path):
    import babu_web as bw  # noqa: PLC0415
    bw.PORTAL_DB = tmp_path / "portal.db"
    with bw._DB_LOCK, bw._db() as c:
        eins = _mandant(c, "SupremeStudio", "nina@example.org")
        zwei = _mandant(c, "Jenny from the Block", "jenny@example.org")
        a = postadresse.anlegen(eins, c=c)
        b = postadresse.anlegen(zwei, c=c)
        assert postadresse.aufloesen(a, c=c) == eins
        assert postadresse.aufloesen(b, c=c) == zwei
        assert postadresse.aufloesen(f"{a}@{DOMAENE}", c=c) == eins
        assert postadresse.aufloesen("gibt-es-nicht", c=c) is None


def test_stillgelegte_adresse_loest_nicht_mehr_auf(tmp_path):
    import babu_web as bw  # noqa: PLC0415
    bw.PORTAL_DB = tmp_path / "portal.db"
    with bw._DB_LOCK, bw._db() as c:
        eins = _mandant(c)
        a = postadresse.anlegen(eins, c=c)
        assert postadresse.stilllegen(a, eins, c=c) is True
        assert postadresse.aufloesen(a, c=c) is None
        # Zweimal stilllegen ist kein Erfolg mehr, aber auch kein Schaden.
        assert postadresse.stilllegen(a, eins, c=c) is False


def test_ein_fremder_betrieb_kann_keine_adresse_stilllegen(tmp_path):
    import babu_web as bw  # noqa: PLC0415
    bw.PORTAL_DB = tmp_path / "portal.db"
    with bw._DB_LOCK, bw._db() as c:
        eins = _mandant(c, "SupremeStudio", "nina@example.org")
        zwei = _mandant(c, "Jenny from the Block", "jenny@example.org")
        a = postadresse.anlegen(eins, c=c)
        assert postadresse.stilllegen(a, zwei, c=c) is False
        assert postadresse.aufloesen(a, c=c) == eins


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    """Eine Kanzlei mit zwei Mandanten, plus eine fremde Kanzlei.

    Dieselbe Bauart wie in `test_kanzlei_routen.welt`, nur ohne Boxen — die
    Adressverwaltung fasst keine Belegbox an.
    """
    import babu_web as bw  # noqa: PLC0415
    import mandanten  # noqa: PLC0415

    monkeypatch.setattr(bw, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(bw, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    for mail, rolle in (("kanzlei-a@0711.io", "kanzlei"),
                        ("kanzlei-b@0711.io", "kanzlei"),
                        ("betreiber@0711.io", "admin"),
                        ("nina@0711.io", "salon"),
                        ("fremd@0711.io", "salon")):
        bw.nutzer_anlegen(mail, mail.split("@")[0], "", rolle)
    with bw._DB_LOCK, bw._db() as c:
        a = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei-a@0711.io", c=c)
        b = mandanten.kanzlei_anlegen("Kanzlei Nord", "kanzlei-b@0711.io", c=c)
        nina = mandanten.mandant_anlegen(a, "SupremeStudio", "nina@0711.io", c=c)
        fremd = mandanten.mandant_anlegen(b, "Salon Fremd", "fremd@0711.io", c=c)
    wer = {"un": "kanzlei-a@0711.io"}
    monkeypatch.setattr(bw, "angemeldet", lambda request: wer["un"])
    monkeypatch.setattr(bw, "_origin_ok", lambda request: True)
    return {"wer": wer, "nina": nina, "fremd": fremd}


@pytest.fixture()
def k(welt):  # noqa: ARG001
    from fastapi.testclient import TestClient  # noqa: PLC0415

    import babu_web as bw  # noqa: PLC0415
    return TestClient(bw.app, base_url="https://testserver")


def test_die_kanzlei_legt_eine_adresse_an_und_sieht_sie_wieder(welt, k):
    antwort = k.post(f"/api/posteingang/adresse/{welt['nina']}")
    assert antwort.status_code == 200
    lokal = antwort.json()["lokal"]
    assert antwort.json()["adresse"].startswith(lokal + "@")
    assert postadresse.LOKAL_RE.match(lokal)

    liste = k.get(f"/api/posteingang/adresse/{welt['nina']}").json()["adressen"]
    assert [z["lokal"] for z in liste] == [lokal]
    assert liste[0]["aktiv"] is True

    assert k.post(f"/api/posteingang/adresse/{welt['nina']}/stilllegen",
                  json={"lokal": lokal}).status_code == 200
    liste = k.get(f"/api/posteingang/adresse/{welt['nina']}").json()["adressen"]
    assert liste[0]["aktiv"] is False


def test_eine_fremde_kanzlei_kommt_an_die_adresse_nicht_heran(welt, k):
    """Die Adresse IST der Zugang zur Belegbox — wer sie lesen darf, darf
    Post hineinschicken."""
    welt["wer"]["un"] = "kanzlei-b@0711.io"
    assert k.get(f"/api/posteingang/adresse/{welt['nina']}").status_code == 403
    assert k.post(f"/api/posteingang/adresse/{welt['nina']}").status_code == 403
    assert k.post(f"/api/posteingang/adresse/{welt['nina']}/stilllegen",
                  json={"lokal": "egal-egal-egal"}).status_code == 403


def test_ein_salon_zugang_verwaltet_keine_adressen(welt, k):
    welt["wer"]["un"] = "nina@0711.io"
    assert k.get(f"/api/posteingang/adresse/{welt['nina']}").status_code == 403


def test_der_lokale_teil_ist_nicht_waehlbar(welt, k):
    """Ein Wunschname (`nina@…`) hätte die Nichterratbarkeit abgeschafft —
    die Route nimmt deshalb gar keinen Körper entgegen."""
    lokal = k.post(f"/api/posteingang/adresse/{welt['nina']}",
                   json={"lokal": "nina"}).json()["lokal"]
    assert lokal != "nina"


def test_mehr_als_fuenf_adressen_gibt_es_nicht(welt, k):
    import posteingang_routen as pr  # noqa: PLC0415

    for _ in range(pr.ADRESSEN_MAX):
        assert k.post(f"/api/posteingang/adresse/{welt['nina']}").status_code == 200
    assert k.post(f"/api/posteingang/adresse/{welt['nina']}").status_code == 409


def test_aufloesen_braucht_das_dienst_geheimnis(tmp_path, monkeypatch):
    """Die Route ist der einzige Weg, aus einer Adresse einen Betrieb zu
    machen — ohne Geheimnis wäre sie ein offenes Adressverzeichnis."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    import babu_web as bw  # noqa: PLC0415
    bw.PORTAL_DB = tmp_path / "portal.db"
    with bw._DB_LOCK, bw._db() as c:
        eins = _mandant(c)
        a = postadresse.anlegen(eins, c=c)

    klient = TestClient(bw.app)
    monkeypatch.delenv("BABU_POSTEINGANG_TOKEN", raising=False)
    assert klient.get("/api/posteingang/aufloesen",
                      params={"lokal": a}).status_code == 403

    monkeypatch.setenv("BABU_POSTEINGANG_TOKEN", "geheim")
    assert klient.get("/api/posteingang/aufloesen", params={"lokal": a},
                      headers={"X-Posteingang-Token": "falsch"}).status_code == 403
    antwort = klient.get("/api/posteingang/aufloesen", params={"lokal": a},
                         headers={"X-Posteingang-Token": "geheim"})
    assert antwort.status_code == 200
    assert antwort.json() == {"mandant_id": eins}
    assert klient.get("/api/posteingang/aufloesen", params={"lokal": "nix"},
                      headers={"X-Posteingang-Token": "geheim"}).status_code == 404
