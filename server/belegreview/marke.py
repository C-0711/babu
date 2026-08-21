"""Der Briefkopf: wie die Rechnung eines Salons aussieht.

Eine Rechnung ist das Einzige, was viele Kundinnen schriftlich vom Salon in
die Hand bekommen. Sie soll nach ihm aussehen — nicht nach Behördenformular.

Hier liegt nur die REGEL: welche Werte erlaubt sind, was die Vorgabe ist,
und wie aus einem Vorschlag des Sprachmodells ein gültiger Stil wird. Das
Zeichnen macht die App, das Fragen macht `babu_web`. So bleibt prüfbar, was
herauskommt — auch wenn das Modell Unsinn antwortet.
"""
from __future__ import annotations

import re

# Bewusst wenige Stellschrauben. Eine Rechnung braucht keine Gestaltungs-
# freiheit, sie braucht Wiedererkennbarkeit und Lesbarkeit.
SCHRIFTEN = ("serif", "sans")
AUSRICHTUNGEN = ("links", "mitte")

VORGABE = {"farbe": "#1F1D1B", "schrift": "serif", "ausrichtung": "links",
           "linie": True}

FARBE_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Zu helle Farben sind auf Papier nicht lesbar — eine Rechnung wird gedruckt.
MAX_HELLIGKEIT = 0.72


def _helligkeit(hex_farbe: str) -> float:
    """Wahrgenommene Helligkeit 0–1 (ITU-R BT.601)."""
    r = int(hex_farbe[1:3], 16) / 255
    g = int(hex_farbe[3:5], 16) / 255
    b = int(hex_farbe[5:7], 16) / 255
    return 0.299 * r + 0.587 * g + 0.114 * b


def stil_pruefen(roh: dict | None) -> dict:
    """Aus einem Vorschlag einen gültigen Stil machen — ohne je zu scheitern.

    Was fehlt oder unbrauchbar ist, fällt auf die Vorgabe zurück. Ein
    Sprachmodell, das sich vertut, darf keine unleserliche Rechnung erzeugen.
    """
    roh = roh if isinstance(roh, dict) else {}
    stil = dict(VORGABE)

    farbe = str(roh.get("farbe") or "").strip()
    if FARBE_RE.match(farbe) and _helligkeit(farbe) <= MAX_HELLIGKEIT:
        stil["farbe"] = farbe.upper()

    schrift = str(roh.get("schrift") or "").strip().lower()
    if schrift in SCHRIFTEN:
        stil["schrift"] = schrift

    ausrichtung = str(roh.get("ausrichtung") or "").strip().lower()
    if ausrichtung in AUSRICHTUNGEN:
        stil["ausrichtung"] = ausrichtung

    if "linie" in roh:
        stil["linie"] = bool(roh["linie"])

    begruendung = str(roh.get("begruendung") or "").strip()[:200]
    if begruendung:
        stil["begruendung"] = begruendung
    return stil


def frage_bauen(einstellungen: dict) -> str:
    """Was babu das Sprachmodell fragt, um einen Briefkopf vorzuschlagen."""
    e = {k: str((einstellungen or {}).get(k) or "").strip()
         for k in ("betrieb_name", "rechtsform", "anschrift")}
    beschreibung = e["betrieb_name"] or "ein Friseursalon"
    return (
        f"Gestalte den Briefkopf für die Rechnungen von „{beschreibung}“"
        + (f" ({e['rechtsform']})" if e["rechtsform"] else "")
        + (f", ansässig in {e['anschrift']}" if e["anschrift"] else "")
        + ". Es ist ein Friseur- und Beautysalon. Die Rechnung wird gedruckt "
          "und Kundinnen in die Hand gegeben: ruhig, hochwertig, gut lesbar. "
          "Wähle EINE Akzentfarbe, die zum Namen passt und auf weißem Papier "
          "gut lesbar ist (dunkel genug, kein Neon, kein Grau in Grau). "
          'Gib NUR JSON zurück: {"farbe": "#RRGGBB", "schrift": "serif|sans", '
          '"ausrichtung": "links|mitte", "linie": true|false, '
          '"begruendung": "ein Satz, warum das zu diesem Salon passt"}. '
          "serif wirkt klassisch und handwerklich, sans modern und kühl. "
          "linie=true zieht eine feine Linie unter den Briefkopf.")


def als_text(stil: dict) -> str:
    """Der Stil in Worten — damit die App ihn erklären kann, ohne Hex-Codes."""
    schrift = "klassisch" if stil.get("schrift") == "serif" else "modern"
    lage = "linksbündig" if stil.get("ausrichtung") == "links" else "mittig"
    satz = f"{schrift.capitalize()}e Schrift, {lage}"
    if stil.get("linie"):
        satz += ", mit feiner Linie"
    return satz


# ---------------------------------------------------------------------------
# Logo von der KI: „Nano Banana" (gemini-3-pro-image). Der Auftrag entsteht
# aus den Firmendaten — der Salon heißt, wie er heißt, und das Zeichen soll
# danach aussehen, nicht nach Stockfoto.
# ---------------------------------------------------------------------------

LOGO_STILE = {
    "schlicht": "eine schlichte, zeitlose Wortmarke mit einem einzigen "
                "klaren Symbol, viel Weißraum",
    "verspielt": "eine freundliche, leicht verspielte Marke mit weichen "
                 "Formen und einer feinen Handschrift-Anmutung",
    "edel": "eine edle, reduzierte Marke wie für ein hochwertiges "
            "Friseurhandwerk, feine Linien, viel Ruhe",
}


def logo_auftrag(einstellungen: dict, stil_name: str = "schlicht",
                 farbe: str | None = None) -> str:
    """Der Auftrag ans Bildmodell — konkret genug, dass etwas Brauchbares
    herauskommt, und streng genug, dass es als Logo taugt."""
    name = str((einstellungen or {}).get("betrieb_name") or "").strip() or "Salon"
    ton = LOGO_STILE.get(stil_name, LOGO_STILE["schlicht"])
    farbe = farbe if farbe and FARBE_RE.match(str(farbe)) else VORGABE["farbe"]
    return (
        f"Entwirf ein Logo für einen Friseur- und Beautysalon namens „{name}“. "
        f"Gewünscht ist {ton}. "
        f"Hauptfarbe {farbe} auf reinem Weiß, höchstens zwei Farben insgesamt. "
        "Absolut flach und vektorartig, keine Fotografie, kein 3D, keine "
        "Verläufe, keine Schatten, kein Rahmen, kein Hintergrundmuster. "
        "Zentriert, quadratisch, mit Rand ringsum. "
        f"Wenn Text vorkommt, dann ausschließlich exakt „{name}“ — "
        "korrekt geschrieben, gut lesbar, keine erfundenen Wörter, keine "
        "Zusatzzeilen wie „Hair“ oder „Studio“. "
        "Es muss auch klein auf einer gedruckten Rechnung erkennbar sein.")


# ---------------------------------------------------------------------------
# Der Farbkatalog: vier Schritte zum Logo, und kein einziger Hex-Code für die
# Nutzerin. Jede Farbe ist auf weißem Papier geprüft — was hier steht, kann
# man drucken, ohne dass es verschwindet.
# ---------------------------------------------------------------------------

KATALOG = (
    {"schluessel": "kupfer",   "name": "Kupfer",      "hex": "#8A4B2A",
     "dazu": "warm und handwerklich"},
    {"schluessel": "mahagoni", "name": "Mahagoni",    "hex": "#6E2C2C",
     "dazu": "kräftig, klassisch"},
    {"schluessel": "aubergine", "name": "Aubergine",  "hex": "#4A2545",
     "dazu": "eigen, modern"},
    {"schluessel": "nachtblau", "name": "Nachtblau",  "hex": "#1F3A5F",
     "dazu": "ruhig und seriös"},
    {"schluessel": "salbei",   "name": "Salbei",      "hex": "#3F5D4B",
     "dazu": "natürlich, frisch"},
    {"schluessel": "tanne",    "name": "Tannengrün",  "hex": "#1F3D30",
     "dazu": "tief und wertig"},
    {"schluessel": "terrakotta", "name": "Terrakotta", "hex": "#9A4A34",
     "dazu": "südlich, warm"},
    {"schluessel": "graphit",  "name": "Graphit",     "hex": "#33383D",
     "dazu": "zurückhaltend, edel"},
    {"schluessel": "schwarz",  "name": "Tiefschwarz", "hex": "#1F1D1B",
     "dazu": "immer richtig"},
)

# Die vier Schritte — sie stehen hier, damit App und Portal dieselben nennen.
SCHRITTE = (
    {"nummer": 1, "titel": "Deine Farbe",
     "frage": "Welche Farbe passt zu deinem Salon?"},
    {"nummer": 2, "titel": "Dein Stil",
     "frage": "Wie soll es wirken?"},
    {"nummer": 3, "titel": "Dein Zeichen",
     "frage": "babu entwirft — gefällt es dir?"},
    {"nummer": 4, "titel": "Fertig",
     "frage": "So sieht deine Rechnung aus."},
)


def farbe_aus_katalog(schluessel: str | None) -> dict | None:
    """Eine Farbe des Katalogs anhand ihres Schlüssels — oder None."""
    for eintrag in KATALOG:
        if eintrag["schluessel"] == str(schluessel or "").strip().lower():
            return dict(eintrag)
    return None


def katalog_pruefen() -> list[str]:
    """Selbstprüfung: keine Farbe darf so hell sein, dass sie beim Drucken
    verschwindet. Steht im Test, damit ein Nachtrag nicht durchrutscht."""
    return [e["name"] for e in KATALOG
            if not FARBE_RE.match(e["hex"]) or _helligkeit(e["hex"]) > MAX_HELLIGKEIT]


# ---------------------------------------------------------------------------
# Ein Knopf, zehn Vorschläge, ein Auftritt. Statt sich durch Farbe und Stil
# zu tasten: babu zeigt zehn fertige Zeichen, eines antippen — und Farbe,
# Schrift und Briefkopf stehen. Wer lieber selbst wählt, nimmt die vier
# Schritte; das hier ist der Weg für alle anderen.
# ---------------------------------------------------------------------------

VORSCHLAEGE = 10


def _mischen(anzahl: int, saat: int) -> list[tuple[str, dict]]:
    """Stil-und-Farbe-Paare, gestreut statt zufällig.

    Bewusst kein `random`: bei zehn Vorschlägen soll jeder Stil vorkommen und
    keine Farbe doppelt — Streuung schlägt Würfeln, wenn nur zehn Plätze da
    sind. Die Saat verschiebt nur den Startpunkt, damit ein zweiter Versuch
    andere Kombinationen zeigt.
    """
    alle = [(stil, dict(farbe)) for farbe in KATALOG for stil in LOGO_STILE]
    # Schrittweite teilerfremd zur Anzahl der Paare: so läuft die Auswahl
    # durch alle 27 Kombinationen, ohne je eine zu wiederholen.
    schritt = 7 if len(alle) % 7 else 5
    return [alle[(i * schritt + saat) % len(alle)] for i in range(anzahl)]


def vorschlag_saetze(einstellungen: dict, anzahl: int = VORSCHLAEGE,
                     saat: int = 0) -> list[dict]:
    """Die Aufträge für einen Schwung Vorschläge — je einer pro Zeichen."""
    anzahl = max(1, min(int(anzahl), 12))
    saetze = []
    for nummer, (stil, farbe) in enumerate(_mischen(anzahl, saat)):
        saetze.append({
            "nummer": nummer,
            "stil": stil,
            "farbe": farbe["hex"],
            "farbe_name": farbe["name"],
            "auftrag": logo_auftrag(einstellungen, stil, farbe["hex"]),
        })
    return saetze


def auftritt_aus(vorschlag: dict) -> dict:
    """Aus einem gewählten Zeichen der ganze Auftritt.

    Die Schrift folgt dem Stil: „edel" und „schlicht" tragen eine klassische
    Schrift, „verspielt" eine moderne — so passt der Briefkopf zum Zeichen,
    ohne dass jemand über Typografie nachdenken muss.
    """
    stil = str((vorschlag or {}).get("stil") or "schlicht")
    return stil_pruefen({
        "farbe": (vorschlag or {}).get("farbe"),
        "schrift": "sans" if stil == "verspielt" else "serif",
        "ausrichtung": "mitte" if stil == "edel" else "links",
        "linie": True,
        "begruendung": f"{(vorschlag or {}).get('farbe_name', 'Farbe')}, "
                       f"{stil} — passend zu deinem Zeichen.",
    })
