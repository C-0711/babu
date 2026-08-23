"""Die Vertragsmaschine muss von der Oberfläche aus erreichbar sein.

`POST /api/arbeitsvertrag/entwurf` baut aus Eckdaten einen vollständigen
Arbeitsvertrag und verweigert ihn unter Mindestlohn — geprüft in
`test_arbeitsvertrag.py`. Nur rief den Weg niemand auf: das Portal holte die
Arten, den Entwurf holte nichts. Eine Maschine, die keine Oberfläche
bedient, ist für Nina nicht vorhanden.

Zweiter Punkt, und der wiegt schwerer als die Verdrahtung: die Vorlagen sind
NICHT von einem Fachanwalt geprüft. Das gehört dorthin, wo jemand einen
Vertrag erzeugt — nicht ins Kleingedruckte.
"""
import re
from pathlib import Path

PORTAL_DATEI = Path(__file__).resolve().parent.parent / "portal.html"
PORTAL = PORTAL_DATEI.read_text()


def _sichtbar(text: str) -> str:
    """Nur das, was die Nutzerin am Bildschirm zu sehen bekommt.

    Kommentare zählen nicht — ein Hinweis, der nur im Quelltext steht, ist
    kein Hinweis.
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _personalbereich() -> str:
    stueck = PORTAL.split('<section class="ansicht" id="a-personal">')
    assert len(stueck) == 2, "der Personalbereich fehlt"
    return stueck[1].split("</section>")[0]


# ————— Der Weg dorthin —————

def test_das_portal_ruft_den_vertragsentwurf_ueberhaupt_ab():
    assert "/api/arbeitsvertrag/entwurf" in PORTAL, \
        "die Vertragsmaschine wird von keiner Oberfläche aufgerufen"


def test_ein_knopf_im_personalbereich_fuehrt_zum_entwurf():
    aufrufe = set(re.findall(r'onclick="(\w+)\(\)"', _personalbereich()))
    assert "vertragEntwurf" in aufrufe, \
        f"kein Knopf für den Vertragsentwurf, nur: {sorted(aufrufe)}"


def test_die_funktion_hinter_dem_knopf_gibt_es():
    assert re.search(r"async function vertragEntwurf\s*\(", PORTAL)


def test_der_entwurf_nimmt_die_eckdaten_aus_dem_formular():
    """Nina hat die Angaben schon eingetippt — ein zweites Formular für
    dieselben Zahlen wäre eine Zumutung."""
    block = PORTAL.split("async function vertragEntwurf")[1].split("\nasync function ")[0]
    for feld in ("pn-art", "pn-eintritt", "pn-stunden", "pn-entgelt"):
        assert feld in block, f"„{feld}“ wird nicht mitgeschickt"


def test_der_name_der_arbeitnehmerin_steht_im_entwurf():
    """Sonst steht im Vertragskopf „— Arbeitnehmerin —“."""
    block = PORTAL.split("async function vertragEntwurf")[1].split("\nasync function ")[0]
    assert "arbeitnehmerin" in block


def test_eine_abgelehnte_angabe_wird_im_klartext_gezeigt():
    """Die Maschine antwortet mit einem ganzen Satz („Der Mindestlohn liegt
    2026 bei 13,90 €") — der muss ankommen, nicht ein blankes „ging nicht"."""
    block = PORTAL.split("async function vertragEntwurf")[1].split("\nasync function ")[0]
    assert "fehler" in block


# ————— Was dabeistehen muss —————

UNGEPRUEFT = "kein Fachanwalt geprüft"


def test_die_vorlage_ist_sichtbar_als_ungeprueft_gekennzeichnet():
    assert UNGEPRUEFT in _sichtbar(PORTAL), \
        "nirgends steht, dass die Vorlagen anwaltlich ungeprüft sind"


def test_der_hinweis_steht_dort_wo_der_vertrag_entsteht():
    """Nicht im Kleingedruckten und nicht auf einer anderen Seite — im
    Personalbereich, neben dem Knopf."""
    assert UNGEPRUEFT in _sichtbar(_personalbereich())


def test_der_hinweis_steht_auch_am_fertigen_entwurf():
    """Wer den Vertrag vor sich hat, verschickt ihn als Nächstes."""
    block = PORTAL.split("function vertragKarte")[1].split("\nasync function ")[0]
    assert UNGEPRUEFT in _sichtbar(block)
