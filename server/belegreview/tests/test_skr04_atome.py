"""SKR04-Kontenatome fürs Kompendium — Text-Schema, Idempotenz, Invariante.

Läuft ohne Embedding-Dienst: `embed` ist injizierbar, hier immer eine
Fake-Funktion. Kein echtes `~/kompendium` wird angefasst — jedes Beispiel
baut sich sein eigenes tmp-Kompendium, im Stil von `tests/test_kompendium.py`.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER.parents[2] / "werkzeuge" / "kompendium"))

import skr04_atome_bauen as sb  # noqa: E402


def _fake_embed(dim: int = 4):
    """Deterministischer Fake-Vektor je Text — kein Netz, kein Modell."""
    def embed(text: str):
        h = abs(hash(text))
        vektor = [((h >> (8 * i)) % 97) / 97.0 + 0.1 for i in range(dim)]
        return {"modell": "fake", "dim": dim, "vektor": vektor}
    return embed


@pytest.fixture()
def leeres_kompendium(tmp_path):
    """Noch kein atome.jsonl/vektoren.npy — der allererste Bau-Lauf."""
    return tmp_path


@pytest.fixture()
def mini_kompendium(tmp_path):
    """Ein bestehendes Kompendium mit ein paar branchenfremden Atomen,
    genau wie es auf dem Host schon läuft — skr04_atome_bauen darf sie
    nicht anfassen."""
    atome = [
        {"id": 0, "quelle": "afa.pdf", "loc": "S1#0", "text": "Nutzungsdauer 10 Jahre"},
        {"id": 1, "quelle": "ustg.md", "loc": "txt#3", "text": "Kleinunternehmer"},
    ]
    with open(tmp_path / "atome.jsonl", "w", encoding="utf-8") as f:
        for a in atome:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    vektoren = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    np.save(tmp_path / "vektoren.npy", vektoren)
    return tmp_path


# ── Atom-Text: Aussage- UND Frageform ─────────────────────────────────────

def test_reines_konto_hat_aussage_und_frageform():
    text = sb.konto_atom_text("0135", "EDV-Software")
    assert "Konto 0135 im SKR04-Kontenrahmen: EDV-Software." in text
    assert "Kontenklasse 0" in text
    assert "Frage: Was ist Konto 0135? Antwort: EDV-Software." in text
    # Ohne verknüpfte babu-Kategorie keine "Welches Konto für …"-Frage.
    assert "Welches Konto für" not in text


def test_konto_mit_kategorie_beantwortet_auch_die_umgekehrte_frage():
    import kontierung as kt
    bewirtung = kt.KATEGORIEN["bewirtung"]
    text = sb.konto_atom_text("6640", "Bewirtung", kategorien=[bewirtung])
    assert "Frage: Was ist Konto 6640? Antwort: Bewirtung." in text
    assert "Frage: Welches Konto für Bewirtung? Antwort: Konto 6640 (Bewirtung)." in text
    assert "In babu die Kategorie „Bewirtung“" in text
    assert "SKR03-Pendant: Konto 4650." in text


def test_zwei_kategorien_auf_demselben_konto_gehen_beide_nicht_verloren():
    # verbrauchsmaterial UND materialeinsatz zeigen beide auf SKR04 5100 —
    # ein {konto: kategorie}-Dict würde eine der beiden Fragen verschlucken.
    import kontierung as kt
    kategorien = [kt.KATEGORIEN["verbrauchsmaterial"], kt.KATEGORIEN["materialeinsatz"]]
    text = sb.konto_atom_text("5100", "Verbrauchsmaterial Salon", kategorien=kategorien)
    assert "Welches Konto für Verbrauchsmaterial Salon?" in text
    assert "Welches Konto für Materialeinsatz am Kunden?" in text


def test_automatik_atom_hat_aussage_und_frageform():
    text = sb.automatik_atom_text("4300", "Erlöse 7 % USt", ("AM", 7, "Erlöse 7 % USt"))
    assert "Steuerautomatik" in text
    assert "Automatik Umsatzsteuer (AM), 7 %." in text
    assert "Frage: Hat Konto 4300 eine Steuerautomatik? Antwort: Ja" in text
    assert "Frage: Braucht Konto 4300 einen Steuerschlüssel beim Buchen? " \
        "Antwort: Nein" in text


def test_automatik_ohne_festen_satz():
    text = sb.automatik_atom_text("4100", "Steuerfreie Umsätze",
                                  ("AM", None, "Steuerfreie Umsätze"))
    assert "steuerfrei oder Sonderfall ohne festen Satz" in text


# ── Die vollständige Kandidatenmenge ──────────────────────────────────────

def test_kandidaten_decken_alle_konten_und_automatikkonten_ab():
    import skr04_automatik as sa
    import skr04_konten as sk
    kandidaten = sb.neue_atome_bauen()
    konten = [a for a in kandidaten if a["quelle"] == "skr04-konten"]
    automatik = [a for a in kandidaten if a["quelle"] == "skr04-automatik"]
    assert len(konten) == len(sk.KONTEN)
    assert len(automatik) == len(sa.AUTOMATIK)
    assert {a["quelle"] for a in kandidaten} == {"skr04-konten", "skr04-automatik"}
    # loc ist "Konto {nr}" — exakt wie im Planauftrag verlangt.
    assert all(a["loc"].startswith("Konto ") for a in kandidaten)


# ── Bau-Lauf: Invariante, L2-Norm, Idempotenz, --probe ────────────────────

def test_probe_schreibt_nichts(leeres_kompendium):
    ergebnis = sb.bauen(leeres_kompendium, probe=True, embed=_fake_embed())
    assert ergebnis["neu"] > 0
    assert not (leeres_kompendium / "atome.jsonl").exists()
    assert not (leeres_kompendium / "vektoren.npy").exists()


def test_bau_erhaelt_bestehende_atome_und_erfuellt_die_invariante(mini_kompendium):
    ergebnis = sb.bauen(mini_kompendium, embed=_fake_embed())
    assert ergebnis["geschrieben"]
    assert ergebnis["fehler"] == 0

    zeilen = [json.loads(z) for z in
              (mini_kompendium / "atome.jsonl").read_text().splitlines() if z]
    vektoren = np.load(mini_kompendium / "vektoren.npy")
    assert len(zeilen) == vektoren.shape[0]

    # Die beiden ursprünglichen, branchenfremden Atome bleiben unverändert
    # an ihrem Platz — nur angehängt, nie umsortiert.
    assert zeilen[0]["quelle"] == "afa.pdf"
    assert zeilen[1]["quelle"] == "ustg.md"
    assert any(z["quelle"] == "skr04-konten" for z in zeilen)
    assert any(z["quelle"] == "skr04-automatik" for z in zeilen)


def test_neue_zeilen_sind_l2_normalisiert(mini_kompendium):
    sb.bauen(mini_kompendium, embed=_fake_embed())
    vektoren = np.load(mini_kompendium / "vektoren.npy")
    # Zeile 0/1 kommen vorbelegt aus der Fixture (bereits Einheitsvektoren);
    # ab Zeile 2 stammt alles aus diesem Lauf und muss Norm ≈ 1 haben.
    for row in vektoren[2:]:
        norm = float(np.linalg.norm(row))
        assert norm == pytest.approx(1.0, abs=1e-5)


def test_zweiter_lauf_ohne_neu_bauen_ist_idempotent(mini_kompendium):
    erster = sb.bauen(mini_kompendium, embed=_fake_embed())
    assert erster["geschrieben"]
    stand_nach_erstem = (mini_kompendium / "atome.jsonl").read_text()

    zweiter = sb.bauen(mini_kompendium, embed=_fake_embed())
    assert zweiter["neu"] == 0
    assert not zweiter["geschrieben"]
    assert (mini_kompendium / "atome.jsonl").read_text() == stand_nach_erstem

    zeilen = [json.loads(z) for z in
              (mini_kompendium / "atome.jsonl").read_text().splitlines() if z]
    quellen = [z["quelle"] for z in zeilen]
    # Keine Dubletten: jede (quelle, loc)-Kombination genau einmal.
    locs = [(z["quelle"], z["loc"]) for z in zeilen if z["quelle"].startswith("skr04-")]
    assert len(locs) == len(set(locs))
    assert quellen.count("skr04-konten") > 0


def test_neu_bauen_ersetzt_die_skr04_atome_statt_zu_verdoppeln(mini_kompendium):
    sb.bauen(mini_kompendium, embed=_fake_embed())
    nach_erstem = len(_zeilen(mini_kompendium))

    ergebnis = sb.bauen(mini_kompendium, neu_bauen=True, embed=_fake_embed())
    assert ergebnis["geschrieben"]
    nach_zweitem = _zeilen(mini_kompendium)
    assert len(nach_zweitem) == nach_erstem  # ersetzt, nicht verdoppelt
    # Die zwei branchenfremden Atome bleiben erhalten.
    assert any(z["quelle"] == "afa.pdf" for z in nach_zweitem)
    assert any(z["quelle"] == "ustg.md" for z in nach_zweitem)


def test_embedding_fehler_wird_gezaehlt_ohne_absturz(mini_kompendium):
    ergebnis = sb.bauen(mini_kompendium, embed=lambda text: None)
    assert ergebnis["fehler"] == ergebnis["neu"]
    assert not ergebnis["geschrieben"]
    # Ohne einen einzigen erfolgreichen Vektor bleibt das Kompendium unberührt.
    assert not (mini_kompendium / "atome.jsonl.tmp").exists()


def _zeilen(kompendium_dir: Path) -> list[dict]:
    return [json.loads(z) for z in
            (kompendium_dir / "atome.jsonl").read_text().splitlines() if z]


# ── Grundwissen-Anhang ────────────────────────────────────────────────────

def test_grundwissen_anhaengen_schreibt_kurzuebersicht(tmp_path):
    pfad = tmp_path / "kontierung-grundwissen.md"
    pfad.write_text("# Grundwissen\n\nSchon vorhandener Text.")
    sb.grundwissen_anhaengen(pfad)
    inhalt = pfad.read_text()
    assert "Schon vorhandener Text." in inhalt
    assert "Bewirtung: SKR04 6640 / SKR03 4650" in inhalt
    assert "Wartung Hard- und Software: SKR04 6495 / SKR03 —" in inhalt


def test_grundwissen_anhaengen_probe_schreibt_nichts(tmp_path):
    pfad = tmp_path / "kontierung-grundwissen.md"
    text = sb.grundwissen_anhaengen(pfad, probe=True)
    assert "Bewirtung: SKR04 6640" in text
    assert not pfad.exists()


def test_grundwissen_anhaengen_ist_idempotent(tmp_path):
    pfad = tmp_path / "kontierung-grundwissen.md"
    sb.grundwissen_anhaengen(pfad)
    erster_stand = pfad.read_text()
    sb.grundwissen_anhaengen(pfad)
    assert pfad.read_text() == erster_stand
    assert erster_stand.count(sb.GRUNDWISSEN_START) == 1
