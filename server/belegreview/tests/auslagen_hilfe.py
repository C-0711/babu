"""Hilfen für die Auslagen-Tests (babu Expenses D1, 04.10.2026).

`auslagen_welt` ist `welt2` aus test_acting_as mit beschreibbaren
Mandantenboxen und ohne Vektor-Dienst. `lea()` legt bei einer Inhaberin eine
Mitarbeiterin mit Zugang an und meldet sie an.
"""
import json
import os

import pytest

import box as bx
from test_acting_as import _login, _neuer_client


@pytest.fixture()
def auslagen_welt(welt2, monkeypatch):
    monkeypatch.setattr(bx, "remote_aus_ref", lambda ref: str(bx.store_aus_ref(ref)))
    monkeypatch.setattr(welt2["bw"], "embedding_rechnen", lambda md: None)
    return welt2


def lea(welt, *, auslagen=True, belege=False, name="Lea", email="lea@salon.de",
        inhaberin="nina"):
    bw = welt["bw"]
    chefin = _login(bw, welt[inhaberin])
    d = chefin.post("/api/team", json={"name": name, "email": email, "betrag": "1200",
                                       "darf_belege": belege,
                                       "darf_auslagen": auslagen}).json()
    person = next(p for p in d["team"] if p["name"] == name)
    start = chefin.post("/api/team-zugang", json={"id": person["id"]}).json()["startpasswort"]
    client = _neuer_client(bw)
    bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    r = client.post("/api/login", json={"email": email, "passwort": start})
    assert r.status_code == 200, r.text
    return client, chefin, person["id"]


BUCHUNG = {"dokumentklasse": "beleg", "konto": "5400", "kategorie": "wareneinkauf",
           "betrag_eur": 23.40, "datum": "2026-05-12", "lieferant": "Rossmann",
           "ust_satz": 19, "zahlungsart": "bar"}


def einreichen(client, *, buchung=None, auslage=True):
    """Ein Beleg wie aus der App: Foto plus Ergebnis der Einschätzung."""
    bild = b"\xff\xd8\xff\xe0" + os.urandom(12)      # jedes Foto anders: keine Dublette
    daten = {"text": "Rossmann 23,40",
             "ergebnis": json.dumps({"buchung": buchung or BUCHUNG,
                                     "zeilen": ["Rossmann", "23,40"]})}
    if auslage:
        daten["auslage"] = "1"
    return client.post("/api/aufnahme", params={"name": "bon.jpg"},
                       files={"file": ("bon.jpg", bild, "image/jpeg")}, data=daten)
