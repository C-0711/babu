#!/usr/bin/env python3
"""Gemma bucht — und fragt so lange nach, bis es buchen kann.

Der Prozess, wie er am 24.08.2026 entschieden wurde: PaddleOCR liest die
Zeilen, dazu kommen Ladenprofil und Personenprofil als Kontext, und Gemma
verbucht den Beleg. Was nur Nina wissen kann, wird gefragt — ALLE offenen
Fragen auf einmal, jede als Multiple Choice. Nina tippt einmal durch, die
Antworten kommen gesammelt zurück, dann wird gebucht. Der Server merkt
sich nichts; der Zustand lebt im Telefon.

Die Leitplanke gegen halluzinierte Konten: Gemma wählt eine KATEGORIE aus
dem geprüften Katalog (kontierung.py), niemals eine Kontonummer. Die Nummer
setzt dieses Modul deterministisch aus dem Katalog — im Kontenrahmen der
Nutzerin.

Reine Logik plus ein HTTP-Aufruf; kein Modulzustand, damit babu_web es
gefahrlos importieren kann.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

import kontierung

VLM_API = os.environ.get("VLM_API", "http://127.0.0.1:11435/v1/chat/completions")
VLM_MODELL = os.environ.get("VLM_MODELL", "gemma4-mm")
VLM_FRIST = float(os.environ.get("VLM_FRIST", "120"))

# Normal ist EIN Fragenpaket. Wer nach so vielen Antworten immer noch
# fragt, bucht nicht mehr — der Beleg gehört auf den Schreibtisch.
ANTWORTEN_MAX = 8


# ── Die OCR-Zeilen aus dem Leseprotokoll ─────────────────────────────────────
#
# Der Watcher schreibt jede erkannte Zeile in die Protokoll-Tabelle. Das ist
# unser eigenes Format — hier zu parsen ist kein Scraping, sondern Lesen der
# eigenen Ablage.

_ZEILE = re.compile(r"\|\s*\d+\s*\|[^|]*\|\s*(.+?)\s*\|\s*\S+\s*\(\d+%\)")


def zeilen_aus_protokoll(md: str) -> list[str]:
    teil = md.split("## Jede erkannte Zeile", 1)
    if len(teil) < 2:
        return []
    return [m.group(1) for z in teil[1].splitlines() if (m := _ZEILE.match(z))]


# ── Profil und Katalog als Prompt-Bausteine ──────────────────────────────────

def profil_text(e: dict) -> str:
    """Ladenprofil + Personenprofil aus den Einstellungen der Nutzerin."""
    klein = (e.get("kleinunternehmer") or "Nein").strip().lower() == "ja"
    return (
        f"Salon „{e.get('betrieb_name') or 'unbenannt'}“, Friseursalon. "
        f"Rechtsform: {e.get('rechtsform') or 'Einzelunternehmen'}. "
        f"Gewinnermittlung: {e.get('abschluss_art') or 'EÜR'}. "
        + ("Kleinunternehmerin nach §19 UStG — kein Vorsteuerabzug. "
           if klein else
           "Keine Kleinunternehmerin — Vorsteuerabzug, soweit ausgewiesen. ")
        + "Die Inhaberin arbeitet selbst im Salon und führt ein tägliches "
          "Kassenbuch; Bareinnahmen sind dort bereits erfasst."
    )


def katalog_text(rahmen: str = "SKR04") -> str:
    zeilen = []
    for k in kontierung.KATEGORIEN.values():
        try:
            konto = k.konto(rahmen)
        except ValueError:
            konto = None
        if not konto:
            continue  # unbestätigte Konten bekommt Gemma gar nicht erst
        hinweis = f" — {k.hinweis}" if k.hinweis else ""
        zeilen.append(f"  {k.code}: {k.name}{hinweis}")
    return "\n".join(zeilen)


# ── Der Prompt ───────────────────────────────────────────────────────────────

def prompt_bauen(profil: str, zeilen: list[str], antworten: list[dict],
                 rahmen: str = "SKR04", umsaetze: list[dict] | None = None,
                 nachbarn: list[dict] | None = None) -> str:
    beantwortet = ""
    if antworten:
        beantwortet = "\nNINA HAT BEREITS BEANTWORTET:\n" + "\n".join(
            f"  Frage: {a.get('frage', '')}\n  Antwort: {a.get('antwort', '')}"
            for a in antworten)
    konto_kontext = ""
    if umsaetze:
        konto_kontext = ("\nKONTOBEWEGUNGEN im Umfeld (Bank/PayPal aus den "
                         "Kontoauszügen) — nutze sie zum Abgleich, z. B. für den "
                         "Euro-Betrag einer Fremdwährungszahlung:\n" + "\n".join(
            f"  {u.get('datum', '?')}  {u.get('betrag', '?')} €  {str(u.get('text', ''))[:70]}"
            for u in umsaetze))
    beleg_kontext = ""
    if nachbarn:
        beleg_kontext = ("\nWEITERE BELEGE desselben Monats (für Dubletten und "
                         "Zusammenhänge — NICHT mitbuchen):\n" + "\n".join(
            f"  {b.get('datum', '?')}  {b.get('brutto', '?')} €  {str(b.get('lieferant', ''))[:50]}"
            for b in nachbarn))
    return f"""Du bist die Buchhaltung eines Friseursalons und verbuchst genau EINEN Beleg.

PROFIL: {profil}

KATEGORIEN (wähle GENAU eine über ihren Code — Kontonummern vergibst nicht du):
{katalog_text(rahmen)}

DER BELEG — die erkannten Textzeilen in Lesereihenfolge:
{chr(10).join('  ' + z for z in zeilen)}
{konto_kontext}{beleg_kontext}{beantwortet}
Verbuche den Beleg unter Berücksichtigung des Profils. Regeln:
- Erfinde keine Umsatzsteuer, die nicht auf dem Beleg ausgewiesen ist.
- Erkenne die Währung aus dem Beleg; bei Fremdwährung nimm betrag_eur aus
  einer passenden Kontobewegung, sonst schätze ihn.
- Passt eine Kontobewegung exakt zu diesem Beleg, nenne sie in der
  Begründung — taucht der Beleg doppelt auf, sag es in einer Rückfrage.
- Wenn Angaben fehlen, die nur Nina kennt, stell ALLE offenen Fragen AUF
  EINMAL — jede als Multiple Choice mit 2 bis 4 kurzen Antwortmöglichkeiten,
  in ihrer Sprache (du-Form). Frag nur, was fürs Buchen wirklich nötig ist.
- Frag nichts, was schon beantwortet wurde. Ist alles klar, buchst du sofort.

Antworte NUR mit einem JSON-Objekt, ohne Text davor oder danach:
entweder {{"status": "fragen",
           "fragen": [{{"frage": "…", "optionen": ["…", "…"]}}]}}
oder     {{"status": "gebucht",
           "kategorie": "<code aus der Liste>",
           "buchungstext": "…",
           "betrag": 0.0, "waehrung": "EUR",
           "betrag_eur": 0.0, "ust_satz": 0,
           "begruendung": "ein Satz"}}"""


# ── Antwort prüfen: der Katalog hat das letzte Wort ──────────────────────────

def buchung_pruefen(roh: dict, rahmen: str = "SKR04") -> dict:
    """Aus Gemmas Antwort wird eine Runde: frage | gebucht | unklar.

    Bei „gebucht" wird die Kontonummer HIER aus dem Katalog gesetzt — eine
    Kategorie, die es nicht gibt, wird zur Rückfrage statt zur Buchung.
    """
    status = roh.get("status")
    if status == "fragen":
        fragen = []
        for f in (roh.get("fragen") or [])[:4]:
            frage = str(f.get("frage", "")).strip() if isinstance(f, dict) else ""
            optionen = [str(o).strip()[:60] for o in (f.get("optionen") or [])
                        if str(o).strip()] if isinstance(f, dict) else []
            if frage:
                fragen.append({"frage": frage[:200], "optionen": optionen[:4]})
        if fragen:
            return {"status": "fragen", "fragen": fragen}
        return {"status": "unklar", "roh": roh}
    if status != "gebucht":
        return {"status": "unklar", "roh": roh}
    kat = kontierung.KATEGORIEN.get(str(roh.get("kategorie", "")).strip())
    konto = None
    if kat is not None:
        try:
            konto = kat.konto(rahmen)
        except ValueError:
            konto = None
    if konto is None:
        return {"status": "fragen", "fragen": [{
            "frage": "In welche Kategorie gehört dieser Beleg?",
            "optionen": ["Material für den Salon", "Ware zum Weiterverkauf",
                         "Etwas Privates", "Weiß ich selbst nicht genau"]}]}
    try:
        betrag_eur = round(float(roh.get("betrag_eur") or roh.get("betrag") or 0), 2)
    except (TypeError, ValueError):
        betrag_eur = 0.0
    try:
        satz = int(roh.get("ust_satz") or 0)
    except (TypeError, ValueError):
        satz = 0
    if satz not in (0, 7, 19):
        satz = 0
    return {"status": "gebucht", "buchung": {
        "kategorie": kat.code,
        "kategorie_name": kat.name,
        "konto": konto,
        "buchungstext": str(roh.get("buchungstext") or kat.name)[:120],
        "betrag": roh.get("betrag"),
        "waehrung": str(roh.get("waehrung") or "EUR")[:8].upper(),
        "betrag_eur": betrag_eur,
        "ust_satz": satz,
        "begruendung": str(roh.get("begruendung") or "")[:300],
    }}


# ── Eine Runde ───────────────────────────────────────────────────────────────

def _gemma(prompt: str) -> dict:
    koerper = {"model": VLM_MODELL, "temperature": 0.1, "max_tokens": 400,
               "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        VLM_API, json.dumps(koerper).encode(),
        {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=VLM_FRIST) as a:
        text = json.load(a)["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def runde(zeilen: list[str], einstellungen: dict, antworten: list[dict],
          rahmen: str = "SKR04", umsaetze: list[dict] | None = None,
          nachbarn: list[dict] | None = None) -> dict:
    """Eine Frage-oder-Buchung-Runde. Wirft nichts Fachliches — Netzfehler
    reicht der Aufrufer als 502 weiter."""
    if len(antworten) >= ANTWORTEN_MAX:
        return {"status": "aufgeben",
                "hinweis": "So viele Fragen löst kein Beleg — der gehört auf "
                           "den Schreibtisch."}
    roh = _gemma(prompt_bauen(profil_text(einstellungen), zeilen, antworten,
                              rahmen, umsaetze, nachbarn))
    ergebnis = buchung_pruefen(roh, rahmen)
    if ergebnis["status"] == "unklar":
        return {"status": "fragen", "fragen": [{
            "frage": "Magst du kurz sagen, worum es bei diesem Beleg geht?",
            "optionen": []}]}
    return ergebnis
