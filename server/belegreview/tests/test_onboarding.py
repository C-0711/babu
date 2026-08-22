"""Der Onboarding-Wizard.

Der Wert steckt in den Prüfziffern. Eine verdrehte Ziffer in der
Steuer-Identifikationsnummer fällt sonst erst beim Lohnrechner auf, Wochen
später und in fremder Sprache. Deshalb prüfen die Tests hier vor allem, ob
Zahlendreher wirklich hängenbleiben — und ob die Meldung jemandem hilft,
der kein Buchhalter ist.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import onboarding as ob  # noqa: E402


# ————— Steuer-Identifikationsnummer —————

def test_gueltige_steuer_idnr():
    assert ob.steuer_idnr_pruefen("36574261809") == "36574261809"
    assert ob.steuer_idnr_pruefen("365 742 618 09") == "36574261809"


def test_die_pruefziffer_wird_nachgerechnet():
    """ISO 7064 MOD 11,10 — dieselbe Nummer mit anderer letzter Ziffer
    muss durchfallen."""
    assert ob._mod11_10("3657426180") == 9
    for falsch in "012345678":
        with pytest.raises(ob.OnboardingFehler):
            ob.steuer_idnr_pruefen("3657426180" + falsch)


def test_zahlendreher_faellt_auf():
    """Der häufigste Tippfehler überhaupt: zwei Ziffern vertauscht."""
    with pytest.raises(ob.OnboardingFehler):
        ob.steuer_idnr_pruefen("36574216809")     # 61 → 16


def test_steuer_idnr_beginnt_nie_mit_null():
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.steuer_idnr_pruefen("06574261809")
    assert "Null" in str(e.value)


def test_falsche_laenge_wird_erklaert():
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.steuer_idnr_pruefen("12345")
    assert "elf Ziffern" in str(e.value) and "Steuernummer des" in str(e.value)


def test_die_ziffernverteilung_wird_geprueft():
    """In den ersten zehn Stellen kommt genau eine Ziffer mehrfach vor.
    Eine Folge ohne Wiederholung kann keine IdNr sein."""
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.steuer_idnr_pruefen("12345678908")
    assert "verdreht" in str(e.value)


def test_fehlende_idnr_sagt_wo_sie_steht():
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.steuer_idnr_pruefen("")
    assert "Steuerbescheid" in str(e.value)


# ————— Sozialversicherungsnummer —————

@pytest.mark.parametrize("nummer", ["65170839J003", "15070649C103"])
def test_gueltige_sv_nummer(nummer):
    assert ob.sv_nummer_pruefen(nummer) == nummer


def test_sv_nummer_mit_leerzeichen_und_kleinbuchstaben():
    assert ob.sv_nummer_pruefen("65 170839 j 003") == "65170839J003"


def test_sv_nummer_pruefziffer():
    for falsch in "124567890":
        with pytest.raises(ob.OnboardingFehler):
            ob.sv_nummer_pruefen("65170839J00" + falsch)


def test_sv_nummer_falsche_form_wird_erklaert():
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.sv_nummer_pruefen("1234567890")
    assert "TTMMJJ" in str(e.value)


def test_wer_keinen_ausweis_hat_wird_nicht_aufgehalten():
    """Die Kasse vergibt eine Nummer — das darf das Onboarding nicht
    blockieren."""
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.sv_nummer_pruefen("")
    assert "lass das Feld frei" in str(e.value)
    # Und im Schritt selbst ist sie tatsächlich freiwillig:
    d = ob.schritt_pruefen("sozialversicherung", {"krankenkasse": "AOK"})
    assert d["krankenkasse"] == "AOK" and "rentenvers_nr" not in d


# ————— IBAN —————

def test_gueltige_iban():
    assert ob.iban_pruefen("DE02 1203 0000 0000 2020 51") == "DE02120300000000202051"


def test_iban_mit_vertauschten_ziffern():
    """Auf ein falsches Konto überwiesenes Gehalt holt niemand gern zurück."""
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.iban_pruefen("DE02120300000000202015")
    assert "Prüfsumme" in str(e.value)


def test_zu_kurze_deutsche_iban():
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.iban_pruefen("DE0212030000000020205")
    assert "22 Zeichen" in str(e.value)


def test_ohne_iban_kein_gehalt():
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.iban_pruefen("")
    assert "kein Gehalt" in str(e.value)


def test_auslaendische_iban_geht_auch():
    assert ob.iban_pruefen("AT611904300234573201").startswith("AT")


# ————— Die Schritte —————

def test_der_wizard_beginnt_bei_der_person():
    assert ob.naechster_schritt({})["id"] == "person"


def test_er_geht_der_reihe_nach():
    stand = {"erledigt": ["person", "anschrift"]}
    assert ob.naechster_schritt(stand)["id"] == "ausweis"


def test_am_ende_kommt_nichts_mehr():
    stand = {"erledigt": [s["id"] for s in ob.SCHRITTE]}
    assert ob.naechster_schritt(stand) is None
    assert ob.fortschritt(stand)["fertig"] is True


def test_der_fortschritt_zaehlt_richtig():
    assert ob.fortschritt({})["satz"].startswith(f"Noch {len(ob.SCHRITTE)}")
    fast = {"erledigt": [s["id"] for s in ob.SCHRITTE[:-1]]}
    assert ob.fortschritt(fast)["satz"] == "Nur noch ein Schritt."


def test_jeder_schritt_erklaert_sich():
    """Wer zwischen zwei Terminen tippt, liest keine Ausfüllhinweise."""
    for s in ob.SCHRITTE:
        assert s["titel"] and len(s["hilfe"]) > 20
        assert set(s["pflicht"]) <= set(s["felder"])


# ————— Ein Schritt wird geprüft —————

def test_person_wird_uebernommen():
    d = ob.schritt_pruefen("person", {"vorname": " Jana ", "name": "Holder",
                                      "geburtsdatum": "02.03.1994"})
    assert d == {"vorname": "Jana", "name": "Holder",
                 "geburtsdatum": "1994-03-02"}


def test_geburtsdatum_in_beiden_schreibweisen():
    for text in ("1994-03-02", "02.03.1994"):
        assert ob.schritt_pruefen("person", {"vorname": "J", "name": "H",
                                             "geburtsdatum": text})["geburtsdatum"] \
            == "1994-03-02"


def test_unmoegliches_geburtsdatum():
    for text in ("02.03.2024", "01.01.1890", "irgendwann"):
        with pytest.raises(ob.OnboardingFehler):
            ob.schritt_pruefen("person", {"vorname": "J", "name": "H",
                                          "geburtsdatum": text})


def test_fehlende_pflichtangabe_wird_benannt():
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.schritt_pruefen("person", {"vorname": "Jana"})
    assert "dein Nachname" in str(e.value)


def test_mehrere_fehlende_werden_aufgezaehlt():
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.schritt_pruefen("anschrift", {})
    text = str(e.value)
    assert "die Straße" in text and "der Ort" in text


def test_postleitzahl_hat_fuenf_ziffern():
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.schritt_pruefen("anschrift", {"strasse": "A", "plz": "701",
                                         "ort": "Stuttgart"})
    assert "fünf Ziffern" in str(e.value)


def test_unbekannter_schritt():
    with pytest.raises(ob.OnboardingFehler):
        ob.schritt_pruefen("irgendwas", {})


def test_kinderabschlaege_werden_gedeckelt():
    d = ob.schritt_pruefen("sozialversicherung",
                           {"krankenkasse": "AOK", "kinder_abschlaege": 9})
    assert d["kinder_abschlaege"] == 4


# ————— Belehrungen —————

def test_alle_drei_belehrungen_einzeln():
    assert ob.belehrungen_pruefen(
        ["arbeitsschutz", "hautschutz", "datenschutz"]) == \
        ["arbeitsschutz", "datenschutz", "hautschutz"]


def test_eine_fehlende_belehrung_wird_benannt():
    """Ein Sammelhaken über „ich habe alles gelesen" ist im Streitfall
    wertlos."""
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.belehrungen_pruefen(["arbeitsschutz", "datenschutz"])
    assert "Hautschutz" in str(e.value)


def test_gar_keine_belehrung():
    with pytest.raises(ob.OnboardingFehler) as e:
        ob.belehrungen_pruefen([])
    for was in ("Arbeitsschutz", "Hautschutz", "Datenschutz"):
        assert was in str(e.value)


def test_der_hautschutz_ist_dabei():
    """Die branchentypische Pflicht nach TRGS 530."""
    assert "hautschutz" in ob.BELEHRUNGEN


# ————— Die Strecke am Server —————

import subprocess  # noqa: E402


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "s"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import babu_web
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None
    babu_web._REG_ZULETZT.clear()
    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    client.post("/api/einstellungen", json={"betrieb_name": "Salon Nina"})
    return client, babu_web


ECKDATEN = {"vorname": "Jana", "name": "Holder", "telefon": "0171 2345678",
            "art": "teilzeit", "eintritt": "2026-10-01", "stunden_woche": 24,
            "tage_woche": 3, "entgelt": 1600, "taetigkeit": "Friseurin"}


def test_anlegen_liefert_einen_link(welt):
    client, _ = welt
    r = client.post("/api/mitarbeiter", json=ECKDATEN)
    assert r.status_code == 200
    d = r.json()
    assert d["einladung"].startswith("/start/") and len(d["einladung"]) > 25
    assert "Jana Holder" in d["satz"] or "Holder" in d["satz"]


def test_unhaltbare_eckdaten_werden_vorher_abgefangen(welt):
    """Sonst füllt sie zwanzig Minuten aus und der Vertrag geht dann nicht."""
    client, _ = welt
    r = client.post("/api/mitarbeiter", json={**ECKDATEN, "entgelt": 900})
    assert r.status_code == 400 and "Mindestlohn" in r.json()["fehler"]


def test_der_link_zeigt_den_ersten_schritt(welt):
    client, _ = welt
    marke = client.post("/api/mitarbeiter", json=ECKDATEN).json()["einladung"].split("/")[-1]
    d = client.get(f"/api/onboarding/{marke}").json()
    assert d["salon"] == "Salon Nina" and d["vorname"] == "Jana"
    assert d["schritt"]["id"] == "person"
    assert d["fortschritt"]["erledigt"] == 0


def test_der_wizard_laeuft_durch(welt):
    client, bw = welt
    marke = client.post("/api/mitarbeiter", json=ECKDATEN).json()["einladung"].split("/")[-1]
    antworten = [
        ("person", {"vorname": "Jana", "name": "Holder",
                    "geburtsdatum": "02.03.1994"}),
        ("anschrift", {"strasse": "Marktstr. 3", "plz": "70173",
                       "ort": "Stuttgart"}),
        ("ausweis", {"ausweis_dokument": "docs/2026-10/ausweis.jpg"}),
        ("steuer", {"steuer_idnr": "36574261809"}),
        ("sozialversicherung", {"krankenkasse": "AOK Baden-Württemberg",
                                "rentenvers_nr": "65170839J003"}),
        ("bank", {"iban": "DE02 1203 0000 0000 2020 51"}),
        ("vertrag", {"vertrag_angenommen": True}),
        ("belehrungen", {"belehrungen": ["arbeitsschutz", "hautschutz",
                                         "datenschutz"]}),
    ]
    for schritt, daten in antworten:
        r = client.post(f"/api/onboarding/{marke}/{schritt}", json=daten)
        assert r.status_code == 200, (schritt, r.json())

    d = client.get(f"/api/onboarding/{marke}").json()
    assert d["fortschritt"]["fertig"] is True
    assert d["schritt"] is None

    [m] = client.get("/api/mitarbeiter").json()["mitarbeiter"]
    assert m["stand"] == "vollstaendig"
    assert m["steuer_idnr"] == "36574261809"
    assert m["iban"] == "DE02120300000000202051"
    assert m["vertrag_angenommen"]
    assert sorted(m["belehrungen"]) == ["arbeitsschutz", "datenschutz",
                                        "hautschutz"]


def test_ein_tippfehler_haelt_den_schritt_auf(welt):
    client, _ = welt
    marke = client.post("/api/mitarbeiter", json=ECKDATEN).json()["einladung"].split("/")[-1]
    r = client.post(f"/api/onboarding/{marke}/steuer",
                    json={"steuer_idnr": "36574216809"})     # Ziffern gedreht
    assert r.status_code == 400 and "verrutscht" in r.json()["fehler"]
    assert client.get(f"/api/onboarding/{marke}").json()["fortschritt"]["erledigt"] == 0


def test_ein_falscher_link_fuehrt_nirgendwohin(welt):
    client, _ = welt
    assert client.get("/api/onboarding/" + "x" * 30).status_code == 404
    assert client.post("/api/onboarding/" + "x" * 30 + "/person",
                       json={}).status_code == 404


def test_ein_abgelaufener_link_gilt_nicht_mehr(welt):
    client, bw = welt
    import datetime as dt
    marke = client.post("/api/mitarbeiter", json=ECKDATEN).json()["einladung"].split("/")[-1]
    alt = (dt.datetime.now(dt.timezone.utc)
           - dt.timedelta(days=bw.EINLADUNG_GILT_TAGE + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with bw._DB_LOCK, bw._db() as c:
        c.execute("UPDATE mitarbeiter SET eingeladen_am=? WHERE einladung=?",
                  (alt, marke))
    r = client.get(f"/api/onboarding/{marke}")
    assert r.status_code == 404 and "gilt nicht mehr" in r.json()["fehler"]


def test_der_link_verraet_nichts_ueber_andere(welt):
    """Ohne Anmeldung — also darf auch nur herauskommen, was sie über sich
    selbst ohnehin weiß."""
    client, _ = welt
    client.post("/api/mitarbeiter", json={**ECKDATEN, "name": "Sommer"})
    marke = client.post("/api/mitarbeiter", json=ECKDATEN).json()["einladung"].split("/")[-1]
    d = client.get(f"/api/onboarding/{marke}").json()
    assert "Sommer" not in str(d)
    assert "entgelt" not in d and "steuer_idnr" not in d


def test_die_akte_laesst_sich_loeschen(welt):
    client, bw = welt
    mid = client.post("/api/mitarbeiter", json=ECKDATEN).json()["id"]
    assert client.post(f"/api/mitarbeiter/{mid}/loeschen").status_code == 200
    assert client.get("/api/mitarbeiter").json()["mitarbeiter"] == []


def test_personaldaten_landen_nicht_in_der_belegbox(welt):
    client, _ = welt
    marke = client.post("/api/mitarbeiter", json=ECKDATEN).json()["einladung"].split("/")[-1]
    client.post(f"/api/onboarding/{marke}/steuer", json={"steuer_idnr": "36574261809"})
    jahre = client.get("/api/ablage").json()["jahre"]
    assert "36574261809" not in str(jahre) and "Holder" not in str(jahre)


def test_fremdes_konto_sieht_die_personalakte_nicht(welt):
    client, bw = welt
    client.post("/api/mitarbeiter", json=ECKDATEN)
    from fastapi.testclient import TestClient
    fremd = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    fremd.post("/api/signup", json={"salon": "Fremd", "email": "f@x.de",
                                    "passwort": "passwort-lang"})
    assert fremd.get("/api/mitarbeiter").status_code == 403
    assert fremd.post("/api/mitarbeiter", json=ECKDATEN).status_code == 403


def test_der_vertrag_steht_vor_der_zustimmung_bereit(welt):
    """Ein Vertrag, den man erst nach der Zusage bekommt, ist keiner."""
    client, _ = welt
    marke = client.post("/api/mitarbeiter", json=ECKDATEN).json()["einladung"].split("/")[-1]
    d = client.get(f"/api/onboarding/{marke}/vertrag/text").json()
    assert "Salon Nina" in d["text"] and "Jana Holder" in d["text"]
    assert "§ 1 Beginn" in d["text"] and "TRGS 530" in d["text"]
    assert d["form"] == "textform" and d["fassung"]


def test_ohne_gueltigen_link_kein_vertrag(welt):
    client, _ = welt
    assert client.get("/api/onboarding/" + "x" * 30 + "/vertrag/text").status_code == 404
