#!/usr/bin/env python3
"""betrieb_anlegen — einen Betrieb in einem Lauf aufnehmen und danach prüfen.

Bis heute ist die Aufnahme eines neuen Betriebs verteiltes Wissen: Konto
anlegen, Belegbox einrichten lassen, Mandantenzeile schreiben, Kontenrahmen
setzen, die Kanzlei verknüpfen. Fünf Schritte, von denen vier still
schiefgehen können — eine fehlende Berater-Nummer fällt erst beim
DATEV-Export auf, ein vergessener `box_ref` erst, wenn jemand Belege sucht,
und die falsche Reihenfolge (Mandant vor Konto) erst unter Postgres.

Für 5 bis 20 Betriebe bleibt das Handarbeit — aber Handarbeit an einem
Werkzeug, nicht aus dem Kopf. Deshalb macht diese Datei zwei Dinge, und
zwar getrennt:

    anlegen()  schreibt, in der einzig richtigen Reihenfolge
    pruefen()  liest danach nach und sagt Ja/Nein mit Grund

Der zweite Teil ist der wichtigere. Ein Anlegewerkzeug, das nur schreibt,
verlagert das Problem nur: dann glaubt man ihm. Erst die Nachprüfung macht
aus „ich habe es getan“ ein „ich habe nachgesehen“.

**Was dieses Werkzeug ausdrücklich NICHT tut: die Belegbox erzeugen.** Das
Gateway `insp-app` ist ein fremdes Projekt und wird nicht ferngesteuert
(CLAUDE.md, „Betrieb H200V — Finger weg“). Das Werkzeug prüft, ob die Box
da und lesbar ist, und nennt sonst den genauen Pfad, den es erwartet.

**Das Startpasswort erscheint genau einmal, auf der Konsole des
Aufrufers.** Es steht in keiner Datei, in keinem Log und in keinem Feld des
Berichts — in der Datenbank liegt nur sein scrypt-Hash. Wer es weitergibt,
tut das persönlich; wer es verliert, vergibt über „Zugänge verwalten →
Neues Startpasswort“ ein neues.

Aufruf (Beispiel):

    /tmp/babu-venv/bin/python werkzeuge/betrieb_anlegen.py \\
        --email nina@supremestudio.de --name "Nina Muster" \\
        --betrieb "SupremeStudio" --kanzlei-id 7 \\
        --berater-nr 16149 --mandant-nr 19364 \\
        --box-ref inspektor/ws-nina.de/babu

Die Belegbox kommt fast immer später — sie entsteht am Gateway, von
Hand. Dann trägt derselbe Aufruf sie nach, ohne etwas anzulegen:

    … betrieb_anlegen.py --nur-box --email nina@supremestudio.de \\
        --box-ref inspektor/ws-nina.de/babu

Rückgabewerte:

    0   angelegt, alle Prüfungen bestanden
    1   angelegt, aber eine Prüfung meldet einen Fehler
    2   nichts geschrieben — die Vorprüfung hat abgebrochen
    3   angelegt und geprüft, es fehlt nur noch die Belegbox (Handarbeit)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
BELEGREVIEW = WURZEL / "server" / "belegreview"
if str(BELEGREVIEW) not in sys.path:
    sys.path.insert(0, str(BELEGREVIEW))

import audit  # noqa: E402
import babu_web as bw  # noqa: E402
import box as bx  # noqa: E402
import einladung as ei  # noqa: E402
import kontenrahmen as kr  # noqa: E402
import mandanten  # noqa: E402
from kontierung import RAHMEN  # noqa: E402

#: Wer im Audit-Log steht. Kein Mensch — das Werkzeug läuft auf der
#: Kommandozeile eines Betreibers, und der ist über die Shell schon
#: identifiziert. Ein erfundener Nutzername wäre schlechter als ehrlich
#: „hier war das Werkzeug“.
AKTEUR = "werkzeug:betrieb_anlegen"


class Abbruch(Exception):
    """Die Vorprüfung sagt Nein — es wurde nichts geschrieben."""


# ---------------------------------------------------------------------------
# Was hinein geht und was heraus kommt
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    """Die Angaben zu einem Betrieb — alles, was das Werkzeug braucht.

    `kanzlei_id` und `kanzlei_neu` schließen sich aus: entweder der Betrieb
    kommt zu einer bestehenden Kanzlei, oder er ist der erste einer neuen.
    Ohne beides entsteht nur das Konto — dann gibt es keine Mandantenzeile,
    und damit auch keinen Ort für Box, Kontenrahmen und DATEV-Nummern.
    """

    email: str
    name: str = ""
    betrieb: str = ""
    kanzlei_id: int | None = None
    kanzlei_neu: str = ""
    kanzlei_inhaber: str = ""
    kontenrahmen: str = ""
    berater_nr: str = ""
    mandant_nr: str = ""
    box_ref: str = ""
    trocken: bool = False


@dataclass
class Schritt:
    """Ein Arbeitsschritt — im Trockenlauf geplant, sonst getan."""

    name: str
    text: str
    getan: bool = False


@dataclass
class Pruefung:
    """Eine Nachfrage an die Datenbank: Ja oder Nein, und warum.

    `handarbeit` unterscheidet zwei Arten von Nein. „Die Mandantenzeile hat
    keine Berater-Nummer“ ist ein Fehler — da hat jemand etwas vergessen,
    und der DATEV-Export fiele später darauf herein. „Die Belegbox gibt es
    noch nicht“ ist keiner: das ist der Wartezustand `box_ausstehend`, und
    der nächste Schritt gehört einem Menschen am Gateway. Beides als Fehler
    zu melden würde die echten Fehler entwerten.
    """

    name: str
    ok: bool
    grund: str = ""
    handarbeit: bool = False


@dataclass
class Bericht:
    #: Überschrift des Konsolenberichts — der Nachtrag legt nichts an.
    titel: str = "Angelegt"
    email: str = ""
    schritte: list[Schritt] = field(default_factory=list)
    pruefungen: list[Pruefung] = field(default_factory=list)
    trocken: bool = False
    konto_neu: bool = False
    kanzlei_id: int | None = None
    mandant_id: int | None = None
    box_ref: str = ""

    @property
    def fehler(self) -> list[Pruefung]:
        return [p for p in self.pruefungen if not p.ok and not p.handarbeit]

    @property
    def offen(self) -> list[Pruefung]:
        return [p for p in self.pruefungen if not p.ok and p.handarbeit]

    def code(self) -> int:
        """0 gut · 1 Fehler · 3 steht, aber die Box fehlt noch.

        Der Trockenlauf ist immer 0: er hat nichts angelegt, also kann
        auch nichts halb angelegt sein. Was er über die Box weiß, steht
        im Vorbefund — als Hinweis, nicht als Befund über einen Zustand,
        den es noch gar nicht gibt.
        """
        if self.trocken:
            return 0
        if self.fehler:
            return 1
        return 3 if self.offen else 0


# ---------------------------------------------------------------------------
# Belegbox: nachsehen, nie anlegen
# ---------------------------------------------------------------------------

def box_befund(box_ref: str) -> Pruefung:
    """Ist die Belegbox da und lesbar?

    Drei mögliche Antworten, und jede nennt den nächsten Schritt. Der Pfad
    kommt aus `box.store_aus_ref` — derselben Konvention, mit der der
    Server die Box später auflöst. Ein Pfad, den das Werkzeug selbst
    ausdenkt, wäre wertlos: er müsste genau der sein, den `insp-app`
    anlegt.
    """
    ref = (box_ref or "").strip().strip("/")
    if not ref:
        return Pruefung(
            "belegbox", False, handarbeit=True,
            grund="kein Verweis angegeben. Sobald die Box am Gateway "
                  "eingerichtet ist, mit --nur-box --box-ref <verweis> "
                  "nachtragen (z. B. inspektor/ws-nina.de/babu).")
    store = bx.store_aus_ref(ref)
    if not store.is_dir():
        return Pruefung(
            "belegbox", False, handarbeit=True,
            grund=f"nicht vorhanden. Erwartet wird {store} — die Box legt "
                  f"insp-app an, nicht dieses Werkzeug.")
    try:
        r = subprocess.run(["git", "-C", str(store), "rev-parse", "--git-dir"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as ex:  # noqa: BLE001
        return Pruefung("belegbox", False,
                        grund=f"{store} lässt sich nicht lesen: {ex}")
    if r.returncode != 0:
        return Pruefung(
            "belegbox", False,
            grund=f"{store} ist kein Git-Speicher "
                  f"({(r.stderr or '').strip()[:120]}).")
    # `--verify -q`, nicht das nackte `rev-parse HEAD`: in einem frischen
    # bare-Speicher gibt letzteres das unaufgelöste Wort „HEAD“ auf
    # stdout aus — und einen Rückgabewert 0 dazu (gemessen, git 2.x).
    # Ohne `--verify` stünde also „HEAD“ als Stand im Bericht.
    kopf = subprocess.run(["git", "-C", str(store), "rev-parse", "--verify",
                           "-q", "HEAD"],
                          capture_output=True, text=True, timeout=10)
    stand = ((kopf.stdout or "").strip()[:12] if kopf.returncode == 0
             else "noch ohne Belege")
    return Pruefung("belegbox", True, grund=f"{store} ({stand})")


# ---------------------------------------------------------------------------
# Vorprüfung — alles, was einen Abbruch VOR dem ersten Schreiben rechtfertigt
# ---------------------------------------------------------------------------

def _geputzt(plan: Plan) -> Plan:
    """Dieselbe Reinigung wie in der Kanzlei-Route: kürzen, trimmen, klein."""
    rahmen = (plan.kontenrahmen or "").strip().upper()
    return Plan(
        email=plan.email.strip().lower()[:200],
        name=plan.name.strip()[:120],
        betrieb=plan.betrieb.strip()[:120],
        kanzlei_id=plan.kanzlei_id,
        kanzlei_neu=plan.kanzlei_neu.strip()[:120],
        kanzlei_inhaber=plan.kanzlei_inhaber.strip().lower()[:200],
        kontenrahmen=rahmen or kr.vorgabe(),
        berater_nr=plan.berater_nr.strip()[:20],
        mandant_nr=plan.mandant_nr.strip()[:20],
        box_ref=plan.box_ref.strip().strip("/")[:200],
        trocken=plan.trocken,
    )


def vorpruefen(plan: Plan) -> Plan:
    """Alles, was den Lauf verhindert, bevor eine einzige Zeile entsteht.

    Der zweite Lauf mit derselben E-Mail landet hier: `nutzer_anlegen`
    gäbe stumm `None` zurück, und der Mandant entstünde trotzdem — ein
    Betrieb mit zwei Mandantenzeilen und einem fremden Konto daran. Lieber
    ein Abbruch mit Grund.
    """
    p = _geputzt(plan)
    if not ei.mail_gueltig(p.email):
        raise Abbruch(f"„{plan.email}“ ist keine brauchbare E-Mail-Adresse.")
    if not p.betrieb:
        raise Abbruch("Ohne Betriebsnamen geht es nicht (--betrieb).")
    if p.kontenrahmen not in RAHMEN:
        raise Abbruch(f"Kontenrahmen „{p.kontenrahmen}“ kennen wir nicht — "
                      f"bekannt sind {', '.join(sorted(RAHMEN))}.")
    if p.kanzlei_id is not None and p.kanzlei_neu:
        raise Abbruch("--kanzlei-id und --kanzlei-neu schließen sich aus.")
    if p.kanzlei_neu and not p.kanzlei_inhaber:
        raise Abbruch("Eine neue Kanzlei braucht ein erstes Mitglied "
                      "(--kanzlei-inhaber).")
    mit_mandant = p.kanzlei_id is not None or bool(p.kanzlei_neu)
    if p.box_ref and not mit_mandant:
        raise Abbruch("Der Verweis auf die Belegbox steht an der "
                      "Mandantenzeile — dafür braucht es --kanzlei-id "
                      "oder --kanzlei-neu.")
    if ".." in p.box_ref or p.box_ref.startswith("-"):
        raise Abbruch(f"„{p.box_ref}“ ist kein gültiger Verweis auf eine "
                      f"Belegbox.")

    if bw.nutzer_holen(p.email) is not None:
        raise Abbruch(f"Für {p.email} gibt es dieses Konto schon. Ein "
                      f"zweiter Betrieb braucht eine eigene Adresse; ein "
                      f"neues Startpasswort vergibt „Zugänge verwalten“.")
    if p.kanzlei_id is not None:
        with bw._db_sitzung() as c:  # noqa: SLF001
            if mandanten.kanzlei_holen(p.kanzlei_id, c=c) is None:
                raise Abbruch(f"Kanzlei {p.kanzlei_id} gibt es hier nicht.")
            doppelt = c.execute("SELECT 1 FROM mandant WHERE kanzlei_id=? AND "
                                "besitzer_un=?", (p.kanzlei_id, p.email)
                                ).fetchone()
        if doppelt:
            raise Abbruch(f"Kanzlei {p.kanzlei_id} betreut {p.email} schon.")
    return p


# ---------------------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------------------

def anlegen(plan: Plan) -> tuple[Bericht, str | None]:
    """Konto, Kanzlei, Mandant, Box — in dieser Reihenfolge.

    Gibt den Bericht und das Startpasswort zurück. Das Passwort wandert
    NUR über diesen Rückgabewert; es landet weder im Bericht noch im
    Audit-Log noch in einer Datei.

    Zur Reihenfolge: `mandant.besitzer_un` zeigt per Fremdschlüssel auf
    `nutzer(email)`, und Postgres prüft das wirklich — der erste Mandant
    im Betrieb fiel darüber mit einem 500 (CLAUDE.md, „Datenbank“).
    Deshalb steht das Konto vor dem Mandanten, und weil `nutzer_anlegen`
    sein Schloss selbst nimmt, steht es auch vor der Sitzung.
    """
    p = vorpruefen(plan)
    b = Bericht(email=p.email, trocken=p.trocken, kanzlei_id=p.kanzlei_id)
    mit_mandant = p.kanzlei_id is not None or bool(p.kanzlei_neu)

    b.schritte.append(Schritt(
        "konto", f"Konto {p.email} (Rolle salon, Betrieb „{p.betrieb}“), "
                 f"Startpasswort erscheint einmal auf der Konsole"))
    if p.kanzlei_neu:
        b.schritte.append(Schritt(
            "kanzlei", f"Kanzlei „{p.kanzlei_neu}“ mit {p.kanzlei_inhaber} "
                       f"als Inhaber"))
    if mit_mandant:
        wessen = (f"Kanzlei {p.kanzlei_id}" if p.kanzlei_id is not None
                  else f"der neuen Kanzlei „{p.kanzlei_neu}“")
        b.schritte.append(Schritt(
            "mandant", f"Mandant „{p.betrieb}“ unter {wessen}, Kontenrahmen "
                       f"{p.kontenrahmen}, Berater {p.berater_nr or '—'}, "
                       f"Mandant {p.mandant_nr or '—'}"))
    if p.box_ref:
        b.schritte.append(Schritt(
            "box", f"Belegbox {p.box_ref} verknüpfen, falls sie da ist"))

    if p.trocken:
        # Der Trockenlauf sieht trotzdem nach der Box: sie ist der einzige
        # Schritt, den ein Mensch vorher erledigen muss.
        b.pruefungen.append(box_befund(p.box_ref))
        return b, None

    # 1. Das Konto. `box=False` wie im Mandanten-Weg der Kanzlei-Route:
    # ein neuer Betrieb bekommt seine eigene Box über `mandant.box_ref` —
    # `box=True` hieße Zugriff auf die Default-Box, also auf die
    # Buchhaltung des Betriebs, der heute schon auf dem Server liegt.
    passwort = bw.nutzer_anlegen(p.email, p.name, p.betrieb, "salon", box=False)
    b.konto_neu = passwort is not None
    _erledigt(b, "konto")

    kanzlei_id = p.kanzlei_id
    with bw._db_sitzung() as c:  # noqa: SLF001
        if p.kanzlei_neu:
            kanzlei_id = mandanten.kanzlei_anlegen(p.kanzlei_neu,
                                                   p.kanzlei_inhaber, c=c)
            _erledigt(b, "kanzlei")
        if mit_mandant:
            b.mandant_id = mandanten.mandant_anlegen(
                kanzlei_id, p.betrieb, p.email, p.kontenrahmen,
                p.berater_nr or None, p.mandant_nr or None, c=c)
            _erledigt(b, "mandant")
    b.kanzlei_id = kanzlei_id

    # 2. Die Box — nur verknüpfen, wenn sie wirklich da ist. Ein
    # `box_ref` auf ein Verzeichnis, das es nicht gibt, machte den
    # Mandanten `aktiv` und die Belegliste zu einem Fehler; der ehrliche
    # Zustand heißt `box_ausstehend`.
    befund = box_befund(p.box_ref)
    if p.box_ref and befund.ok and b.mandant_id is not None:
        with bw._db_sitzung() as c:  # noqa: SLF001
            mandanten.box_verknuepfen(b.mandant_id, p.box_ref, c=c)
        b.box_ref = p.box_ref
        _erledigt(b, "box")

    audit.audit(AKTEUR, "betrieb_anlegen", ziel_un=p.email,
                mandant_id=str(b.mandant_id) if b.mandant_id else None,
                kanzlei_id=kanzlei_id, kontenrahmen=p.kontenrahmen,
                box_verknuepft=bool(b.box_ref))
    b.pruefungen = pruefen(p, b, passwort)
    return b, passwort


def _erledigt(b: Bericht, name: str) -> None:
    for s in b.schritte:
        if s.name == name:
            s.getan = True


def box_nachtragen(plan: Plan) -> Bericht:
    """Die Belegbox an einen schon angelegten Betrieb hängen.

    Der zweite Handgriff der Aufnahme, und der einzige, der zwangsläufig
    später kommt: die Box entsteht am Gateway, von Hand, und niemand weiß
    vorher, wann. Ohne diesen Weg wäre der Rat „erneut mit --box-ref
    aufrufen“ falsch — der volle Lauf bricht auf dem vorhandenen Konto ab,
    und das zu Recht.

    Angelegt wird hier nichts, verändert nur `mandant.box_ref` und der
    Status. Ist die Box nicht erreichbar, bleibt auch das aus: ein
    Mandant auf `aktiv` mit einem Verweis ins Leere wäre schlimmer als
    einer, der ehrlich wartet.
    """
    p = _geputzt(plan)
    if not p.box_ref:
        raise Abbruch("--nur-box braucht --box-ref.")
    if bw.nutzer_holen(p.email) is None:
        raise Abbruch(f"Für {p.email} gibt es kein Konto — hier ist noch "
                      f"nichts nachzutragen.")
    with bw._db_sitzung() as c:  # noqa: SLF001
        if p.kanzlei_id is not None:
            zeilen = c.execute("SELECT id FROM mandant WHERE kanzlei_id=? AND "
                               "besitzer_un=?", (p.kanzlei_id, p.email)
                               ).fetchall()
        else:
            zeilen = c.execute("SELECT id FROM mandant WHERE besitzer_un=?",
                               (p.email,)).fetchall()
    if not zeilen:
        raise Abbruch(f"Zu {p.email} gibt es keine Mandantenzeile, an die "
                      f"eine Box gehören könnte.")
    if len(zeilen) > 1:
        raise Abbruch(f"{p.email} ist bei mehreren Kanzleien Mandant — bitte "
                      f"mit --kanzlei-id sagen, welche gemeint ist.")

    b = Bericht(titel="Nachgetragen", email=p.email, trocken=p.trocken,
                mandant_id=int(zeilen[0][0]))
    m = mandanten.mandant_holen(b.mandant_id)
    b.kanzlei_id = int(m["kanzlei_id"])
    b.schritte.append(Schritt("box", f"Belegbox {p.box_ref} an Mandant "
                                     f"{b.mandant_id} („{m['name']}“)"))
    befund = box_befund(p.box_ref)
    if p.trocken:
        b.pruefungen.append(befund)
        return b
    if befund.ok:
        with bw._db_sitzung() as c:  # noqa: SLF001
            mandanten.box_verknuepfen(b.mandant_id, p.box_ref, c=c)
        b.box_ref = p.box_ref
        _erledigt(b, "box")
        audit.audit(AKTEUR, "betrieb_box_nachtragen", ziel_un=p.email,
                    mandant_id=str(b.mandant_id), kanzlei_id=b.kanzlei_id)
    # Der volle Prüfsatz, nicht nur die Box: wer die Box nachträgt, will
    # wissen, ob der Betrieb jetzt vollständig ist.
    b.pruefungen = pruefen(p, b, None)
    return b


# ---------------------------------------------------------------------------
# Nachprüfen
# ---------------------------------------------------------------------------

def pruefen(p: Plan, b: Bericht, passwort: str | None = None) -> list[Pruefung]:
    """Nachsehen, was wirklich in der Datenbank steht.

    Bewusst über dieselben Wege, die der Server im Betrieb geht
    (`nutzer_holen`, `mandant_holen`, `kanzlei_mitglied`, `store_aus_ref`)
    — eine Prüfung, die anders liest als der Server, prüft das Falsche.
    """
    aus: list[Pruefung] = []

    n = bw.nutzer_holen(p.email)
    if n is None:
        aus.append(Pruefung("konto", False,
                            f"{p.email} steht nicht in der Nutzertabelle."))
    elif not n["aktiv"]:
        aus.append(Pruefung("konto", False, f"{p.email} ist gesperrt."))
    elif n["rolle"] != "salon":
        aus.append(Pruefung("konto", False,
                            f"{p.email} hat die Rolle „{n['rolle']}“, "
                            f"erwartet war „salon“."))
    else:
        aus.append(Pruefung("konto", True, f"{p.email}, Rolle salon, aktiv"))

    # Die Anmeldung wird wirklich durchgerechnet, nicht angenommen: der
    # Hash in der Datenbank muss zu dem Passwort passen, das der Aufrufer
    # gleich weitergibt. Ein Konto, an dem sich niemand anmelden kann,
    # sieht sonst genauso aus wie ein gutes.
    #
    # Ohne Passwort — beim Nachtragen der Box bestand das Konto schon —
    # bleibt die schwächere, aber ehrliche Frage: liegt überhaupt ein
    # brauchbarer scrypt-Hash da? Ein leeres Feld hieße, dass sich
    # niemand anmelden kann, und das wäre sehr wohl ein Fehler.
    if n is None:
        aus.append(Pruefung("anmeldung", False, "ohne Konto nicht prüfbar."))
    elif passwort is None:
        hash_da = str(n["pw"] or "").startswith("scrypt$")
        aus.append(Pruefung(
            "anmeldung", hash_da,
            "ein Passwort ist hinterlegt (hier nicht nachrechenbar — das "
            "Konto bestand schon)" if hash_da else
            f"{p.email} hat kein brauchbares Passwort hinterlegt; ein neues "
            f"vergibt „Zugänge verwalten“."))
    elif not bw.pw_pruefen(passwort, n["pw"] or ""):
        aus.append(Pruefung("anmeldung", False,
                            "das Startpasswort passt nicht zum "
                            "gespeicherten Hash."))
    else:
        aus.append(Pruefung("anmeldung", True,
                            "Startpasswort passt zum gespeicherten Hash"))

    if b.mandant_id is None:
        aus.append(Pruefung(
            "mandantenzeile", False, handarbeit=True,
            grund="keine angelegt — ohne Kanzlei gibt es keine Zeile für "
                  "Box, Kontenrahmen und DATEV-Nummern."))
        aus.append(box_befund(p.box_ref))
        return aus

    m = mandanten.mandant_holen(b.mandant_id)
    if m is None:
        aus.append(Pruefung("mandantenzeile", False,
                            f"Mandant {b.mandant_id} ist nicht auffindbar."))
        aus.append(Pruefung("kanzlei", False, "ohne Mandant nicht prüfbar."))
        aus.append(Pruefung("kontenrahmen", False, "ohne Mandant nicht prüfbar."))
        aus.append(box_befund(p.box_ref))
        return aus

    fehlt = [feld for feld in ("name", "besitzer_un", "berater_nr", "mandant_nr")
             if not (m.get(feld) or "").strip()]
    if m["besitzer_un"] != p.email:
        aus.append(Pruefung("mandantenzeile", False,
                            f"gehört {m['besitzer_un']}, erwartet war "
                            f"{p.email}."))
    elif fehlt:
        aus.append(Pruefung(
            "mandantenzeile", False,
            f"unvollständig, es fehlt: {', '.join(fehlt)}. Berater- und "
            f"Mandantennummer braucht der DATEV-Stapel — ohne sie fällt "
            f"es erst beim Export auf."))
    else:
        aus.append(Pruefung(
            "mandantenzeile", True,
            f"„{m['name']}“, Berater {m['berater_nr']}, Mandant "
            f"{m['mandant_nr']}, Status {m['status']}"))

    k = mandanten.kanzlei_holen(int(m["kanzlei_id"]))
    if k is None:
        aus.append(Pruefung("kanzlei", False,
                            f"Kanzlei {m['kanzlei_id']} gibt es nicht — die "
                            f"Mandantenzeile zeigt ins Leere."))
    elif not mandanten.kanzlei_mitglied(k["inhaber_un"], b.mandant_id):
        aus.append(Pruefung(
            "kanzlei", False,
            f"„{k['name']}“ hat kein Mitglied, das diesen Mandanten "
            f"bedienen darf."))
    else:
        aus.append(Pruefung("kanzlei", True,
                            f"„{k['name']}“ (id {k['id']}), Inhaber "
                            f"{k['inhaber_un']}"))

    rahmen = (m.get("kontenrahmen") or "").strip().upper()
    if rahmen not in RAHMEN:
        aus.append(Pruefung(
            "kontenrahmen", False,
            f"„{rahmen or '—'}“ ist keiner der bekannten Rahmen "
            f"({', '.join(sorted(RAHMEN))}). Ohne ihn bucht der Betrieb "
            f"nach der Server-Vorgabe statt nach seiner eigenen Wahl."))
    else:
        aus.append(Pruefung("kontenrahmen", True, rahmen))

    befund = box_befund(m.get("box_ref") or p.box_ref)
    if befund.ok and not (m.get("box_ref") or "").strip():
        befund = Pruefung(
            "belegbox", False, handarbeit=True,
            grund="da, aber nicht an der Mandantenzeile eingetragen — "
                  "mit --nur-box --box-ref nachtragen.")
    aus.append(befund)
    return aus


# ---------------------------------------------------------------------------
# Konsole
# ---------------------------------------------------------------------------

def bericht_zeilen(b: Bericht, passwort: str | None = None) -> list[str]:
    """Der Bericht als Text. Das Passwort steht nur hier, nur einmal."""
    z: list[str] = []
    z.append("Trockenlauf — nichts geschrieben:" if b.trocken
             else f"{b.titel}:")
    for s in b.schritte:
        marke = "  " if b.trocken else ("+ " if s.getan else "- ")
        z.append(f"  {marke}{s.text}" + ("" if s.getan or b.trocken
                                         else "   (nicht ausgeführt)"))
    if b.pruefungen:
        z.append("")
        z.append("Vorbefund:" if b.trocken else "Geprüft:")
        for p in b.pruefungen:
            marke = "ja  " if p.ok else ("offen" if p.handarbeit else "NEIN")
            z.append(f"  {marke:5} {p.name}: {p.grund}")
    if b.trocken:
        z.append("")
        z.append("Nichts geschrieben. Derselbe Aufruf ohne --trocken legt "
                 "es an.")
    elif b.fehler:
        z.append("")
        z.append(f"{len(b.fehler)} Prüfung(en) melden einen Fehler — "
                 f"der Betrieb ist noch nicht arbeitsfähig.")
    elif b.offen:
        z.append("")
        z.append(f"Der Betrieb steht. Offen bleibt Handarbeit: "
                 f"{', '.join(p.name for p in b.offen)}.")
    if passwort:
        z.append("")
        z.append(f"Startpasswort für {b.email}: {passwort}")
        z.append("Persönlich weitergeben. Es steht nirgends sonst und lässt "
                 "sich nicht noch einmal anzeigen.")
    return z


def _argumente(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="betrieb_anlegen",
        description="Einen Betrieb aufnehmen: Konto, Mandant, Kontenrahmen, "
                    "Belegbox verknüpfen — und danach nachprüfen.")
    ap.add_argument("--email", required=True, help="Anmeldung des Betriebs")
    ap.add_argument("--name", default="", help="Name des Menschen dahinter")
    # Nicht `required`: mit --nur-box steht der Betrieb längst da, und
    # sein Name wird nicht noch einmal gebraucht. Fehlt er beim vollen
    # Lauf, sagt das die Vorprüfung auf Deutsch.
    ap.add_argument("--betrieb", default="", help="Name des Betriebs")
    ap.add_argument("--kanzlei-id", type=int, default=None,
                    help="bestehende Kanzlei, die ihn betreut")
    ap.add_argument("--kanzlei-neu", default="",
                    help="Name einer neuen Kanzlei (braucht --kanzlei-inhaber)")
    ap.add_argument("--kanzlei-inhaber", default="",
                    help="erstes Mitglied der neuen Kanzlei")
    ap.add_argument("--kontenrahmen", default="",
                    help=f"{', '.join(sorted(RAHMEN))} (Vorgabe: "
                         f"{kr.vorgabe()})")
    ap.add_argument("--berater-nr", default="", help="DATEV-Beraternummer")
    ap.add_argument("--mandant-nr", default="", help="DATEV-Mandantennummer")
    ap.add_argument("--box-ref", default="",
                    help="Verweis auf die schon eingerichtete Belegbox")
    ap.add_argument("--nur-box", action="store_true",
                    help="nichts anlegen, nur die Belegbox an einen "
                         "vorhandenen Betrieb hängen")
    ap.add_argument("--trocken", action="store_true",
                    help="nur zeigen, was passieren würde")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    a = _argumente(argv)
    plan = Plan(email=a.email, name=a.name, betrieb=a.betrieb,
                kanzlei_id=a.kanzlei_id, kanzlei_neu=a.kanzlei_neu,
                kanzlei_inhaber=a.kanzlei_inhaber,
                kontenrahmen=a.kontenrahmen, berater_nr=a.berater_nr,
                mandant_nr=a.mandant_nr, box_ref=a.box_ref, trocken=a.trocken)
    passwort = None
    try:
        if a.nur_box:
            bericht = box_nachtragen(plan)
        else:
            bericht, passwort = anlegen(plan)
    except Abbruch as ex:
        print(f"Abgebrochen: {ex}", file=sys.stderr)
        return 2
    for zeile in bericht_zeilen(bericht, passwort):
        print(zeile)
    return bericht.code()


if __name__ == "__main__":
    raise SystemExit(main())
