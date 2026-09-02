#!/usr/bin/env python3
"""SKR04-Konten als Kompendium-Atome — läuft auf dem HOST, nicht im Container.

`~/kompendium` ist im babu-web-Container read-only gemountet
(`server/docker/compose.yml`), ein Container-Prozess kann dort also nicht
schreiben. Dieses Skript hängt für jedes der 1.516 SKR04-Konten
(`skr04_konten.KONTEN`) und jedes der 183 Automatikkonten
(`skr04_automatik.AUTOMATIK`) einen Text-Atom an `atome.jsonl`/
`vektoren.npy` an, damit Chat und Buchung beides beantworten können:
„Was ist Konto 6640?" und „Welches Konto für Bewirtung?" — Letzteres nur für
Konten, die in `kontierung.KATEGORIEN` als `geprueft=True` mit einem
SKR04-Konto verknüpft sind (Stand dieser Datei: 27 von 38 Kategorien).

Aufruf auf der H200V (Beispiel, siehe Abschlussbericht für Details):

    python3 werkzeuge/kompendium/skr04_atome_bauen.py --probe
    python3 werkzeuge/kompendium/skr04_atome_bauen.py --grundwissen-anhaengen
    docker compose -f ~/babu-docker/docker/compose.yml restart babu-web

Pflicht-Eigenschaften (siehe Planauftrag Phase 1):
  - nur ANHÄNGEN, bestehende Zeilen/Reihenfolge bleiben unberührt, außer
    `--neu-bauen` ersetzt ausdrücklich alle bisherigen skr04-*-Atome;
  - jede neue Zeile wird vor dem Speichern L2-normalisiert
    (`kompendium.suchen()` normalisiert nur den Query-Vektor, Zeile 81);
  - atomares Schreiben über `.tmp` + `os.replace()`, mit Backup der
    vorherigen Dateien und einer Nachprüfung der Invariante
    `len(atome.jsonl) == vektoren.shape[0]` (`kompendium.py:31-56`), bevor
    der alte Stand fällt — bricht die Nachprüfung, bleibt der alte Stand
    unverändert stehen;
  - idempotent: ein zweiter Lauf ohne `--neu-bauen` fügt nichts doppelt an,
    Schlüssel ist `(quelle, loc)`.

Die Embedding-Funktion ist injizierbar (Parameter `embed` von `bauen()`),
damit Tests ohne laufenden Embedding-Dienst auskommen — Default versucht
`babu_web.embedding_rechnen` wiederzuverwenden (exakt das Muster aus
`backfill_embeddings.py`), fällt aber, falls `babu_web` auf dem nackten Host
nicht importierbar ist (kein FastAPI installiert), auf denselben HTTP-Aufruf
direkt zurück.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import requests

HIER = Path(__file__).resolve().parent
REPO = HIER.parent.parent
BELEGREVIEW = REPO / "server" / "belegreview"
if str(BELEGREVIEW) not in sys.path:
    sys.path.insert(0, str(BELEGREVIEW))

import kontierung  # noqa: E402
import skr04_automatik  # noqa: E402
import skr04_konten  # noqa: E402

# Wörtlich aus dem SKR04-Kontenrahmen-PDF gelesen (Kapitelüberschriften der
# zehn Kontenklassen), Art.-Nr. 11175, Ausgabe 2026 — nicht geraten, siehe
# Abschlussbericht des Bau-Laufs für die geprüften Seitenzahlen.
KONTENKLASSEN: dict[str, str] = {
    "0": "Anlagevermögenskonten",
    "1": "Umlaufvermögenskonten",
    "2": "Eigenkapitalkonten/Fremdkapitalkonten",
    "3": "Fremdkapitalkonten",
    "4": "Betriebliche Erträge",
    "5": "Betriebliche Aufwendungen",
    "6": "Betriebliche Aufwendungen",
    "7": "Weitere Erträge und Aufwendungen",
    "8": "künftige Verwendung, von DATEV noch nicht belegt",
    "9": "Vortrags-, Kapital-, Korrektur- und statistische Konten",
}

GRUNDWISSEN_START = "<!-- skr04-atome: kontenuebersicht start -->"
GRUNDWISSEN_ENDE = "<!-- skr04-atome: kontenuebersicht ende -->"

SKR04_QUELLEN = ("skr04-konten", "skr04-automatik")


# ── Atom-Texte ────────────────────────────────────────────────────────────

def _automatik_satz(art: str, satz: float | int | None) -> str:
    name = "Automatik Vorsteuer (AV)" if art == "AV" else "Automatik Umsatzsteuer (AM)"
    if satz is None:
        return f"{name}, steuerfrei oder Sonderfall ohne festen Satz."
    satz_txt = f"{satz:g}".replace(".", ",")
    return f"{name}, {satz_txt} %."


def _kategorien_je_konto() -> dict[str, list]:
    """SKR04-Konto → alle geprüften babu-Kategorien, die darauf zeigen.

    Mehrere Kategorien können auf dasselbe Konto zeigen (z. B.
    verbrauchsmaterial UND materialeinsatz auf SKR04 5100) — ein einfaches
    `{skr04: kategorie}`-Dict würde die erste dabei stillschweigend
    verlieren, deshalb eine Liste je Konto."""
    zuordnung: dict[str, list] = {}
    for k in kontierung.KATEGORIEN.values():
        if k.geprueft and k.skr04:
            zuordnung.setdefault(k.skr04, []).append(k)
    return zuordnung


def konto_atom_text(nr: str, name: str, *, automatik=None, kategorien=None) -> str:
    """Ein Atom in Aussage- UND Frageform. `kategorien` (optional, eine
    Liste) fügt je Treffer eine weitere Frage „Welches Konto für …?" an —
    das beantwortet nicht nur „Was ist Konto 6640?", sondern auch
    „Welches Konto für Bewirtung?"."""
    name = name.strip()
    klasse = nr[0]
    zeilen = [f"Konto {nr} im SKR04-Kontenrahmen: {name}. "
              f"Kontenklasse {klasse} ({KONTENKLASSEN.get(klasse, 'unbekannt')})."]
    if automatik:
        zeilen.append(_automatik_satz(automatik[0], automatik[1]))
    for kategorie in (kategorien or []):
        if kategorie.hinweis:
            zeilen.append(f"In babu die Kategorie „{kategorie.name}“ — "
                          f"{kategorie.hinweis.rstrip('.')}.")
        else:
            zeilen.append(f"In babu die Kategorie „{kategorie.name}“.")
        if kategorie.skr03:
            zeilen.append(f"SKR03-Pendant: Konto {kategorie.skr03}.")
        zeilen.append(f"Frage: Welches Konto für {kategorie.name}? "
                      f"Antwort: Konto {nr} ({name}).")
    zeilen.append(f"Frage: Was ist Konto {nr}? Antwort: {name}.")
    return "\n".join(zeilen)


def automatik_atom_text(nr: str, name: str, eintrag: tuple) -> str:
    """Eigenes Atom je Automatikkonto — die Steuerautomatik ist hier das
    eigentliche Wissen (kein Steuerschlüssel auf der Buchung nötig/erlaubt),
    zusätzlich zum normalen `skr04-konten`-Atom desselben Kontos."""
    art, satz, _bezeichnung = eintrag
    satz_kurz = _automatik_satz(art, satz)
    zeilen = [
        f"Konto {nr} ({name.strip()}) hat im SKR04 eine Steuerautomatik: {satz_kurz}",
        "Automatik Vorsteuer (AV) errechnet die Vorsteuer, Automatik "
        "Umsatzsteuer (AM) die Umsatzsteuer automatisch aus dem "
        "Buchungsbetrag dieses Kontos — ein zusätzlicher Steuerschlüssel "
        "auf der Buchung widerspricht der Automatik.",
        f"Frage: Hat Konto {nr} eine Steuerautomatik? "
        f"Antwort: Ja, {satz_kurz.rstrip('.')}.",
        f"Frage: Braucht Konto {nr} einen Steuerschlüssel beim Buchen? "
        "Antwort: Nein — die Steuer kommt automatisch aus dem Konto.",
    ]
    return "\n".join(zeilen)


def neue_atome_bauen() -> list[dict]:
    """Die vollständige, deterministische Menge frischer SKR04-Atome (ohne
    `id`, ohne Vektor) — Reihenfolge: erst alle 1.516 Konten (Dict-Reihen-
    folge von `skr04_konten.KONTEN`), danach alle 183 Automatikkonten."""
    kategorien_je_konto = _kategorien_je_konto()
    atome: list[dict] = []
    for nr, name in skr04_konten.KONTEN.items():
        text = konto_atom_text(nr, name, automatik=skr04_automatik.AUTOMATIK.get(nr),
                               kategorien=kategorien_je_konto.get(nr))
        atome.append({"quelle": "skr04-konten", "loc": f"Konto {nr}", "text": text})
    for nr, eintrag in skr04_automatik.AUTOMATIK.items():
        name = skr04_konten.KONTEN.get(nr) or eintrag[2]
        atome.append({"quelle": "skr04-automatik", "loc": f"Konto {nr}",
                      "text": automatik_atom_text(nr, name, eintrag)})
    return atome


def kontenuebersicht_zeilen() -> list[str]:
    """Eine Zeile je geprüfter babu-Kategorie fürs Grundwissen — NICHT die
    1.516 SKR04-Konten (das würde den 30.000-Zeichen-Deckel von
    `kompendium.kontierungswissen()` sprengen, dafür gibt es die Vektor-
    suche)."""
    return [f"{k.name}: SKR04 {k.skr04} / SKR03 {k.skr03 or '—'}"
            for k in kontierung.KATEGORIEN.values() if k.geprueft]


def kontenuebersicht_block() -> str:
    body = "\n".join(kontenuebersicht_zeilen())
    return (f"{GRUNDWISSEN_START}\n"
            "## Kontenübersicht (geprüfte babu-Kategorien)\n\n"
            f"{body}\n{GRUNDWISSEN_ENDE}\n")


def grundwissen_anhaengen(pfad: Path, *, probe: bool = False) -> str:
    """Schreibt/aktualisiert den Kurzübersicht-Abschnitt in
    `kontierung-grundwissen.md`, markiert durch feste Kommentare — ein
    erneuter Lauf ersetzt nur den eigenen Abschnitt, verdoppelt ihn nicht.
    Mit `--probe` wird nur der Text zurückgegeben, nichts geschrieben."""
    neu_block = kontenuebersicht_block()
    alt = pfad.read_text(encoding="utf-8") if pfad.exists() else ""
    if GRUNDWISSEN_START in alt and GRUNDWISSEN_ENDE in alt:
        vorher, rest = alt.split(GRUNDWISSEN_START, 1)
        _, nachher = rest.split(GRUNDWISSEN_ENDE, 1)
        ergebnis = vorher.rstrip("\n") + ("\n\n" if vorher.strip() else "") + \
            neu_block + nachher.lstrip("\n")
    else:
        trenner = "\n\n" if alt.strip() else ""
        ergebnis = alt.rstrip("\n") + trenner + neu_block if alt.strip() else neu_block
    if not probe:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(ergebnis, encoding="utf-8")
    return ergebnis


# ── Embedding (injizierbar) ─────────────────────────────────────────────

def _embedding_rechnen_direkt(text: str, *, api: str | None = None,
                              modell: str | None = None) -> dict | None:
    """Dieselbe HTTP-Konvention wie `babu_web.embedding_rechnen`
    (Präfix "title: none | text: …", `truncate_prompt_tokens`) — Fallback,
    falls `babu_web` auf dem Host wegen fehlendem FastAPI nicht
    importierbar ist."""
    api = api or os.environ.get("EMBED_API", "http://127.0.0.1:11436/v1/embeddings")
    modell = modell or os.environ.get("EMBED_MODELL", "embeddinggemma")
    try:
        r = requests.post(api, json={
            "model": modell,
            "input": f"title: none | text: {text[:6000]}",
            "truncate_prompt_tokens": 2040,
        }, timeout=15)
        r.raise_for_status()
        vektor = r.json()["data"][0]["embedding"]
        return {"modell": modell, "dim": len(vektor), "vektor": vektor}
    except Exception:  # noqa: BLE001
        return None


def _standard_embedder(*, api: str | None = None, modell: str | None = None):
    """`babu_web.embedding_rechnen`, wenn importierbar — sonst derselbe
    HTTP-Aufruf direkt."""
    if api is None and modell is None:
        try:
            import babu_web as bw  # noqa: PLC0415
            return bw.embedding_rechnen
        except Exception:  # noqa: BLE001
            pass
    return lambda text: _embedding_rechnen_direkt(text, api=api, modell=modell)


def _l2_normalisieren(vektor) -> list[float]:
    import numpy as np  # noqa: PLC0415
    arr = np.asarray(vektor, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm == 0:
        return arr.tolist()
    return (arr / norm).tolist()


# ── Lesen / Schreiben des Kompendiums ────────────────────────────────────

def _atome_lesen(pfad: Path) -> list[dict]:
    if not pfad.exists():
        return []
    with open(pfad, encoding="utf-8") as f:
        return [json.loads(z) for z in f if z.strip()]


def _ist_skr04(atom: dict) -> bool:
    return atom.get("quelle") in SKR04_QUELLEN


def _backup(pfad: Path) -> Path | None:
    if not pfad.exists():
        return None
    ziel = pfad.with_name(pfad.name + f".bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(pfad, ziel)
    return ziel


def bauen(kompendium_dir: Path | str, *, probe: bool = False,
          neu_bauen: bool = False, embed=None) -> dict:
    """Der eigentliche Bau-Lauf. `embed(text) -> {"vektor": [...]} | None`
    ist injizierbar — Tests übergeben eine Fake-Funktion, der Host-Lauf
    lässt sie weg und bekommt `_standard_embedder()`."""
    kompendium_dir = Path(kompendium_dir).expanduser()
    jsonl_pfad = kompendium_dir / "atome.jsonl"
    npy_pfad = kompendium_dir / "vektoren.npy"

    alt = _atome_lesen(jsonl_pfad)
    vorhandene_skr04 = {(a.get("quelle"), a.get("loc")) for a in alt if _ist_skr04(a)}

    kandidaten = neue_atome_bauen()
    if neu_bauen:
        behalten_indizes = [i for i, a in enumerate(alt) if not _ist_skr04(a)]
        zu_bauen = kandidaten
    else:
        behalten_indizes = list(range(len(alt)))
        zu_bauen = [a for a in kandidaten
                    if (a["quelle"], a["loc"]) not in vorhandene_skr04]

    ergebnis = {
        "vorhandene_atome": len(alt), "vorhandene_skr04": len(vorhandene_skr04),
        "kandidaten": len(kandidaten), "neu": len(zu_bauen), "fehler": 0,
        "geschrieben": False,
    }
    if probe or not zu_bauen:
        return ergebnis

    embed = embed or _standard_embedder()
    fertig = []
    for a in zu_bauen:
        v = embed(a["text"])
        if not v or not v.get("vektor"):
            ergebnis["fehler"] += 1
            print(f"  ohne Vektor (Dienst?): {a['quelle']} · {a['loc']}")
            continue
        fertig.append({**a, "_vektor": _l2_normalisieren(v["vektor"])})

    if not fertig:
        return ergebnis

    import numpy as np  # noqa: PLC0415
    behalten_matrix = None
    if npy_pfad.exists():
        alte_matrix = np.asarray(np.load(npy_pfad), dtype=np.float32)
        behalten_matrix = (alte_matrix[behalten_indizes] if behalten_indizes
                           else np.zeros((0, alte_matrix.shape[1]), dtype=np.float32))

    neue_matrix = np.asarray([a["_vektor"] for a in fertig], dtype=np.float32)
    if behalten_matrix is not None and behalten_matrix.shape[0]:
        if behalten_matrix.shape[1] != neue_matrix.shape[1]:
            raise RuntimeError(
                f"Dimension passt nicht: bestehende Vektoren "
                f"{behalten_matrix.shape[1]}, neue {neue_matrix.shape[1]} — "
                "falsches Embedding-Modell? Nichts geschrieben.")
        gesamt_matrix = np.concatenate([behalten_matrix, neue_matrix])
    else:
        gesamt_matrix = neue_matrix

    behalten_atome = [alt[i] for i in behalten_indizes]
    naechste_id = max((a.get("id", -1) for a in behalten_atome), default=-1) + 1
    neue_zeilen = [{"id": naechste_id + i, "quelle": a["quelle"], "loc": a["loc"],
                    "text": a["text"]} for i, a in enumerate(fertig)]
    gesamt_zeilen = behalten_atome + neue_zeilen

    if len(gesamt_zeilen) != gesamt_matrix.shape[0]:
        raise RuntimeError(
            f"Invariante verletzt: {len(gesamt_zeilen)} Atome, "
            f"{gesamt_matrix.shape[0]} Vektoren — nichts geschrieben.")

    _backup(jsonl_pfad)
    _backup(npy_pfad)

    kompendium_dir.mkdir(parents=True, exist_ok=True)
    tmp_jsonl = jsonl_pfad.with_name(jsonl_pfad.name + ".tmp")
    tmp_npy = npy_pfad.with_name(npy_pfad.name + ".tmp")
    with open(tmp_jsonl, "w", encoding="utf-8") as f:
        for z in gesamt_zeilen:
            f.write(json.dumps(z, ensure_ascii=False) + "\n")
    # np.save haengt ".npy" an, wenn der Dateiname nicht schon so endet —
    # ueber ein offenes Dateihandle schreiben umgeht das (sonst wuerde aus
    # "vektoren.npy.tmp" ein "vektoren.npy.tmp.npy").
    with open(tmp_npy, "wb") as f:
        np.save(f, gesamt_matrix)

    # Nachpruefung genau wie kompendium._laden() (Zeile 44-52), BEVOR der
    # alte Stand faellt — schlaegt sie fehl, bleibt alles beim Alten.
    zeilen_zahl = sum(1 for _ in open(tmp_jsonl, "rb"))
    matrix_zahl = np.load(tmp_npy, mmap_mode="r").shape[0]
    if zeilen_zahl != matrix_zahl:
        tmp_jsonl.unlink(missing_ok=True)
        tmp_npy.unlink(missing_ok=True)
        raise RuntimeError(
            f"Nachpruefung fehlgeschlagen: {zeilen_zahl} Zeilen, "
            f"{matrix_zahl} Vektoren im .tmp-Stand — alter Stand bleibt "
            "erhalten, nichts wurde ersetzt.")

    os.replace(tmp_jsonl, jsonl_pfad)
    os.replace(tmp_npy, npy_pfad)
    ergebnis["geschrieben"] = True
    ergebnis["gesamt_atome"] = len(gesamt_zeilen)
    return ergebnis


# ── CLI ───────────────────────────────────────────────────────────────────

def _parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--kompendium", default=str(Path.home() / "kompendium"),
                  help="Kompendium-Verzeichnis (Default ~/kompendium)")
    p.add_argument("--probe", action="store_true",
                  help="nur zählen und melden, nichts schreiben")
    p.add_argument("--neu-bauen", action="store_true",
                  help="bisherige skr04-konten/skr04-automatik-Atome ersetzen "
                       "statt nur fehlende anzuhängen")
    p.add_argument("--grundwissen-anhaengen", action="store_true",
                  help="Kontenübersicht in kontierung-grundwissen.md "
                       "schreiben/aktualisieren")
    p.add_argument("--embed-api", default=None,
                  help="Embedding-Dienst-URL (nur der Fallback-Pfad "
                       "verwendet sie, falls babu_web nicht importierbar ist)")
    p.add_argument("--embed-modell", default=None)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    kompendium_dir = Path(args.kompendium).expanduser()

    if args.grundwissen_anhaengen:
        pfad = kompendium_dir / "kontierung-grundwissen.md"
        grundwissen_anhaengen(pfad, probe=args.probe)
        zeilen = kontenuebersicht_zeilen()
        print(f"Kontenübersicht: {len(zeilen)} geprüfte Kategorien "
              f"{'würden nach' if args.probe else 'in'} {pfad} geschrieben.")

    embed = None
    if args.embed_api or args.embed_modell:
        embed = _standard_embedder(api=args.embed_api, modell=args.embed_modell)

    ergebnis = bauen(kompendium_dir, probe=args.probe, neu_bauen=args.neu_bauen,
                     embed=embed)
    print(f"{ergebnis['vorhandene_atome']} Atome im Kompendium "
          f"({ergebnis['vorhandene_skr04']} davon SKR04) · "
          f"{ergebnis['kandidaten']} SKR04-Kandidaten insgesamt · "
          f"{ergebnis['neu']} {'würden' if args.probe else 'werden'} neu "
          f"eingebettet · {ergebnis['fehler']} Fehler")
    if ergebnis.get("geschrieben"):
        print(f"Kompendium jetzt {ergebnis['gesamt_atome']} Atome, "
              f"geschrieben nach {kompendium_dir}. Danach: "
              "docker compose restart babu-web (Prozess haelt Vektoren "
              "sonst bis zum naechsten Deploy im alten Stand).")
    return 0 if not ergebnis["fehler"] else 1


if __name__ == "__main__":
    sys.exit(main())
