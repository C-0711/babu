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

GitChain-Standard (27.09.2026): Ziel ist der neue Dienst (hostPort :3361 auf
der H200v, intern, am Tunnel vorbei), angemeldet als Dienstkonto `svc-babu`
mit dessen gcpat-Token aus `.pat_babu` (je Aufruf frisch gelesen — Rotation
ohne Neustart). Git Smart HTTP nimmt dort heute Basic an (Benutzer =
Dienstkonto, Passwort = Token); `BABU_GIT_AUTH=bearer` schaltet um, sobald der
Dienst Bearer auch für git annimmt. Neue Boxen entstehen per Push-to-create
(`box_anlegen`) in `babu/<betrieb>/belege`. Der Token-Wert erscheint nie in
einer Meldung, einem Log oder einer URL.
"""
import base64
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

import box as bx

KLON = Path(os.environ.get("BABU_BOX_KLON", str(Path.home() / "babu-web" / "box")))
# Der neue GitChain-Dienst (hostPort auf der H200v). Bis 27.09.2026 stand hier
# das alte Gateway insp-app :7808 — Rückweg per Umgebung, nicht per Code.
GATEWAY = os.environ.get("BABU_GATEWAY", "http://127.0.0.1:3361").rstrip("/")
# Box des Einzelbetriebs (Mandant 2). Namensraum nach dem Standard:
# babu/<betrieb>/belege — <betrieb> ist der bisherige Box-Kurzname.
REF = os.environ.get("BABU_REF", "babu/babu/belege")
PAT_PFAD = Path(os.environ.get("BABU_PUSH_PAT", str(Path.home() / "gitchain-eingang" / ".pat_babu")))
REMOTE = os.environ.get("BABU_BOX_REMOTE", f"{GATEWAY}/git/{REF}.git")
# Wer sich bei git anmeldet: das Dienstkonto der Integration.
GIT_NUTZER = os.environ.get("BABU_GIT_NUTZER", "svc-babu")
# basic (heute) | bearer (sobald der Dienst Bearer für git annimmt, D1).
GIT_AUTH = os.environ.get("BABU_GIT_AUTH", "basic").strip().lower()
# Die Form eines Box-Verweises nach dem Standard.
BOX_REF_RE = re.compile(r"^babu/[a-z0-9][a-z0-9._-]{0,79}/belege$")


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


def _auth_kopf(pat: str) -> str:
    """Der Authorization-Kopf für git — Basic (Dienstkonto:Token) oder Bearer."""
    if GIT_AUTH == "bearer":
        return f"Authorization: Bearer {pat}"
    paar = base64.b64encode(f"{GIT_NUTZER}:{pat}".encode()).decode()
    return f"Authorization: Basic {paar}"


def _pat_umgebung() -> dict[str, str]:
    env = dict(os.environ)
    # Nie nachfragen, nie einen Schlüsselbund befragen: fehlt die Anmeldung,
    # soll git sofort mit einer klaren Meldung scheitern statt zu warten.
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        pat = PAT_PFAD.read_text().strip()
    except FileNotFoundError:
        return env  # Tests: Remote ohne Auth (file://)
    # Eine vorhandene GIT_CONFIG_*-Liste (z. B. safe.directory aus compose)
    # bleibt erhalten; der Auth-Kopf kommt dahinter.
    n = int(env.get("GIT_CONFIG_COUNT", "0") or "0")
    env.update({
        f"GIT_CONFIG_KEY_{n}": "http.extraHeader",
        f"GIT_CONFIG_VALUE_{n}": _auth_kopf(pat),
        f"GIT_CONFIG_KEY_{n + 1}": "credential.helper",
        f"GIT_CONFIG_VALUE_{n + 1}": "",
        "GIT_CONFIG_COUNT": str(n + 2),
    })
    return env


def git_fehler_text(stderr: str | None) -> str:
    """Eine git-Fehlermeldung, die ein Mensch versteht — ohne Geheimnisse.

    git gibt den Auth-Kopf nie aus; trotzdem wird alles, was wie ein Token
    aussieht, geschwärzt, bevor es in ein Log oder eine Ausnahme geht.
    """
    roh = re.sub(r"gcpat-[A-Za-z0-9_-]+", "gcpat-***", (stderr or "").strip())
    if re.search(r"\b401\b|Authentication|could not read Username|terminal prompts disabled",
                 roh):
        return ("GitChain hat die Anmeldung abgelehnt (401) — Token in "
                f"{PAT_PFAD.name} ungültig, abgelaufen oder widerrufen?")
    if re.search(r"\b403\b", roh):
        return "GitChain verweigert den Zugriff (403) — Namensraum nicht freigegeben?"
    if re.search(r"\b404\b|not found", roh, re.I):
        return ("Box bei GitChain nicht gefunden oder kein Zugriff (404) — Verweis, "
                "Namensraum-Freigabe und Token prüfen.")
    return roh[:200]


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
                           capture_output=True, text=True,
                           timeout=int(os.environ.get("BABU_LESE_KLON_FRIST", "900")),
                           env=_pat_umgebung())
        if r.returncode != 0:
            raise SchreibFehler(f"Clone fehlgeschlagen: {git_fehler_text(r.stderr)}")
        _git("config", "user.name", "babu-portal", box=box)
        _git("config", "user.email", "portal@gitchain.local", box=box)
    else:
        # Umzug des Remotes (z. B. altes Gateway :7808 → neuer Dienst): die
        # Arbeitskopie folgt der Konfiguration, nicht ihrer Erinnerung.
        url = _git("remote", "get-url", "origin", box=box)
        if url.stdout.strip() != box.remote:
            _git("remote", "set-url", "origin", box.remote, box=box)
    r = _git("fetch", "origin", box=box, timeout=30)
    if r.returncode != 0:
        raise SchreibFehler(f"Fetch fehlgeschlagen: {git_fehler_text(r.stderr)}")
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
    kurz = None
    try:
        with box.schloss:
            for versuch in (1, 2):
                _bereit(box)
                vormerken()
                r = _git("commit", "-m", nachricht, "--author", autor, box=box)
                if r.returncode != 0:
                    raise SchreibFehler(f"Commit fehlgeschlagen: {r.stderr.strip()[:200]}")
                p = _git("push", "origin", "main", box=box, timeout=30)
                if p.returncode == 0:
                    kurz = _git("rev-parse", "--short", "HEAD", box=box).stdout.strip()
                    break
                letzter_fehler = git_fehler_text(p.stderr)
                time.sleep(0.7)  # Watcher-Push abklingen lassen, dann frisch aufsetzen
    except SchreibFehler as ex:
        print(f"[box] {box.ref}: {ex}", flush=True)
        raise
    if kurz is None:
        fehler = SchreibFehler(f"Push fehlgeschlagen (auch nach Retry): {letzter_fehler}")
        print(f"[box] {box.ref}: {fehler}", flush=True)
        raise fehler
    # Der eigene Commit soll beim nächsten Lesen schon da sein — der
    # Lesespiegel zieht sofort nach (im Modus `store` ein No-op). Scheitert
    # das, ist der Beleg trotzdem gespeichert; der Spiegel holt ihn später.
    # Ohne zu warten: zieht gerade jemand nach (oder läuft der Erstklon),
    # vermerkt `lesestand_holen` nur, dass der nächste Leser holen soll.
    bx.lesestand_holen(box, sofort=True, warten=False)
    return kurz


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


def box_da(ref: str) -> tuple[bool, str]:
    """Gibt es die Box beim Dienst, und welchen Stand hat sie?

    `(True, "<sha12>")`, `(True, "noch ohne Belege")` für ein Repo ohne
    Commits, `(False, "<Grund>")` sonst. Fragt per `git ls-remote` mit dem
    Token des Schreibwegs — also genau so, wie babu die Box später benutzt.
    """
    import box as _bx  # noqa: PLC0415
    remote = _bx.remote_aus_ref(ref)
    try:
        r = subprocess.run(["git", "ls-remote", remote, "HEAD", "refs/heads/main"],
                           capture_output=True, text=True, timeout=30,
                           env=_pat_umgebung())
    except (OSError, subprocess.SubprocessError) as ex:
        return False, f"nicht erreichbar ({ex.__class__.__name__})"
    if r.returncode != 0:
        return False, git_fehler_text(r.stderr)
    zeilen = [z.split() for z in r.stdout.splitlines() if z.strip()]
    main = next((z[0] for z in zeilen if len(z) == 2 and z[1] == "refs/heads/main"), None)
    return True, (main[:12] if main else "noch ohne Belege")


def box_anlegen(ref: str, anzeige: str = "") -> str:
    """Neue Belegbox per Push-to-create im Namensraum der Integration.

    Legt einen ersten Commit mit `.0711/container.json` an und pusht ihn als
    `main` nach `<GATEWAY>/git/<ref>.git`; der Dienst erzeugt das Repo dabei
    selbst (privat, Eigentümer = Dienstkonto). Idempotent: hat die Box schon
    einen Stand, passiert nichts. Gibt den Kurz-Hash des Stands zurück.
    """
    ref = (ref or "").strip().strip("/")
    if not BOX_REF_RE.match(ref) or ".." in ref:
        raise SchreibFehler(f"„{ref}“ ist kein Box-Verweis der Form babu/<betrieb>/belege")
    da, stand = box_da(ref)
    if da and stand != "noch ohne Belege":
        return stand[:7]
    typ, namensraum, kennung = ref.split("/")
    manifest = {"type": typ, "namespace": namensraum, "identifier": kennung,
                "name": anzeige or f"Belegbox {namensraum}",
                "visibility": "private"}
    import box as _bx  # noqa: PLC0415
    remote = _bx.remote_aus_ref(ref)
    with tempfile.TemporaryDirectory(prefix="babu-box-") as tmp:
        def g(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
            return subprocess.run(["git", "-C", tmp, *args], capture_output=True,
                                  text=True, timeout=timeout, env=_pat_umgebung())
        g("init", "-q", "-b", "main")
        (Path(tmp) / ".0711").mkdir()
        (Path(tmp) / ".0711" / "container.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        g("add", ".0711/container.json")
        r = g("-c", "user.name=babu-portal", "-c", "user.email=portal@gitchain.local",
              "commit", "-q", "-m", f"box: angelegt ({ref})")
        if r.returncode != 0:
            raise SchreibFehler(f"Commit fehlgeschlagen: {r.stderr.strip()[:200]}")
        p = g("push", "-q", remote, "HEAD:refs/heads/main", timeout=60)
        if p.returncode != 0:
            raise SchreibFehler(f"Box anlegen fehlgeschlagen: {git_fehler_text(p.stderr)}")
        kurz = g("rev-parse", "--short", "HEAD").stdout.strip()
    # Der Dienst registriert den neuen Container im Hintergrund (Eigentümer,
    # Rechte); bis dahin meldet er ihn Lesenden als „not found". Erst zurück,
    # wenn babu die Box auch lesen kann — sonst scheitert die Prüfung direkt
    # danach an einem Rennen, nicht an einem Fehler.
    for _ in range(int(os.environ.get("BABU_BOX_ANLEGEN_WARTEN", "30"))):
        if box_da(ref)[0]:
            break
        time.sleep(0.5)
    return kurz


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
