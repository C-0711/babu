"""boxschreiber — Schreibpfad des Portals in die GitChain-Belegbox.

Eigener Clone (~/babu-web/box), NIE die Arbeitskopie des Watchers
(~/belegreview/babu — dessen `reset --hard` frisst lokale Commits) und nie
der Bare-Store direkt. Muster wie review_watcher.py: fetch + reset --hard →
Datei schreiben → Commit mit Autor = angemeldete Nutzerin → Push via Gateway
mit Service-PAT im Header (Wert ohne Newline — bekannte Falle Nr. 2).
Push-Rennen mit dem Watcher (15-s-Takt): genau ein Retry, sonst Fehler.

Der Klon ist EINE Arbeitskopie mit EINEM Git-Index — Portal-Requests und
Hintergrund-Jobs (Vertrag lesen, Brief erklären, Salon-Check) schreiben aber
nebenläufig. Deshalb läuft `schreiben()` komplett unter einem Schloss: sonst
räumt der `reset --hard` des einen Threads dem anderen die Datei aus dem
Index, und der Commit trägt am Ende den falschen Inhalt unter fremdem Namen.
"""
import os
import re
import secrets
import subprocess
import threading
import time
from pathlib import Path

KLON = Path(os.environ.get("BABU_BOX_KLON", str(Path.home() / "babu-web" / "box")))
GATEWAY = os.environ.get("BABU_GATEWAY", "http://127.0.0.1:7808")
REF = os.environ.get("BABU_REF", "inspektor/ws-christoph0711.io/babu")
PAT_PFAD = Path(os.environ.get("BABU_PUSH_PAT", str(Path.home() / "gitchain-eingang" / ".pat_babu")))
REMOTE = os.environ.get("BABU_BOX_REMOTE", f"{GATEWAY}/git/{REF}.git")


class SchreibFehler(RuntimeError):
    pass


class NichtsZuLoeschen(SchreibFehler):
    """Die Datei war schon weg — kein Grund für einen leeren Commit."""


# Ein Schreiber zur Zeit — siehe Modul-Kopf.
_SCHLOSS = threading.Lock()


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


def _git(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(KLON), *args],
                          capture_output=True, text=True, timeout=timeout,
                          env=_pat_umgebung())


def _bereit() -> None:
    if not (KLON / ".git").exists():
        KLON.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "clone", REMOTE, str(KLON)],
                           capture_output=True, text=True, timeout=60,
                           env=_pat_umgebung())
        if r.returncode != 0:
            raise SchreibFehler(f"Clone fehlgeschlagen: {r.stderr.strip()[:200]}")
        _git("config", "user.name", "babu-portal")
        _git("config", "user.email", "portal@gitchain.local")
    r = _git("fetch", "origin", timeout=30)
    if r.returncode != 0:
        raise SchreibFehler(f"Fetch fehlgeschlagen: {r.stderr.strip()[:200]}")
    r = _git("reset", "--hard", "origin/main")
    if r.returncode != 0:
        raise SchreibFehler(f"Reset fehlgeschlagen: {r.stderr.strip()[:200]}")


def _pfad_pruefen(pfad: str) -> None:
    # Ein führender Schrägstrich wäre der gefährlichste Fall: `KLON / "/etc/x"`
    # ist in pathlib schlicht "/etc/x" — der Klon fällt weg.
    if (not re.match(r"^[A-Za-z0-9._/ -]{1,200}$", pfad) or ".." in pfad
            or Path(pfad).is_absolute()):
        raise SchreibFehler("ungültiger Pfad")


def _commit_und_push(vormerken, nachricht: str, autor_un: str) -> str:
    """Der gemeinsame Ablauf von Schreiben und Löschen.

    `vormerken()` läuft im frisch zurückgesetzten Klon und legt an oder
    entfernt; alles Weitere — Schloss, Commit, Push, der eine Retry — ist für
    beide gleich, damit es nicht zwei Wahrheiten über den Schreibpfad gibt.
    """
    autor = f"{autor_un} <portal@gitchain.local>"
    letzter_fehler = ""
    with _SCHLOSS:
        for versuch in (1, 2):
            _bereit()
            vormerken()
            r = _git("commit", "-m", nachricht, "--author", autor)
            if r.returncode != 0:
                raise SchreibFehler(f"Commit fehlgeschlagen: {r.stderr.strip()[:200]}")
            p = _git("push", "origin", "main", timeout=30)
            if p.returncode == 0:
                h = _git("rev-parse", "--short", "HEAD")
                return h.stdout.strip()
            letzter_fehler = p.stderr.strip()[:200]
            time.sleep(0.7)  # Watcher-Push abklingen lassen, dann frisch aufsetzen
    raise SchreibFehler(f"Push fehlgeschlagen (auch nach Retry): {letzter_fehler}")


def schreiben(rel_pfad: str | dict[str, bytes], inhalt: bytes | None,
              nachricht: str, autor_un: str) -> str:
    """Datei(en) committen + pushen; gibt den Kurz-Hash zurück. Ein Push-Retry.

    Entweder (pfad, inhalt) für eine Datei oder ein dict {pfad: bytes} für
    mehrere Dateien in EINEM Commit (z. B. Dokument + Meta-Sidecar).
    """
    dateien = rel_pfad if isinstance(rel_pfad, dict) else {rel_pfad: inhalt}
    for pfad in dateien:
        _pfad_pruefen(pfad)

    def anlegen() -> None:
        for pfad, daten in dateien.items():
            ziel = KLON / pfad
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(daten)
            a = _git("add", pfad)
            if a.returncode != 0:
                raise SchreibFehler(f"Vormerken fehlgeschlagen: {a.stderr.strip()[:200]}")

    return _commit_und_push(anlegen, nachricht, autor_un)


def loeschen(pfade: list[str], nachricht: str, autor_un: str) -> str:
    """Datei(en) entfernen — als eigener Commit, der die Historie behält.

    Der aktuelle Stand zeigt sie danach nicht mehr; nachvollziehbar bleibt,
    dass es sie gab. Pfade, die es nicht (mehr) gibt, werden übergangen —
    zweimal Löschen ist harmlos. Ist am Ende gar nichts dabei, meldet sich
    `NichtsZuLoeschen`, statt einen leeren Commit zu bauen.
    """
    for pfad in pfade:
        _pfad_pruefen(pfad)

    def entfernen() -> None:
        entfernt = 0
        for pfad in pfade:
            r = _git("rm", "-q", "--ignore-unmatch", "--", pfad)
            if r.returncode != 0:
                raise SchreibFehler(f"Entfernen fehlgeschlagen: {r.stderr.strip()[:200]}")
            entfernt += 1
        stand = _git("diff", "--cached", "--name-only")
        if not (stand.stdout or "").strip():
            raise NichtsZuLoeschen("nichts zu löschen")

    return _commit_und_push(entfernen, nachricht, autor_un)


def beleg_dateiname(original: str) -> str:
    """Server-Namensschema JJJJMMTT-HHMMSS-<hex>-<name> wie beim Eingang."""
    stamm = re.sub(r"[^A-Za-z0-9._-]", "_", original)[-80:] or "beleg"
    zeit = time.strftime("%Y%m%d-%H%M%S")
    return f"{zeit}-{secrets.token_hex(3)}-{stamm}"
