"""boxschreiber — Schreibpfad des Portals in die GitChain-Belegbox.

Eigener Clone (~/babu-web/box), nie der Bare-Store direkt.
Muster: fetch + reset --hard →
Datei schreiben → Commit mit Autor = angemeldete Nutzerin → Push via Gateway
mit Service-PAT im Header (Wert ohne Newline — bekannte Falle Nr. 2).
Push-Rennen mit dem Watcher (15-s-Takt): genau ein Retry, sonst Fehler.

Der Klon ist EINE Arbeitskopie mit EINEM Git-Index — Portal-Requests und
Hintergrund-Jobs (Vertrag lesen, Brief erklären, Salon-Check) schreiben aber
nebenläufig. Deshalb läuft `schreiben()` komplett unter einem Schloss: sonst
räumt der `reset --hard` des einen Threads dem anderen die Datei aus dem
Index, und der Commit trägt am Ende den falschen Inhalt unter fremdem Namen.

Seit Plan 21 (Phase 2) steht der Klon nicht mehr als Modulkonstante hier,
sondern in der `Box` — mitsamt ihrem Schloss. Ein Server kann mehrere Boxen
bedienen, und jede braucht ihre eigene Arbeitskopie mit ihrem eigenen
Schloss; ein gemeinsames wäre nur langsamer, ein gemeinsamer Klon falsch.
`schreiben()`/`loeschen()` bekommen die Box deshalb als erstes Argument.
`KLON`/`REF`/`REMOTE` bleiben als Quelle der Default-Box stehen (box.py
liest sie bei jedem Aufruf frisch), `PAT_PFAD` bleibt EIN Service-PAT: wer
auf welchen Ref schreiben darf, entscheidet das Gateway, nicht dieser Code.
"""
import os
import re
import secrets
import subprocess
import time
from pathlib import Path

import box as bx

KLON = Path(os.environ.get("BABU_BOX_KLON", str(Path.home() / "babu-web" / "box")))
GATEWAY = os.environ.get("BABU_GATEWAY", "http://127.0.0.1:7808")
REF = os.environ.get("BABU_REF", "inspektor/ws-christoph0711.io/babu")
PAT_PFAD = Path(os.environ.get("BABU_PUSH_PAT", str(Path.home() / "gitchain-eingang" / ".pat_babu")))
REMOTE = os.environ.get("BABU_BOX_REMOTE", f"{GATEWAY}/git/{REF}.git")


class SchreibFehler(RuntimeError):
    pass


class NichtsZuLoeschen(SchreibFehler):
    """Die Datei war schon weg — kein Grund für einen leeren Commit."""


# Ein Schreiber zur Zeit je Box — das Schloss liegt in `Box.schloss`,
# siehe Modul-Kopf.

# Übergangsschale: bis Phase 3 gibt es genau EINE Box, und Aufrufe ohne
# Box-Argument sind deshalb eindeutig. `_mit_box` schiebt sie dann selbst
# davor. Mit der zweiten echten Box muss das weg — dann ist ein fehlendes
# Argument kein Weglassen mehr, sondern ein stiller Schreibfehler in die
# falsche Box.
_FEHLT = object()


def _mit_box(erstes, rest: tuple) -> tuple:
    werte = [w for w in rest if w is not _FEHLT]
    if isinstance(erstes, bx.Box):
        return erstes, werte
    return bx.default_box(), [erstes, *werte]


def _pat_umgebung() -> dict[str, str]:
    env = dict(os.environ)
    try:
        pat = PAT_PFAD.read_text().strip()
    except FileNotFoundError:
        return env  # Tests: Remote ohne Auth (file://)
    env.update({
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Bearer {pat}",
    })
    return env


def _git(*args: str, box: "bx.Box", timeout: int = 30) -> subprocess.CompletedProcess:
    """Ein git-Aufruf in der Arbeitskopie DIESER Box.

    Die Box steht hinten und nur als Schlüsselwort: vorne bleiben damit die
    git-Argumente, so wie sie hier immer standen.
    """
    return subprocess.run(["git", "-C", str(box.klon), *args],
                          capture_output=True, text=True, timeout=timeout,
                          env=_pat_umgebung())


def _bereit(box: "bx.Box") -> None:
    if not (box.klon / ".git").exists():
        box.klon.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "clone", box.remote, str(box.klon)],
                           capture_output=True, text=True, timeout=60,
                           env=_pat_umgebung())
        if r.returncode != 0:
            raise SchreibFehler(f"Clone fehlgeschlagen: {r.stderr.strip()[:200]}")
        _git("config", "user.name", "babu-portal", box=box)
        _git("config", "user.email", "portal@gitchain.local", box=box)
    r = _git("fetch", "origin", box=box, timeout=30)
    if r.returncode != 0:
        raise SchreibFehler(f"Fetch fehlgeschlagen: {r.stderr.strip()[:200]}")
    r = _git("reset", "--hard", "origin/main", box=box)
    if r.returncode != 0:
        raise SchreibFehler(f"Reset fehlgeschlagen: {r.stderr.strip()[:200]}")


def _pfad_pruefen(pfad: str) -> None:
    # Ein führender Schrägstrich wäre der gefährlichste Fall: `KLON / "/etc/x"`
    # ist in pathlib schlicht "/etc/x" — der Klon fällt weg.
    if (not re.match(r"^[A-Za-z0-9._/ -]{1,200}$", pfad) or ".." in pfad
            or Path(pfad).is_absolute()):
        raise SchreibFehler("ungültiger Pfad")


def _commit_und_push(box: "bx.Box", vormerken, nachricht: str, autor_un: str) -> str:
    """Der gemeinsame Ablauf von Schreiben und Löschen.

    `vormerken()` läuft im frisch zurückgesetzten Klon und legt an oder
    entfernt; alles Weitere — Schloss, Commit, Push, der eine Retry — ist für
    beide gleich, damit es nicht zwei Wahrheiten über den Schreibpfad gibt.
    """
    autor = f"{autor_un} <portal@gitchain.local>"
    letzter_fehler = ""
    with box.schloss:
        for versuch in (1, 2):
            _bereit(box)
            vormerken()
            r = _git("commit", "-m", nachricht, "--author", autor, box=box)
            if r.returncode != 0:
                raise SchreibFehler(f"Commit fehlgeschlagen: {r.stderr.strip()[:200]}")
            p = _git("push", "origin", "main", box=box, timeout=30)
            if p.returncode == 0:
                h = _git("rev-parse", "--short", "HEAD", box=box)
                return h.stdout.strip()
            letzter_fehler = p.stderr.strip()[:200]
            time.sleep(0.7)  # Watcher-Push abklingen lassen, dann frisch aufsetzen
    raise SchreibFehler(f"Push fehlgeschlagen (auch nach Retry): {letzter_fehler}")


def schreiben(box: "bx.Box", rel_pfad: str | dict[str, bytes] = _FEHLT,
              inhalt: bytes | None = _FEHLT, nachricht: str = _FEHLT,
              autor_un: str = _FEHLT) -> str:
    """Datei(en) in DIESE Box committen + pushen; gibt den Kurz-Hash zurück.

    Entweder (pfad, inhalt) für eine Datei oder ein dict {pfad: bytes} für
    mehrere Dateien in EINEM Commit (z. B. Dokument + Meta-Sidecar). Ein
    Push-Retry. Ohne führendes Box-Argument greift die Default-Box (siehe
    `_mit_box`).
    """
    box, werte = _mit_box(box, (rel_pfad, inhalt, nachricht, autor_un))
    rel_pfad, inhalt, nachricht, autor_un = werte
    dateien = rel_pfad if isinstance(rel_pfad, dict) else {rel_pfad: inhalt}
    for pfad in dateien:
        _pfad_pruefen(pfad)

    def anlegen() -> None:
        for pfad, daten in dateien.items():
            ziel = box.klon / pfad
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(daten)
            a = _git("add", pfad, box=box)
            if a.returncode != 0:
                raise SchreibFehler(f"Vormerken fehlgeschlagen: {a.stderr.strip()[:200]}")

    return _commit_und_push(box, anlegen, nachricht, autor_un)


def loeschen(box: "bx.Box", pfade: list[str] = _FEHLT, nachricht: str = _FEHLT,
             autor_un: str = _FEHLT) -> str:
    """Datei(en) entfernen — als eigener Commit, der die Historie behält.

    Der aktuelle Stand zeigt sie danach nicht mehr; nachvollziehbar bleibt,
    dass es sie gab. Pfade, die es nicht (mehr) gibt, werden übergangen —
    zweimal Löschen ist harmlos. Ist am Ende gar nichts dabei, meldet sich
    `NichtsZuLoeschen`, statt einen leeren Commit zu bauen.
    """
    box, werte = _mit_box(box, (pfade, nachricht, autor_un))
    pfade, nachricht, autor_un = werte
    for pfad in pfade:
        _pfad_pruefen(pfad)

    def entfernen() -> None:
        entfernt = 0
        for pfad in pfade:
            r = _git("rm", "-q", "--ignore-unmatch", "--", pfad, box=box)
            if r.returncode != 0:
                raise SchreibFehler(f"Entfernen fehlgeschlagen: {r.stderr.strip()[:200]}")
            entfernt += 1
        stand = _git("diff", "--cached", "--name-only", box=box)
        if not (stand.stdout or "").strip():
            raise NichtsZuLoeschen("nichts zu löschen")

    return _commit_und_push(box, entfernen, nachricht, autor_un)


NAME_MAX = 80


def _mitte_kuerzen(name: str, hoechstens: int = NAME_MAX) -> str:
    """Zu lange Namen in der MITTE kürzen — Anfang und Endung bleiben.

    Vorher stand hier `[-80:]`: das behielt das Ende und warf den Anfang
    weg. Vorne steht aber, worum es geht. Aus
    „Rechnung-Friseurbedarf-Grosshandel-…-2026-03.pdf" wurde
    „…-2026-03.pdf", und in einer Liste solcher Belege sah jede Zeile
    gleich aus — genau die Namen, die eine Ablage lesbar machen, fielen als
    Erstes weg.
    """
    if len(name) <= hoechstens:
        return name
    stamm, punkt, endung = name.rpartition(".")
    if punkt and 0 < len(endung) <= 8 and stamm:
        endung = "." + endung
    else:
        stamm, endung = name, ""
    platz = hoechstens - len(endung) - 3          # drei Punkte als Auslassung
    if platz < 8:                                 # absurd lange „Endung"
        return name[:hoechstens]
    vorn = (platz + 1) // 2
    return stamm[:vorn] + "..." + stamm[len(stamm) - (platz - vorn):] + endung


def beleg_dateiname(original: str) -> str:
    """Server-Namensschema JJJJMMTT-HHMMSS-<hex>-<name> wie beim Eingang."""
    stamm = _mitte_kuerzen(re.sub(r"[^A-Za-z0-9._-]", "_", original)) or "beleg"
    zeit = time.strftime("%Y%m%d-%H%M%S")
    return f"{zeit}-{secrets.token_hex(3)}-{stamm}"
