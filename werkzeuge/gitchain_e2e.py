#!/usr/bin/env python3
"""gitchain_e2e — babu gegen einen ECHTEN GitChain-Dienst (GitChain-Standard 27.09.2026).

Gedacht für den Wegwerf-Dienst, nie für den Live-Dienst: das Skript legt Boxen
an und schreibt Belege hinein. babu-web läuft dabei als eigener Prozess
(uvicorn, freier Port, alle Daten in einem Temp-Ordner) — der Weg ist also
derselbe wie im Betrieb: HTTP an babu-web → git push beim Dienst → Lesen aus
dem eigenen Lesespiegel.

Geprüft wird:
  1. Push-to-create der Default-Box (boxschreiber.box_anlegen)
  2. betrieb_anlegen --nur-box --box-anlegen für einen zweiten Betrieb
     (Mandant box_ausstehend → Box beim Dienst → Mandant aktiv)
  3. Token-Anmeldung eines Menschen über /v1/user (/api/anmelden)
     − falsches Token → 401, Dienstkonto-Token → 401
  4. Upload über /ablage (Bearer eines Menschen) → Commit beim Dienst, Autor
     = der Mensch, geschrieben vom Dienstkonto
  5. Lesen: /api/belege zeigt den Beleg, `stand` = HEAD beim Dienst; ein
     fremder Commit erscheint nach dem Nachziehen
  6. Negativkontrollen: falsches Schreib-Token → 502 mit klarer Meldung im
     Log, kein Absturz, /healthz bleibt 200; Box in fremdem Namensraum und in
     Pushes außerhalb babu/ (belegwerk/…, babux/…) und in einen fremden Tenant
     werden VOM DIENST abgewiesen; das Token eines Menschen (Leser) kann nicht
     in die Box pushen (Antwort des Dienstes geprüft). Mit --d1: ein neuer
     Betrieb unter babu/* ist ohne vorher angelegten Tenant anlegbar; ohne
     --d1 steht diese Erwartung als „offen bis D1“ im Ergebnis
  7. Kein Token-Wert in Ausgaben und Logs

Aufruf (Tokens nur als Dateien, 0600):
    python werkzeuge/gitchain_e2e.py --dienst http://127.0.0.1:3471 \\
        --dienst-token ~/…/token-svc-babu-e2e --dienst-konto svc-babu-e2e \\
        --mensch-token ~/…/token-t-babu-mensch --mensch t-babu-mensch \\
        --box babu/babu-e2e-7/belege --zweite-box babu/salon-e2e-8/belege \\
        --fremde-box babu/babu-fremd/belege --ergebnis /pfad/ergebnis.json

Rückgabe 0 = alle Prüfungen bestanden, 1 = mindestens eine nicht.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

WURZEL = Path(__file__).resolve().parent.parent
BELEGREVIEW = WURZEL / "server" / "belegreview"
PRUEFUNGEN: list[dict] = []
OFFEN: list[dict] = []   # Erwartungen, die erst gegen einen D1-Dienst prüfbar sind


def pruefe(name: str, ok: bool, beleg: str = "") -> bool:
    PRUEFUNGEN.append({"name": name, "ok": bool(ok), "beleg": beleg})
    print(f"{'OK  ' if ok else 'FEHL'} {name}{(' — ' + beleg) if beleg else ''}", flush=True)
    return ok


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def git_env(konto: str, token: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG_")}
    paar = base64.b64encode(f"{konto}:{token}".encode()).decode()
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "http.extraHeader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Basic {paar}",
                "GIT_CONFIG_KEY_1": "credential.helper", "GIT_CONFIG_VALUE_1": ""})
    return env


def git(args: list[str], env: dict, cwd: Path | None = None, timeout: int = 120):
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=timeout)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dienst", required=True)
    ap.add_argument("--dienst-token", required=True, type=Path)
    ap.add_argument("--dienst-konto", required=True)
    ap.add_argument("--mensch-token", required=True, type=Path)
    ap.add_argument("--mensch", required=True)
    ap.add_argument("--box", required=True)
    ap.add_argument("--zweite-box", required=True)
    ap.add_argument("--fremde-box", required=True)
    ap.add_argument("--ergebnis", type=Path)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--d1", action="store_true",
                    help="Dienst mit D1 (Dienstkonten, Namensraum babu/*): auch Push-to-create "
                         "für einen neuen Betrieb ohne Tenant muss gelingen")
    a = ap.parse_args()

    dienst = a.dienst.rstrip("/")
    svc_tok = a.dienst_token.read_text().strip()
    mensch_tok = a.mensch_token.read_text().strip()
    geheim = [svc_tok, mensch_tok]
    tmp = Path(tempfile.mkdtemp(prefix="babu-e2e-"))
    (tmp / "pat").mkdir(mode=0o700)
    pat = tmp / "pat" / ".pat_babu"
    shutil.copyfile(a.dienst_token, pat)
    pat.chmod(0o600)
    port = freier_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG_")}
    env.update({
        "HOME": str(tmp), "PYTHONPATH": str(BELEGREVIEW),
        "BABU_GATEWAY": dienst, "GITCHAIN_ID_HOST": dienst, "BABU_REF": a.box,
        "BABU_PUSH_PAT": str(pat), "BABU_GIT_NUTZER": a.dienst_konto, "BABU_GIT_AUTH": "basic",
        "BABU_LESEN": "klon", "BABU_LESE_WURZEL": str(tmp / "lesen"), "BABU_LESE_TTL": "0",
        "BABU_BOX_KLON": str(tmp / "klon"), "BABU_BOX_KLON_WURZEL": str(tmp / "boxen"),
        "BABU_PORTAL_DB": str(tmp / "portal.db"), "BABU_SESSION_GEHEIMNIS": str(tmp / ".geheimnis"),
        "BABU_ERLAUBT": a.mensch, "BABU_NACHLESE": "0", "BABU_INDEX_TTL": "0",
        "BABU_ORIGIN": f"http://127.0.0.1:{port}", "BABU_PORT": str(port),
        "BABU_SEITE": str(WURZEL / "server" / "babu-web" / "index.html"),
        "BABU_ABSCHLUSS_TMP": str(tmp / "abschluss"),
        "GEMMA_API": "http://127.0.0.1:9/v1/chat/completions",
        "EMBED_API": "http://127.0.0.1:9/v1/embeddings",
        "GIT_TERMINAL_PROMPT": "0",
    })
    svc_git = git_env(a.dienst_konto, svc_tok)
    mensch_git = git_env(a.mensch, mensch_tok)

    def py(code: str) -> subprocess.CompletedProcess:
        return subprocess.run([a.python, "-c", code], env=env, cwd=BELEGREVIEW,
                              capture_output=True, text=True, timeout=300)

    # 1. Default-Box per Push-to-create
    r = py(f"import boxschreiber; print(boxschreiber.box_anlegen({a.box!r}, 'babu E2E'))")
    ls = git(["ls-remote", f"{dienst}/git/{a.box}.git", "refs/heads/main"], svc_git)
    pruefe("Box per Push-to-create angelegt", r.returncode == 0 and ls.returncode == 0
           and ls.stdout.strip() != "", f"{a.box} main={ls.stdout[:12]}")
    r2 = py(f"import boxschreiber; print(boxschreiber.box_anlegen({a.box!r}))")
    ls2 = git(["ls-remote", f"{dienst}/git/{a.box}.git", "refs/heads/main"], svc_git)
    pruefe("Box anlegen ist idempotent", r2.returncode == 0 and ls2.stdout == ls.stdout)

    # 2. Zweiter Betrieb: Konto + Mandant in babus DB, dann das Werkzeug
    r = py("import babu_web as bw, mandanten\n"
           "bw.nutzer_anlegen('inhaber@salon-e2e.test','Inhaberin','Salon E2E','salon',"
           "passwort='ein-langes-passwort-e2e',box=True)\n"
           "bw.nutzer_anlegen('buero@kanzlei-e2e.test','Buero','Kanzlei E2E','kanzlei',"
           "passwort='ein-langes-passwort-e2e',box=True)\n"
           "k=mandanten.kanzlei_anlegen('Kanzlei E2E','buero@kanzlei-e2e.test')\n"
           "print(mandanten.mandant_anlegen(k,'Salon E2E','inhaber@salon-e2e.test'))")
    mid = r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else "?"
    w = subprocess.run([a.python, str(WURZEL / "werkzeuge" / "betrieb_anlegen.py"), "--nur-box",
                        "--box-anlegen", "--email", "inhaber@salon-e2e.test",
                        "--box-ref", a.zweite_box], env=env, capture_output=True, text=True,
                       timeout=300)
    st = py(f"import babu_web, mandanten; m=mandanten.mandant_holen({mid}); "
            f"print(m['status'], m['box_ref'])") if mid != "?" else None
    klon2 = tmp / "pruef-zweite"
    c2 = git(["clone", "-q", f"{dienst}/git/{a.zweite_box}.git", str(klon2)], svc_git)
    mf = (klon2 / ".0711" / "container.json")
    pruefe("betrieb_anlegen --nur-box --box-anlegen: Mandant aktiv, Box beim Dienst",
           w.returncode in (0, 1) and st is not None and st.stdout.strip() == f"aktiv {a.zweite_box}"
           and c2.returncode == 0 and mf.is_file() and '"type": "babu"' in mf.read_text(),
           f"rc={w.returncode} stand={(st.stdout.strip() if st else '?')}"
           + ("" if w.returncode in (0, 1) and st and st.stdout.strip().startswith("aktiv") else
              f" | anlegen: {r.stdout.strip()[-80:]} {r.stderr.strip()[-200:]}"
              f" | werkzeug: {w.stdout.strip()[-300:]} {w.stderr.strip()[-300:]}"))

    # 3. babu-web starten
    log = open(tmp / "babu-web.log", "w")
    proz = subprocess.Popen([a.python, "babu_web.py"], cwd=BELEGREVIEW, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    basis = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                if requests.get(basis + "/healthz", timeout=2).status_code in (200, 503):
                    break
            except requests.RequestException:
                time.sleep(0.5)
        # Lesespiegel entsteht im Hintergrund beim Start
        spiegel = tmp / "lesen" / f"{a.box}.git"
        for _ in range(60):
            if (spiegel / "HEAD").is_file():
                break
            time.sleep(0.5)
        pruefe("Lesespiegel beim Start angelegt", (spiegel / "HEAD").is_file(), str(spiegel.relative_to(tmp)))

        # 4. Anmeldung per Zugangscode (/v1/user)
        s = requests.Session()
        h = {"Origin": basis}
        r = s.post(basis + "/api/anmelden", json={"pat": mensch_tok}, headers=h, timeout=20)
        pruefe("Token-Anmeldung Mensch über /v1/user → 200", r.status_code == 200
               and r.json().get("un") == a.mensch.lower(), f"{r.status_code} {r.text[:60]}")
        r = requests.post(basis + "/api/anmelden", json={"pat": "gcpat-falsch" + "0" * 30},
                          headers=h, timeout=20)
        pruefe("falsches Token → 401", r.status_code == 401, f"{r.status_code} {r.text[:60]}")
        r = requests.post(basis + "/api/anmelden", json={"pat": svc_tok}, headers=h, timeout=20)
        pruefe("Dienstkonto-Token als Mensch → 401", r.status_code == 401, f"{r.status_code}")

        # 5. Upload über /ablage
        from PIL import Image  # noqa: PLC0415
        import io  # noqa: PLC0415
        buf = io.BytesIO()
        Image.new("RGB", (64, 48), (200, 30, 90)).save(buf, "JPEG")
        bild = buf.getvalue() + os.urandom(16)  # nie eine Dublette eines früheren Laufs
        auth = {"Authorization": f"Bearer {mensch_tok}"}
        r = requests.post(basis + "/ablage", headers=auth, timeout=60,
                          files={"file": ("e2e-bon.jpg", bild, "image/jpeg")})
        ok = r.status_code == 200 and r.json().get("ok")
        datei = r.json().get("datei", "") if ok else ""
        pruefe("Upload /ablage → Commit beim Dienst", bool(ok), f"{r.status_code} {datei} commit={r.json().get('commit') if ok else r.text[:80]}")
        pruef = tmp / "pruef"
        c = git(["clone", "-q", f"{dienst}/git/{a.box}.git", str(pruef)], svc_git)
        da = c.returncode == 0 and datei and (pruef / datei).is_file() \
            and (pruef / datei).read_bytes() == bild
        autor = git(["-C", str(pruef), "log", "-1", "--format=%an|%s"], svc_git).stdout.strip()
        pruefe("Beleg liegt byte-gleich beim Dienst, Autor = Mensch", bool(da)
               and autor.startswith(a.mensch.lower() + "|aufnahme:"), autor)

        # 6. Lesen aus dem Spiegel
        r = requests.get(basis + "/api/belege", headers=auth, timeout=30)
        kopf = git(["ls-remote", f"{dienst}/git/{a.box}.git", "refs/heads/main"],
                   svc_git).stdout.split()[0]
        stamm = Path(datei).stem
        pruefe("Lesen: /api/belege zeigt den Beleg, stand = HEAD beim Dienst",
               r.status_code == 200 and r.json().get("stand") == kopf
               and stamm in r.text, f"stand={str(r.json().get('stand'))[:12]} dienst={kopf[:12]}")
        # fremder Commit (steht für Hintergrundjob/zweiten Server)
        (pruef / "review").mkdir(exist_ok=True)
        (pruef / "review" / f"{stamm}.json").write_text(json.dumps({"e2e": True}))
        git(["-C", str(pruef), "add", "-A"], svc_git)
        git(["-C", str(pruef), "-c", "user.name=belegreview", "-c", "user.email=r@e2e",
             "commit", "-q", "-m", f"review: {stamm}"], svc_git)
        p = git(["-C", str(pruef), "push", "-q", "origin", "HEAD:main"], svc_git)
        neu = git(["-C", str(pruef), "rev-parse", "HEAD"], svc_git).stdout.strip()
        r = requests.get(basis + "/api/belege", headers=auth, timeout=30)
        pruefe("fremder Commit erscheint nach dem Nachziehen",
               p.returncode == 0 and r.json().get("stand") == neu, f"{str(r.json().get('stand'))[:12]}")
        pruefe("kein Lesen im GitChain-Speicher",
               not (tmp / "inspektor-store").exists() and "inspektor" not in
               (spiegel / "config").read_text() and a.box in (spiegel / "config").read_text())

        # 7. Negativkontrollen
        pat.write_text("gcpat-" + "f" * 40)
        pat.chmod(0o600)
        r = requests.post(basis + "/ablage", headers=auth, timeout=90,
                          files={"file": ("e2e-zwei.jpg", bild + b"2", "image/jpeg")})
        time.sleep(0.5)
        logtext = (tmp / "babu-web.log").read_text(errors="replace")
        pruefe("falsches Schreib-Token → 502, klare Meldung im Log",
               r.status_code == 502 and "401" in logtext and "abgelehnt" in logtext,
               f"{r.status_code} {r.text[:60]}")
        hz = requests.get(basis + "/healthz", timeout=10)
        pruefe("kein Absturz: Prozess lebt, /healthz 200", proz.poll() is None
               and hz.status_code == 200, hz.text[:80])
        shutil.copyfile(a.dienst_token, pat)
        pat.chmod(0o600)
        r = requests.post(basis + "/ablage", headers=auth, timeout=60,
                          files={"file": ("e2e-drei.jpg", bild + b"3", "image/jpeg")})
        pruefe("Token-Rotation ohne Neustart (Datei je Push frisch gelesen)",
               r.status_code == 200 and r.json().get("ok"), f"{r.status_code}")
        neu_kopf_vorher = git(["ls-remote", f"{dienst}/git/{a.box}.git", "refs/heads/main"],
                              svc_git).stdout.split()[0]

        # --- Namensraum-Grenze (Modell D1: svc-babu darf in babu/<neuer-betrieb>
        # anlegen, sonst nirgends). Geprüft wird der DIENST: direkte Pushes an
        # die URL, an der Client-Prüfung von box_anlegen vorbei.
        def roh_push(ref: str, git_umg: dict, name: str) -> subprocess.CompletedProcess:
            d = tmp / f"roh-{name}"
            git(["init", "-q", "-b", "main", str(d)], git_umg)
            (d / ".0711").mkdir(exist_ok=True)
            (d / ".0711" / "container.json").write_text(json.dumps({"name": name}))
            git(["-C", str(d), "add", "-A"], git_umg)
            git(["-C", str(d), "-c", "user.name=e2e", "-c", "user.email=e@e2e",
                 "commit", "-q", "-m", name], git_umg)
            return git(["-C", str(d), "push", "-q", f"{dienst}/git/{ref}.git",
                        "HEAD:refs/heads/main"], git_umg)

        def server_abweisung(p: subprocess.CompletedProcess) -> tuple[bool, str]:
            """Hat der DIENST abgelehnt (401/403/404), nicht git lokal?"""
            err = p.stderr.strip()
            lokal = "does not appear to be a git repository" in err
            vom_dienst = any(m in err for m in ("401", "403", "404", "not found",
                                                "Authentication failed"))
            return (p.returncode != 0 and vom_dienst and not lokal,
                    (err.splitlines()[-1][:110] if err else f"rc={p.returncode}"))

        stempel = time.strftime("%H%M%S")
        for ref in (f"belegwerk/e2e-{stempel}/y", f"babux/e2e-{stempel}/belege", a.fremde_box):
            ok, beleg = server_abweisung(roh_push(ref, svc_git, ref.replace("/", "_")))
            pruefe(f"Dienst weist svc-Push außerhalb der Freigabe ab: {ref}", ok, beleg)
        # Client-Grenze: box_anlegen verweigert fremde Typen schon vor dem Netz.
        r = py("import boxschreiber\ntry:\n  boxschreiber.box_anlegen('belegwerk/x/y')\n"
               "  print('ANGELEGT')\nexcept boxschreiber.SchreibFehler as ex:\n  print('ABGEWIESEN', ex)")
        pruefe("box_anlegen verweigert fremden Typ (belegwerk/x/y) vor dem Netz",
               "ABGEWIESEN" in r.stdout and "Form babu/" in r.stdout, r.stdout.strip()[:100])
        # Neuer Betrieb unter babu/* OHNE vorher angelegten Tenant: unter D1 erlaubt.
        neu = f"babu/neu-e2e-{stempel}/belege"
        r = py(f"import boxschreiber\ntry:\n  print('ANGELEGT', boxschreiber.box_anlegen({neu!r}))\n"
               f"except boxschreiber.SchreibFehler as ex:\n  print('ABGEWIESEN', ex)")
        if a.d1:
            pruefe(f"neuer Betrieb ohne Tenant anlegbar (D1): {neu}", "ANGELEGT" in r.stdout,
                   r.stdout.strip()[:110])
        else:
            OFFEN.append({"name": f"neuer Betrieb ohne Tenant anlegbar (D1): {neu}",
                          "ergebnis": r.stdout.strip()[:110],
                          "grund": "Dienst ohne D1 — Erwartung erst mit dialog-s-20260927d prüfbar"})
            print(f"OFFEN neuer Betrieb ohne Tenant (erst mit D1): {r.stdout.strip()[:90]}", flush=True)

        # --- Das Token eines Menschen (Leser am Tenant) schreibt nicht in die Box.
        # Direkt an die Box-URL, Ablehnung muss vom Dienst kommen.
        ok, beleg = server_abweisung(roh_push(a.box, mensch_git, "mensch"))
        pruefe("Dienst weist Push mit dem Token eines Menschen in die Box ab", ok, beleg)
        kopf_nach = git(["ls-remote", f"{dienst}/git/{a.box}.git", "refs/heads/main"],
                        svc_git).stdout.split()[0]
        pruefe("Box-HEAD nach den abgewiesenen Pushes unverändert", kopf_nach == neu_kopf_vorher,
               kopf_nach[:12])
    finally:
        proz.terminate()
        try:
            proz.wait(10)
        except subprocess.TimeoutExpired:
            proz.kill()
        log.close()

    alles = (tmp / "babu-web.log").read_text(errors="replace") + json.dumps(PRUEFUNGEN)
    pruefe("kein Token-Wert in Log und Ergebnis", not any(g in alles for g in geheim))
    ok = all(p["ok"] for p in PRUEFUNGEN)
    if a.ergebnis:
        a.ergebnis.write_text(json.dumps({"dienst": dienst, "box": a.box, "zweite_box": a.zweite_box,
                                          "ok": ok, "pruefungen": PRUEFUNGEN, "offen_bis_d1": OFFEN,
                                          "d1": a.d1,
                                          "zeit": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                         ensure_ascii=False, indent=2))
        shutil.copyfile(tmp / "babu-web.log", a.ergebnis.with_suffix(".babu-web.log"))
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{sum(p['ok'] for p in PRUEFUNGEN)}/{len(PRUEFUNGEN)} bestanden"
          + (f", {len(OFFEN)} offen bis D1" if OFFEN else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
