"""Das babu-Mail-Design (maildesign.py): eine Funktion, alle Mails.

Gemessen wird beides: die HTML-Fassung trägt die Handschrift der Startseite
(warmes Papier, Serifen-Überschrift, Beige #857b61, kein Nachladen), und die
Textfassung steht Wort für Wort drin — schlichte Clients und Spam-Filter
sehen dieselben Wörter wie vorher.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import maildesign  # noqa: E402

WARTELISTE = ("Hallo,\n\n"
              "jemand möchte einen Zugang zu babu:\n\n"
              "    Salon / Betrieb\n"
              "    salon@example.org\n"
              "    Name: Erika\n"
              "    Betrieb: Probe-Salon\n"
              "\nEinladen: Portal → Verwaltung → Warteliste → „Zugang einladen“.\n")

EINLADUNG = ("Hallo Maria,\n\n"
             "dein Steuerbüro hat für „SupremeStudio“ einen Zugang zu babu "
             "eingerichtet. Beim ersten Öffnen legst du dein Passwort fest:\n\n"
             "    https://babu.0711.io/portal#reset/abc123\n"
             "\nDer Link gilt 3 Tage und nur einmal.\n")


def _textteil(m) -> str:
    return m.get_payload(0).get_content()


def _htmlteil(m) -> str:
    return m.get_payload(1).get_content()


def test_beide_fassungen_da():
    m = maildesign.mail("nina@0711.io", "Warteliste: Salon — salon@example.org",
                        WARTELISTE, von="babu <post@babu.0711.io>")
    assert m.is_multipart()
    assert _textteil(m) == WARTELISTE
    assert "text/html" in _htmlteil(m) or "<html" in _htmlteil(m).lower()


def test_design_traegt_die_handschrift_der_startseite():
    h = _htmlteil(maildesign.mail("nina@0711.io", "Betreff", WARTELISTE,
                                  von="babu <post@babu.0711.io>"))
    # Warmes Papier als Kartenhintergrund, Beige als Signalfarbe, Serifen-
    # Überschrift — die Palette aus index.html :root.
    assert "#faf9f5" in h and "#857b61" in h and "Georgia" in h
    # Bilder nur von der EIGENEN Wurzel (mybabu.io/bilder/…), nie von
    # Dritten — und jedes mit Alternativtext und fixer Größe: ohne Bild
    # springt das Layout nicht und der Sinn bleibt.
    for src in re.findall(r"src='([^']+)'", h):
        assert src.startswith("https://mybabu.io/bilder/"), src
    assert "<img" in h                      # das Hero-Bild ist immer da
    assert h.count("<img") == h.count("alt=")  # jedes Bild hat Alternativtext
    assert "width=" in h and "height=" in h
    # Keine Webfonts, kein Stylesheet, kein Skript von irgendwo.
    for verboten in ("fonts.googleapis", "@import", "url(", "<script",
                     "src='http:", "src='//"):
        assert verboten not in h, verboten


def test_link_wird_zum_knopf_mit_url_daneben():
    h = _htmlteil(maildesign.mail("maria@example.org", "Dein Zugang", EINLADUNG,
                                  von="babu <post@babu.0711.io>"))
    assert "Jetzt öffnen ›" in h            # der Knopf
    assert "babu.0711.io/portal#reset/abc123" in h  # die URL bleibt sichtbar
    assert h.count("href=") >= 1


def test_eingerueckter_block_wird_zur_karte():
    h = _htmlteil(maildesign.mail("nina@0711.io", "Warteliste", WARTELISTE,
                                  von="babu <post@babu.0711.io>"))
    assert "#f0ebe3" in h                   # die Beige-Karte
    assert "Salon / Betrieb" in h and "Probe-Salon" in h


def test_grusszeile_nennt_den_vornamen():
    h = _htmlteil(maildesign.mail("maria@example.org", "Dein Zugang", EINLADUNG,
                                  von="babu <post@babu.0711.io>"))
    assert "Für Maria" in h


def test_fuss_ist_stets_da():
    h = _htmlteil(maildesign.mail("x@example.org", "B", "Hallo,\n\nkurz.\n",
                                  von="babu <post@babu.0711.io>"))
    assert "mybabu.io" in h
    assert "ersetzt keine individuelle Steuerberatung" in h


def test_postfach_baut_die_design_mail():
    """postfach._nachricht nimmt den Weg über maildesign — die .eml im
    Postausgang trägt beide Fassungen."""
    import postfach
    m = postfach._nachricht("nina@0711.io", "Betreff", WARTELISTE)
    assert m.is_multipart()
    assert m["From"] == postfach.ABSENDER
    assert _textteil(m) == WARTELISTE


def test_startguide_steht_in_der_einladung():
    """Der Guide liefert die Schritte als eingerückten Block — das Maildesign
    macht daraus die Kreis-Ziffern-Liste, der Text bleibt Wort für Wort."""
    import startguide
    text = ("Hallo Maria,\n\n"
            "dein Steuerbüro hat für „SupremeStudio“ einen Zugang zu babu "
            "eingerichtet. Beim ersten Öffnen legst du dein Passwort fest:\n\n"
            "    https://babu.0711.io/portal#reset/abc123\n\n"
            + startguide.schritte("https://babu.0711.io")
            + "\nDer Link gilt 3 Tage und nur einmal.\n")
    h = _htmlteil(maildesign.mail("maria@example.org", "Dein Zugang zu babu",
                                  text, von="babu <post@babu.0711.io>"))
    # Vier Schritte, Kreis-Ziffern, in den Worten des Guides.
    assert "Passwort zweimal eingeben" in h
    assert "Ein paar kurze Fragen zu deinem Salon" in h
    assert "grüner" in h
    assert h.count("border-radius:50%") >= 4
    # Die Kanzlei-Variante kennt keinen Salon-Step.
    k = startguide.schritte("https://babu.0711.io", art="kanzlei")
    assert "Betriebe deiner Kanzlei" in k and "Salon" not in k
    hk = _htmlteil(maildesign.mail(
        "j@kanzlei.de", "Zugang", "Hallo,\n\n    " + k.strip() + "\n",
        von="babu <post@babu.0711.io>"))
    assert "Betriebe deiner Kanzlei" in hk
