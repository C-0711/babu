"""Der Chat im Portal hat ein Gedächtnis.

Bis zum 08.09.2026 schickte diese Seite genau `{frage, stream:true}` — den
Verlauf, den die App längst mitschickte, gab es hier nicht. Eine Nachfrage
wie „und wie viel war das nochmal?" lief ins Leere, und ein Neuladen leerte
den Chat.

Das Portal ist eine einzige HTML-Datei; falsche Verdrahtung fällt still
aus. Deshalb hier gegen den Text geprüft — dieselbe Bauart wie
`test_portal_verdrahtung.py`.
"""
import re
from pathlib import Path

PORTAL = (Path(__file__).resolve().parent.parent / "portal.html").read_text()

# Der Aufruf an den Chat, so wie er in der Datei steht.
ANFRAGE = re.search(r'api\("/chat".*?\}\)\}\);', PORTAL, re.S)


def test_die_frage_reist_nicht_mehr_allein():
    assert ANFRAGE, "der Aufruf an /chat wurde nicht gefunden"
    ruf = ANFRAGE.group(0)
    assert "verlauf:" in ruf, "das Portal schickt seinen Verlauf nicht mit"
    assert "gespraech:" in ruf, "die Nummer des Fadens reist nicht mit"


def test_der_verlauf_ueberlebt_das_neuladen():
    """Er liegt im Gerät — deshalb steht er nach dem Neuladen wieder da."""
    assert 'localStorage.setItem(CHAT_SPEICHER' in PORTAL
    assert "function chatHolen()" in PORTAL and "function chatZeichnen()" in PORTAL
    # Und er wird beim Öffnen der Ansicht auch wirklich gezeichnet.
    assert "fragen: ladeFragen" in PORTAL
    assert re.search(r"function ladeFragen\(\)\{[^}]*chatZeichnen\(\)", PORTAL, re.S)


def test_der_faden_kommt_zurueck_und_wird_behalten():
    """Ohne das würde jede Frage ein neues Gespräch anfangen — genau der
    Fehler, an dem die erste Fassung (BABU-25) gescheitert ist."""
    assert "if (j.gespraech){ chatFaden = j.gespraech; chatMerken(); }" in PORTAL


def test_nur_fertige_antworten_kommen_in_den_verlauf():
    """Eine halbe Antwort hilft beim nächsten Mal niemandem."""
    assert 'chatVerlauf.push({rolle:"assistant"' in PORTAL
    stelle = PORTAL.index('chatVerlauf.push({rolle:"assistant"')
    davor = PORTAL[stelle - 400:stelle]
    assert 'antwort.classList.remove("tippt")' in davor


def test_der_verlauf_waechst_nicht_unbegrenzt():
    """Weder im Gerät noch auf dem Weg zur Antwort."""
    assert "chatVerlauf.slice(-40)" in PORTAL
    assert "chatVerlauf.slice(-CHAT_ZUEGE * 2)" in PORTAL


def test_von_vorn_anfangen_gibt_es():
    assert 'id="chat-neu"' in PORTAL
    assert re.search(r'\$\("#chat-neu"\)\.addEventListener\("click"', PORTAL)


def test_das_gemerkte_ist_sichtbar_und_wegwerfbar():
    """Ein Gedächtnis, das man nicht sehen kann, ist keines, dem man trauen
    sollte — und Art. 17 DSGVO will einen Weg, es loszuwerden."""
    assert 'id="gemerkt"' in PORTAL
    assert "async function ladeGemerktes()" in PORTAL
    assert '"/api/gedaechtnis/" + nr + "/vergessen"' in PORTAL


def test_im_onclick_steht_nur_eine_nummer():
    """Hausregel: nie Namen in onclick-Attribute. Ein Merksatz ist ihr
    eigener Text und hätte dort nichts zu suchen."""
    stelle = PORTAL.index("async function ladeGemerktes()")
    block = PORTAL[stelle:stelle + 1200]
    assert "onclick=\"vergessen(${m.id})\"" in block
    assert "${m.text}" not in block, "der Text wird gesetzt, nicht eingebaut"
    assert 's.textContent = liste[i].text' in block
