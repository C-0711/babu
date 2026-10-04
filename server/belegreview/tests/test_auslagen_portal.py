"""Portal: Auslagen-Ansicht, Heute-Karte, Team-Schalter (babu Expenses D1)."""
import re
from pathlib import Path

PORTAL = (Path(__file__).resolve().parent.parent / "portal.html").read_text()


def test_die_ansicht_ist_verdrahtet():
    assert '<section class="ansicht" id="a-auslagen">' in PORTAL
    assert re.search(r"auslagen:\s*ladeAuslagen", PORTAL)
    assert "menuGeh('#auslagen')" in PORTAL


def test_nur_nummern_im_onclick():
    for teil in re.findall(r'onclick="(auslage\w+|erstattung\w+)\(([^)]*)\)"', PORTAL):
        assert re.fullmatch(r"\$\{[in]\}|'(ueberweisung|bar)'|\$\{i\}, this\.checked", teil[1]), teil


def test_team_schalter_und_heute_karte():
    assert "teamRecht(${p.id}, 'darf_auslagen', this.checked)" in PORTAL
    assert "darf_auslagen: p.darf_auslagen" in PORTAL
    assert 'api("/api/auslagen?stand=offen")' in PORTAL
