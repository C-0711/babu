#!/usr/bin/env python3
"""Gemma bucht — und fragt so lange nach, bis es buchen kann.

Der Prozess, wie er am 24.08.2026 (letzte Fassung) entschieden wurde:
Gemma 4 Vision liest den Beleg SELBST — das Foto geht direkt ans Modell,
dazu Ladenprofil und Personenprofil als Kontext, und Gemma verbucht.
Kein OCR-Dienst mehr im Buchungsweg; Textzeilen/Markdown bleiben nur als
Rückfall, falls einmal kein Bild vorliegt. Was nur Nina wissen kann, wird gefragt — ALLE offenen
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

# Die Fächer der Ablage — Gemmas Klassifizierung muss eines davon treffen.
DOKUMENTKLASSEN = ("beleg", "vertrag", "behoerde", "kontoauszug")

# Normal ist EIN Fragenpaket. Wer nach so vielen Antworten immer noch
# fragt, bucht nicht mehr — der Beleg gehört auf den Schreibtisch.
ANTWORTEN_MAX = 8


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
                 nachbarn: list[dict] | None = None,
                 markdown: str | None = None, mit_bild: bool = False,
                 vertraege: list[dict] | None = None,
                 personal: list[dict] | None = None,
                 offene_abbuchungen: list[dict] | None = None) -> str:
    beantwortet = ""
    if antworten:
        beantwortet = "\nNINA HAT BEREITS BEANTWORTET:\n" + "\n".join(
            f"  Frage: {a.get('frage', '')}\n  Antwort: {a.get('antwort', '')}"
            for a in antworten)
    abgleich_kontext = ""
    if offene_abbuchungen:
        abgleich_kontext = ("\nNOCH UNGEDECKTE ABBUCHUNGEN vom Konto (der "
                            "Abgleich fand dafür noch keinen Beleg — deckt "
                            "DIESER Beleg eine davon, nenne sie in der "
                            "Begründung; deckt er keine, ist auch das eine "
                            "Antwort):\n" + "\n".join(
            f"  {u.get('datum', '?')}  {u.get('betrag', '?')} €  "
            f"{str(u.get('text') or u.get('gegenpartei') or '')[:60]}"
            for u in offene_abbuchungen))
    konto_kontext = ""
    if umsaetze:
        konto_kontext = ("\nKONTOBEWEGUNGEN im Umfeld (Bank/PayPal aus den "
                         "Kontoauszügen) — nutze sie zum Abgleich, z. B. für den "
                         "Euro-Betrag einer Fremdwährungszahlung:\n" + "\n".join(
            f"  {u.get('datum', '?')}  {u.get('betrag', '?')} €  {str(u.get('text', ''))[:70]}"
            for u in umsaetze))
    vertrag_kontext = ""
    if vertraege:
        vertrag_kontext = ("\nLAUFENDE VERTRÄGE des Salons (Dauerkosten — eine "
                           "Zahlung, die zu einem passt, gehört auf DESSEN "
                           "Kategorie und ist kein neuer Einzelaufwand; weicht "
                           "der Betrag vom Vertrag ab, frag nach):\n" + "\n".join(
            f"  {v.get('art_name') or v.get('art') or 'Vertrag'} · "
            f"{str(v.get('partner') or '?')[:40]} · "
            f"{v.get('betrag_monat') if v.get('betrag_monat') is not None else '?'} €/Monat"
            for v in vertraege))
    personal_kontext = ""
    if personal:
        personal_kontext = ("\nPERSONAL des Salons (eine Zahlung an diese "
                            "Person ist LOHN — Löhne bucht der Lohnlauf, nicht "
                            "der Beleg. Erkennst du eine Lohnzahlung, antworte "
                            "mit status \"abgeben\" und sag warum):\n" + "\n".join(
            f"  {str(p.get('name') or '?')[:40]} · "
            f"{p.get('kosten_monat') if p.get('kosten_monat') is not None else '?'} €/Monat"
            for p in personal))
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

DER BELEG — {"liegt dir als FOTO bei. Lies ihn selbst, vollständig: Kopf, jede Einzelposition, Summen, Steuerzeilen, Währung, Zahlweise." if mit_bild else ("als strukturiertes Dokument (Layout-Lesung):" if markdown else "die erkannten Textzeilen in Lesereihenfolge:")}
{"" if mit_bild else (markdown if markdown else chr(10).join('  ' + z for z in zeilen))}
{konto_kontext}{abgleich_kontext}{vertrag_kontext}{personal_kontext}{beleg_kontext}{beantwortet}
Verbuche den Beleg unter Berücksichtigung des Profils. Regeln:
- Erfinde keine Umsatzsteuer, die nicht auf dem Beleg ausgewiesen ist.
- Lies die EINZELPOSITIONEN aus dem Beleg: Bezeichnung, Betrag, Steuersatz
  und Kategorie je Position. Buche das Ganze auf die Kategorie mit dem
  größten Betragsanteil; jede Position behält daneben ihre eigene Kategorie.
  Sind die Positionen fachlich gemischt und keine Kategorie trägt mindestens
  80 % des Betrags, stell EINMAL die Frage, wie aufgeteilt werden soll —
  hat Nina dazu schon geantwortet, buche nach ihrer Antwort und frag nicht
  erneut.
- Enthält die Lesung Seiten-Marker („— Seite 1 von 3 —"), ist das EIN
  mehrseitiger Beleg: der Rechnungsbetrag ist die Endsumme der LETZTEN
  Seite; Zwischensummen und Überträge der Seiten davor zählst du nicht
  doppelt.
- Erkenne die Währung aus dem Beleg; bei Fremdwährung nimm betrag_eur aus
  einer passenden Kontobewegung, sonst schätze ihn.
- Passt eine Kontobewegung exakt zu diesem Beleg, nenne sie in der
  Begründung — taucht der Beleg doppelt auf, sag es in einer Rückfrage.
- Wenn Angaben fehlen, die nur Nina kennt, stell ALLE offenen Fragen AUF
  EINMAL — jede als Multiple Choice mit 2 bis 4 kurzen Antwortmöglichkeiten,
  in ihrer Sprache (du-Form). Frag nur, was fürs Buchen wirklich nötig ist.
- Frag nichts, was schon beantwortet wurde. Ist alles klar, buchst du sofort.
- Sag außerdem, WAS das Dokument ist (dokumentklasse): "beleg" (Bon oder
  Rechnung über einen Kauf — der Regelfall), "vertrag", "behoerde" (Post vom
  Amt) oder "kontoauszug". Danach richtet sich, in welches Fach es kommt.

Antworte NUR mit einem JSON-Objekt, ohne Text davor oder danach:
entweder {{"status": "abgeben", "hinweis": "…"}}  (nur für Lohn u. Ä. — Dinge,
          die nicht über einen Beleg gebucht werden)
oder     {{"status": "fragen",
           "fragen": [{{"frage": "…", "optionen": ["…", "…"]}}]}}
oder     {{"status": "gebucht",
           "kategorie": "<code aus der Liste>",
           "dokumentklasse": "beleg | vertrag | behoerde | kontoauszug",
           "lieferant": "…", "datum": "JJJJ-MM-TT",
           "buchungstext": "…",
           "betrag": 0.0, "waehrung": "EUR",
           "betrag_eur": 0.0, "ust_satz": 0,
           "positionen": [{{"bezeichnung": "…", "betrag": 0.0,
                           "ust_satz": 0, "kategorie": "<code>"}}],
           "begruendung": "ein Satz"}}"""


# ── Antwort prüfen: der Katalog hat das letzte Wort ──────────────────────────

def buchung_pruefen(roh: dict, rahmen: str = "SKR04") -> dict:
    """Aus Gemmas Antwort wird eine Runde: frage | gebucht | unklar.

    Bei „gebucht" wird die Kontonummer HIER aus dem Katalog gesetzt — eine
    Kategorie, die es nicht gibt, wird zur Rückfrage statt zur Buchung.
    """
    status = roh.get("status")
    if status in ("abgeben", "aufgeben"):
        return {"status": "aufgeben",
                "hinweis": str(roh.get("hinweis") or "Das gehört auf den "
                               "Schreibtisch, nicht auf einen Beleg.")[:300]}
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
    # Ohne gültige Dokumentklasse kann die Ablage kein Fach wählen — dann
    # wird gefragt statt geraten. Die Antwort fließt als `antworten` zurück.
    klasse = str(roh.get("dokumentklasse") or "").strip().lower()
    if klasse not in DOKUMENTKLASSEN:
        return {"status": "fragen", "fragen": [{
            "frage": "Was für ein Dokument ist das?",
            "optionen": ["Ein Beleg (Kauf oder Rechnung)", "Ein Vertrag",
                         "Post vom Amt", "Ein Kontoauszug"]}]}
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
    positionen = _positionen(roh)
    waehrung = str(roh.get("waehrung") or "EUR")[:8].upper()
    # Fremdwährung: die Positionsbeträge sind KEINE Euro, und ausländische
    # Steuer ist keine abziehbare Vorsteuer — keine Steuertabelle, Satz 0.
    steuersaetze = _steuertabelle(positionen) if waehrung == "EUR" else []
    if waehrung != "EUR":
        satz = 0
    if steuersaetze:
        # Bei Mischsätzen gibt es keinen „einen" Satz — auf Belegebene gilt
        # der führende (größter Bruttoanteil), die Tabelle trägt den Rest.
        satz = steuersaetze[0]["satz"]
    return {"status": "gebucht", "buchung": {
        "dokumentklasse": klasse,
        "lieferant": str(roh.get("lieferant") or "")[:80] or None,
        "datum": str(roh.get("datum") or "")[:10] or None,
        "kategorie": kat.code,
        "kategorie_name": kat.name,
        "konto": konto,
        "buchungstext": str(roh.get("buchungstext") or kat.name)[:120],
        "betrag": roh.get("betrag"),
        "waehrung": waehrung,
        "betrag_eur": betrag_eur,
        "ust_satz": satz,
        "positionen": positionen,
        "steuersaetze": steuersaetze,
        "begruendung": str(roh.get("begruendung") or "")[:300],
    }}


def _positionen(roh: dict) -> list[dict]:
    """Die Einzelpositionen, gesäubert. Kategorien außerhalb des Katalogs
    bleiben leer statt erfunden; mehr als 20 Positionen liest kein Bon."""
    aus = []
    for p in (roh.get("positionen") or [])[:20]:
        if not isinstance(p, dict):
            continue
        try:
            betrag = round(float(p.get("betrag") or 0), 2)
        except (TypeError, ValueError):
            continue
        try:
            satz = int(p.get("ust_satz") or 0)
        except (TypeError, ValueError):
            satz = 0
        kat = str(p.get("kategorie") or "").strip()
        aus.append({
            "bezeichnung": str(p.get("bezeichnung") or "")[:80],
            "betrag": betrag,
            "ust_satz": satz if satz in (0, 7, 19) else 0,
            "kategorie": kat if kat in kontierung.KATEGORIEN else None,
        })
    return aus


def _steuertabelle(positionen: list[dict]) -> list[dict]:
    """Die Steuertabelle des Belegs, aus den Positionen aggregiert —
    je Satz Brutto, Netto und USt, absteigend nach Bruttoanteil. Das ist
    genau die Form, die das Beleg-Modell der App (steuerPositionen) und
    der Mehrsatz-Split im Export erwarten."""
    je_satz: dict[int, float] = {}
    for p in positionen:
        satz, betrag = p.get("ust_satz"), p.get("betrag")
        if satz in (0, 7, 19) and betrag:
            je_satz[satz] = round(je_satz.get(satz, 0) + betrag, 2)
    aus = []
    for satz, brutto in je_satz.items():
        netto = round(brutto / (1 + satz / 100), 2)
        aus.append({"satz": satz, "brutto": brutto,
                    "netto": netto, "ust": round(brutto - netto, 2)})
    aus.sort(key=lambda z: -z["brutto"])
    return aus


def gemischt(buchung: dict) -> bool:
    """Tragen die Positionen keine klare Hauptkategorie (≥ 80 % des
    Betrags), soll niemand still buchen — dann wird gefragt."""
    je_kat: dict[str, float] = {}
    for p in buchung.get("positionen") or []:
        if p.get("kategorie") and p.get("betrag"):
            je_kat[p["kategorie"]] = je_kat.get(p["kategorie"], 0) + abs(p["betrag"])
    if len(je_kat) <= 1:
        return False
    return max(je_kat.values()) / sum(je_kat.values()) < 0.8


# ── Eine Runde ───────────────────────────────────────────────────────────────

def _gemma(prompt: str, bild: tuple[bytes, str] | None = None) -> dict:
    if bild is not None:
        import base64  # noqa: PLC0415
        daten, mime = bild
        inhalt = [
            {"type": "image_url", "image_url":
                {"url": f"data:{mime};base64,{base64.b64encode(daten).decode()}"}},
            {"type": "text", "text": prompt},
        ]
    else:
        inhalt = prompt
    koerper = {"model": VLM_MODELL, "temperature": 0.1, "max_tokens": 1200,
               "messages": [{"role": "user", "content": inhalt}]}
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
          nachbarn: list[dict] | None = None,
          markdown: str | None = None,
          bild: tuple[bytes, str] | None = None,
          vertraege: list[dict] | None = None,
          personal: list[dict] | None = None,
          offene_abbuchungen: list[dict] | None = None) -> dict:
    """Eine Frage-oder-Buchung-Runde. Wirft nichts Fachliches — Netzfehler
    reicht der Aufrufer als 502 weiter."""
    if len(antworten) >= ANTWORTEN_MAX:
        return {"status": "aufgeben",
                "hinweis": "So viele Fragen löst kein Beleg — der gehört auf "
                           "den Schreibtisch."}
    roh = _gemma(prompt_bauen(profil_text(einstellungen), zeilen, antworten,
                              rahmen, umsaetze, nachbarn, markdown,
                              mit_bild=bild is not None,
                              vertraege=vertraege, personal=personal,
                              offene_abbuchungen=offene_abbuchungen), bild)
    ergebnis = buchung_pruefen(roh, rahmen)
    if ergebnis["status"] == "unklar":
        return {"status": "fragen", "fragen": [{
            "frage": "Magst du kurz sagen, worum es bei diesem Beleg geht?",
            "optionen": []}]}
    return ergebnis
