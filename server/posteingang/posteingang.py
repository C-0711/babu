#!/usr/bin/env python3
"""posteingang — ein eigener Mailserver als Posteingang für babu.

babu verspricht die digitale Erfassung des ganzen Schriftverkehrs, konnte
bis hierher aber nur senden (`server/belegreview/postfach.py`). Post kam nur
ins System, wenn Nina sie abfotografiert hat. Alles, was per Mail kommt —
Lieferantenrechnungen, Bescheide, Kontoauszüge — musste ausgedruckt oder
weitergeleitet werden. Dieser Dienst nimmt sie direkt an.

Drei Entscheidungen, die man sonst für Zufall halten könnte:

**1. Ein eigener Dienst, nicht eine Route in babu-web.**
Port 25 braucht andere Rechte als ein Webserver, ein Absturz im
Mailempfang darf die Belegannahme nicht mitreißen, und ein offener
SMTP-Empfänger hat einen ganz anderen Update-Zyklus als ein Portal, an dem
man einmal die Woche eine Zeile ändert.

**2. Dieser Dienst schreibt NIE in die Belegbox.**
Er reicht jede Sendung über die HTTP-API von babu-web weiter
(`/api/aufnahme` für Anhänge, `/api/dokumente` für den Mailtext). Der
Grund steht in `server/belegreview/boxschreiber.py`: die Belegbox ist ein
Git-Repository mit EINER Arbeitskopie und EINEM Index, und das Schloss
darum herum (`Box.schloss`) schützt nur innerhalb eines Prozesses. Zwei
Prozesse, die `fetch + reset --hard` auf demselben Klon fahren, räumen
einander die Datei aus dem Index und committen am Ende fremden Inhalt.
Genau ein Dienst darf Eigentümer der Box sein.

**3. Die Zuordnung hängt an einer nicht erratbaren Adresse.**
An diese Adresse schreiben Lieferanten und Behörden — sie muss für jeden
Absender offen sein, eine Absenderliste würde die Funktion zerstören. Also
ist die Nichterratbarkeit die Zugangskontrolle: der lokale Teil ist ein
Zufallswort aus `post_adresse` (siehe `server/belegreview/postadresse.py`),
kein Name. Wäre er erratbar (`nina@…`), könnte jeder Belege in eine fremde
Belegbox schicken und darin Buchungen erzeugen.

**Abwehr.** Ein offener SMTP-Empfänger ist ein Ziel, deshalb, in dieser
Reihenfolge (billig vor teuer):

    Rate-Limit je IP        bevor überhaupt aufgelöst wird
    Empfänger bekannt?      sonst 550 — kein Relay, kein Ablegen
    Rate-Limit je Adresse   eine bekannte Adresse ist kein Freifahrtschein
    Größe der Sendung       SIZE-Ankündigung UND Nachmessen
    Größe je Anhang         eine 40-MB-Datei in einer 25-MB-Mail gibt es nicht,
                            aber die Grenze steht getrennt, weil sie das
                            Weiterreichen begrenzt, nicht das Annehmen
    Format je Anhang        nur was der Leseweg kennt (PDF/JPG/PNG/HEIC)

**Was NICHT still passiert:** ein Anhang im falschen Format wird benannt.
Er steht mit Namen und Grund im abgelegten Mailtext. Ein verworfener
Anhang, von dem niemand erfährt, ist schlimmer als gar kein Posteingang —
die Absenderin glaubt, ihre Rechnung sei angekommen.

**Antwortcodes und warum.** 550 heißt „gibt es nicht, versuch es nicht
wieder" und steht ausschließlich auf unbekannten Empfängern. Alles andere,
was schiefgeht — babu-web nicht erreichbar, Rate-Limit, ein Fehler beim
Weiterreichen — wird ein 4xx: der absendende Server hebt die Mail dann auf
und versucht es später erneut. Ein 5xx an dieser Stelle wäre verlorene
Post. Wiederholung ist ungefährlich: babu-web legt bytegleiche Dateien
nicht zweimal ab (`_blob_schon_da`).
"""
from __future__ import annotations

import email
import email.policy
import os
import ssl
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Grenzen — alles aus der Umgebung, mit Vorgaben, die für einen Salon passen
# ---------------------------------------------------------------------------

#: Nur was der Leseweg von babu kennt. `.xml` fehlt mit Absicht: die
#: E-Rechnung im XML-Format geht heute über den Portal-Upload und hat dort
#: einen eigenen Weg; sie über den Mailempfang hereinzulassen, ohne dass
#: dieser Weg geprüft ist, wäre eine Zusage ohne Deckung.
BELEG_ENDUNGEN = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".heic"})


def _zahl(name: str, vorgabe: int) -> int:
    roh = (os.environ.get(name) or "").strip()
    try:
        wert = int(roh)
    except ValueError:
        return vorgabe
    return wert if wert > 0 else vorgabe


@dataclass(frozen=True)
class Grenzen:
    """Was hereindarf. Eine Stelle, damit Prüfung und Ankündigung (SMTP
    SIZE) nicht auseinanderlaufen können."""

    #: Ganze Sendung. 25 MB ist, was die großen Anbieter annehmen — mehr
    #: anzunehmen brächte nichts, weil es ohnehin niemand schickt.
    sendung_max: int = 25 * 1024 * 1024
    #: Ein einzelner Anhang. Kleiner als die Sendung, weil er weitergereicht
    #: wird: babu-web hat sein eigenes Limit (HOCHLADEN_MAX, 40 MB) und soll
    #: nicht der sein, der Nein sagt.
    anhang_max: int = 15 * 1024 * 1024
    #: Anhänge je Sendung. Eine Mail mit 200 Anhängen ist kein Beleg,
    #: sondern eine Last.
    anhaenge_max: int = 25
    #: Empfänger je Sendung. Post an einen Betrieb hat einen Empfänger;
    #: mehrere sind das Muster eines Relay-Versuchs.
    empfaenger_max: int = 5
    #: Empfängerzeilen je Zeitfenster, je absendender IP und je
    #: Empfangsadresse. Gezählt wird am RCPT, nicht an der fertigen Mail:
    #: eine Flut kostet dann schon vor dem Übertragen der Daten ihr
    #: Kontingent — und eine Mail an zwei Adressen zählt zweimal, was
    #: richtig ist, denn sie erzeugt auch zweimal Arbeit.
    rate_ip: int = 60
    rate_adresse: int = 120
    #: Länge des Zeitfensters in Sekunden.
    fenster: int = 3600

    @classmethod
    def aus_umgebung(cls) -> "Grenzen":
        return cls(
            sendung_max=_zahl("POSTEINGANG_SENDUNG_MAX", cls.sendung_max),
            anhang_max=_zahl("POSTEINGANG_ANHANG_MAX", cls.anhang_max),
            anhaenge_max=_zahl("POSTEINGANG_ANHAENGE_MAX", cls.anhaenge_max),
            empfaenger_max=_zahl("POSTEINGANG_EMPFAENGER_MAX", cls.empfaenger_max),
            rate_ip=_zahl("POSTEINGANG_RATE_IP", cls.rate_ip),
            rate_adresse=_zahl("POSTEINGANG_RATE_ADRESSE", cls.rate_adresse),
            fenster=_zahl("POSTEINGANG_FENSTER", cls.fenster),
        )


# ---------------------------------------------------------------------------
# Rate-Limit
# ---------------------------------------------------------------------------

class Rate:
    """Gleitendes Fenster je Schlüssel. Kein Redis, kein Zustand auf Platte.

    Nach einem Neustart ist der Zähler leer — das ist bewusst in Kauf
    genommen: der Dienst startet selten, und ein Angreifer, der ihn zum
    Neustart bringt, hat ein größeres Problem verursacht als ein
    zurückgesetztes Kontingent.
    """

    #: Ab wann aufgeräumt wird, damit die Tabelle nicht ewig wächst —
    #: dieselbe Bauart wie `_IP_TABELLE_MAX` in babu_web.
    TABELLE_MAX = 5000

    def __init__(self, hoechstens: int, fenster: int) -> None:
        self.hoechstens = hoechstens
        self.fenster = fenster
        self._treffer: dict[str, list[float]] = {}
        self._schloss = threading.Lock()

    def erlaubt(self, schluessel: str, jetzt: float | None = None) -> bool:
        """Zählt den Versuch mit und sagt, ob er noch im Kontingent liegt."""
        jetzt = time.time() if jetzt is None else jetzt
        grenze = jetzt - self.fenster
        with self._schloss:
            treffer = [t for t in self._treffer.get(schluessel, ()) if t > grenze]
            if len(treffer) >= self.hoechstens:
                self._treffer[schluessel] = treffer
                return False
            treffer.append(jetzt)
            self._treffer[schluessel] = treffer
            self._aufraeumen(jetzt)
            return True

    def _aufraeumen(self, jetzt: float) -> None:
        if len(self._treffer) <= self.TABELLE_MAX:
            return
        for schluessel, treffer in list(self._treffer.items()):
            if not treffer or jetzt - max(treffer) > self.fenster:
                self._treffer.pop(schluessel, None)


# ---------------------------------------------------------------------------
# babu-web — der einzige Weg in die Belegbox
# ---------------------------------------------------------------------------

class BabuFehler(RuntimeError):
    """babu-web hat nicht geantwortet oder nicht angenommen.

    Immer ein 4xx nach draußen, nie ein 5xx: die Mail liegt beim
    absendenden Server und kommt wieder. Ein 5xx wäre verlorene Post.
    """


class Babu:
    """Der HTTP-Client zu babu-web. Kennt genau drei Adressen.

    Der Dienst spricht als Sachbearbeiter: sein PAT gehört einem Zugang,
    der in der Kanzlei Mitglied ist, und `X-Mandant` sagt, für welchen
    Betrieb er gerade arbeitet. Damit gilt für ihn dieselbe Prüfung wie für
    einen Menschen im Portal (`babu_web._box_wache`) — der Mailserver hat
    keine eigene Berechtigung und kann sich keine geben.
    """

    def __init__(self, url: str | None = None, pat: str | None = None,
                 token: str | None = None, zeit_aus: int = 30,
                 sitzung=None) -> None:
        self.url = (url or os.environ.get("BABU_URL")
                    or "http://127.0.0.1:7844").rstrip("/")
        self.pat = pat if pat is not None else (
            os.environ.get("BABU_POSTEINGANG_PAT") or "")
        self.token = token if token is not None else (
            os.environ.get("BABU_POSTEINGANG_TOKEN") or "")
        self.zeit_aus = zeit_aus
        self.sitzung = sitzung or requests
        # Kurzer Zwischenspeicher für die Auflösung: ein RCPT je Mail, und
        # ein Absender schickt oft mehrere hintereinander. 60 s ist kurz
        # genug, dass eine stillgelegte Adresse zeitnah wirklich zu ist.
        self._cache: dict[str, tuple[int | None, float]] = {}
        self.cache_dauer = 60.0

    # -- Auflösung ---------------------------------------------------------

    def aufloesen(self, lokal: str) -> int | None:
        """Welcher Betrieb — oder None (= 550).

        `None` heißt „gibt es nicht"; erreicht der Dienst babu-web gar
        nicht, fliegt `BabuFehler` und der Aufrufer macht daraus ein 4xx.
        Die beiden Fälle auseinanderzuhalten ist der ganze Punkt: sonst
        würde ein Ausfall von babu-web zu 550 auf JEDE Adresse — und damit
        zu endgültig abgewiesener Post.
        """
        jetzt = time.time()
        eintrag = self._cache.get(lokal)
        if eintrag and eintrag[1] > jetzt:
            return eintrag[0]
        try:
            antwort = self.sitzung.get(
                f"{self.url}/api/posteingang/aufloesen",
                params={"lokal": lokal},
                headers={"X-Posteingang-Token": self.token},
                timeout=self.zeit_aus)
        except Exception as ex:  # noqa: BLE001
            raise BabuFehler(f"babu-web nicht erreichbar: {ex!r}") from ex
        if antwort.status_code == 404:
            self._cache[lokal] = (None, jetzt + self.cache_dauer)
            return None
        if antwort.status_code != 200:
            raise BabuFehler(f"Auflösung antwortete {antwort.status_code}")
        try:
            mandant_id = int(antwort.json()["mandant_id"])
        except Exception as ex:  # noqa: BLE001
            raise BabuFehler(f"Auflösung unlesbar: {ex!r}") from ex
        self._cache[lokal] = (mandant_id, jetzt + self.cache_dauer)
        return mandant_id

    # -- Ablegen -----------------------------------------------------------

    def _senden(self, pfad: str, mandant_id: int, params: dict,
                daten: bytes) -> dict:
        kopf = {"Authorization": f"Bearer {self.pat}",
                "X-Mandant": str(mandant_id),
                "Content-Type": "application/octet-stream"}
        try:
            antwort = self.sitzung.post(f"{self.url}{pfad}", params=params,
                                        headers=kopf, data=daten,
                                        timeout=self.zeit_aus)
        except Exception as ex:  # noqa: BLE001
            raise BabuFehler(f"babu-web nicht erreichbar: {ex!r}") from ex
        if antwort.status_code != 200:
            raise BabuFehler(f"{pfad} antwortete {antwort.status_code}")
        try:
            return antwort.json()
        except Exception:  # noqa: BLE001
            return {}

    def beleg(self, mandant_id: int, name: str, daten: bytes) -> dict:
        """Ein Anhang, der ein Beleg sein kann → `/api/aufnahme`.

        Ohne Einschätzung: der Mailserver liest nichts. babu-web entscheidet
        selbst, ob das ein Beleg, ein Vertrag, Behördenpost oder ein
        Kontoauszug ist — genau wie beim Upload aus dem Portal.
        """
        return self._senden("/api/aufnahme", mandant_id, {"name": name}, daten)

    def dokument(self, mandant_id: int, name: str, daten: bytes, titel: str,
                 art: str = "post") -> dict:
        """Alles, was kein Beleg-Anhang ist → `/api/dokumente`."""
        return self._senden("/api/dokumente", mandant_id,
                            {"name": name, "titel": titel[:120], "art": art},
                            daten)


# ---------------------------------------------------------------------------
# Die Sendung
# ---------------------------------------------------------------------------

@dataclass
class Sendung:
    """Was aus einer Mail geworden ist, bevor irgendetwas abgelegt wurde."""

    absender: str = ""
    betreff: str = ""
    datum: str = ""
    text: str = ""
    #: (Dateiname, Bytes) — nur Formate, die der Leseweg kennt.
    anhaenge: list[tuple[str, bytes]] = field(default_factory=list)
    #: (Dateiname, Grund) — benannt, nicht still geschluckt.
    verworfen: list[tuple[str, str]] = field(default_factory=list)


def _sicherer_name(roh: str, nummer: int) -> str:
    """Ein Dateiname, der nichts anrichtet.

    Ein Anhang heißt, wie der Absender ihn nennt — auch `../../etc/passwd`
    oder `..\\..\\x`. `Path(...).name` schneidet jeden Pfadanteil ab, der
    Rest wird auf harmlose Zeichen reduziert. babu-web prüft den Pfad
    seinerseits (`boxschreiber._pfad_pruefen`); hier steht der Gürtel zum
    Hosenträger, denn diese Seite kennt die Herkunft.
    """
    name = Path(roh.replace("\\", "/")).name.strip()
    sauber = "".join(z if (z.isalnum() or z in "._- ") else "_" for z in name)
    sauber = sauber.strip(" .") or f"anhang-{nummer}"
    return sauber[:100]


def zerlegen(rohdaten: bytes, grenzen: Grenzen | None = None) -> Sendung:
    """Rohe Mail → Absender, Betreff, Datum, Text, Anhänge.

    Was hier NICHT passiert: nichts wird gelesen, gedeutet oder klassifiziert.
    Der Mailserver zerlegt und reicht weiter; die Deutung ist babu-webs
    Aufgabe und steht dort genau einmal.
    """
    grenzen = grenzen or Grenzen()
    nachricht = email.message_from_bytes(rohdaten, policy=email.policy.default)
    sendung = Sendung(
        absender=str(nachricht.get("From", "") or "")[:200],
        betreff=str(nachricht.get("Subject", "") or "")[:200],
        datum=str(nachricht.get("Date", "") or "")[:100])

    koerper = None
    try:
        koerper = nachricht.get_body(preferencelist=("plain", "html"))
    except Exception:  # noqa: BLE001 — kaputte Mails gibt es
        koerper = None
    if koerper is not None:
        try:
            sendung.text = koerper.get_content()
        except Exception:  # noqa: BLE001 — unbekannte Kodierung
            sendung.text = ""
    if not isinstance(sendung.text, str):
        sendung.text = ""

    teile = list(nachricht.iter_attachments())
    if not teile and not nachricht.is_multipart() \
            and nachricht.get_content_maintype() != "text":
        # Eine Mail, die NUR aus dem PDF besteht (einteilig, mit
        # `Content-Disposition: attachment`). `iter_attachments()` liefert
        # dafür nichts — es kennt nur Teile eines mehrteiligen Körpers —
        # und der Beleg fiele wortlos hinten runter. Genau so verschicken
        # manche Scanner und Faxdienste ihre Post.
        teile = [nachricht]

    nummer = 0
    for teil in teile:
        nummer += 1
        name = _sicherer_name(teil.get_filename() or "", nummer)
        if len(sendung.anhaenge) + len(sendung.verworfen) >= grenzen.anhaenge_max:
            sendung.verworfen.append(
                (name, f"mehr als {grenzen.anhaenge_max} Anhänge in einer Mail"))
            continue
        endung = Path(name).suffix.lower()
        if endung not in BELEG_ENDUNGEN:
            sendung.verworfen.append(
                (name, f"Format „{endung or 'ohne Endung'}“ wird nicht gelesen"))
            continue
        try:
            daten = teil.get_content()
        except Exception:  # noqa: BLE001
            sendung.verworfen.append((name, "Anhang nicht lesbar"))
            continue
        if isinstance(daten, str):
            daten = daten.encode("utf-8", "replace")
        if not daten:
            sendung.verworfen.append((name, "leer"))
            continue
        if len(daten) > grenzen.anhang_max:
            sendung.verworfen.append(
                (name, f"größer als {grenzen.anhang_max // (1024 * 1024)} MB"))
            continue
        sendung.anhaenge.append((name, daten))
    return sendung


def _kb(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1048576:.1f} MB"


def mailtext(sendung: Sendung, an: str, ergebnis: list[str] | None = None) -> str:
    """Der Mailtext als abzulegendes Dokument.

    Der Text SELBST ist Schriftverkehr — eine Kündigung, eine Zusage, eine
    Rückfrage vom Amt steht oft im Text und nicht im Anhang. Deshalb wird er
    auch dann abgelegt, wenn kein Anhang dabei war.

    Er trägt außerdem, was mit den Anhängen geschah. Das ist die Stelle, an
    der ein verworfener Anhang sichtbar wird: er steht mit Namen und Grund
    hier, statt still zu verschwinden.
    """
    zeilen = [f"Von: {sendung.absender}", f"An: {an}",
              f"Betreff: {sendung.betreff}", f"Datum: {sendung.datum}",
              f"Empfangen: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
              "", (sendung.text or "").strip(), ""]
    if sendung.anhaenge:
        zeilen.append("Anhänge:")
        zeilen += [f"  - {name} ({_kb(len(daten))})"
                   for name, daten in sendung.anhaenge]
        zeilen.append("")
    if sendung.verworfen:
        zeilen.append("Nicht übernommen:")
        zeilen += [f"  - {name}: {grund}" for name, grund in sendung.verworfen]
        zeilen.append("")
    if ergebnis:
        zeilen.append("Abgelegt:")
        zeilen += [f"  - {z}" for z in ergebnis]
        zeilen.append("")
    return "\n".join(zeilen)


# ---------------------------------------------------------------------------
# Der SMTP-Empfänger
# ---------------------------------------------------------------------------

#: Was der Empfänger zurückgibt. Als Konstanten, weil sie an mehreren
#: Stellen stehen und ein Zahlendreher hier verlorene Post bedeutet.
ANTWORT_OK = "250 Message accepted for delivery"
ANTWORT_RCPT_OK = "250 OK"
ANTWORT_UNBEKANNT = "550 5.1.1 Unbekannter Empfänger"
ANTWORT_ZUVIEL = "451 4.7.0 Zu viele Sendungen — bitte später erneut"
ANTWORT_GROSS = "552 5.3.4 Sendung zu groß"
ANTWORT_EMPFAENGER = "452 4.5.3 Zu viele Empfänger"
ANTWORT_KEIN_INHALT = "451 4.3.0 Leere Sendung"


class Posteingang:
    """Der aiosmtpd-Handler. Bewusst ohne aiosmtpd-Import.

    `handle_RCPT` und `handle_DATA` bekommen `session` und `envelope`
    durchgereicht und lesen daran nur `peer`, `mail_from`, `rcpt_tos` und
    `content`. Dadurch ist der ganze Empfangsweg ohne Netz und ohne
    laufenden Server prüfbar — und die Tests messen den Code, nicht die
    Bibliothek.
    """

    def __init__(self, babu: Babu | None = None, grenzen: Grenzen | None = None,
                 domaene: str | None = None) -> None:
        self.babu = babu or Babu()
        self.grenzen = grenzen or Grenzen.aus_umgebung()
        self.domaene = (domaene or os.environ.get("BABU_POST_DOMAENE")
                        or "post.babu.0711.io").strip().lower()
        self.rate_ip = Rate(self.grenzen.rate_ip, self.grenzen.fenster)
        self.rate_adresse = Rate(self.grenzen.rate_adresse, self.grenzen.fenster)

    # -- Hilfen ------------------------------------------------------------

    @staticmethod
    def _ip(session) -> str:
        peer = getattr(session, "peer", None)
        if isinstance(peer, (tuple, list)) and peer:
            return str(peer[0])
        return str(peer or "?")

    def _lokal(self, adresse: str) -> str:
        """Lokaler Teil, wenn die Domäne stimmt — sonst "".

        Kleinschreibung, `+`-Zusatz weg, Domäne geprüft. Dieselbe Regel wie
        `postadresse.normieren` in babu-web; sie steht hier ein zweites Mal,
        weil dieser Dienst die Datenbank nicht kennt und ein RCPT nicht erst
        über das Netz gehen soll, um als Unsinn erkannt zu werden.
        """
        wert = (adresse or "").strip().lower().strip("<>")
        if "@" not in wert:
            return ""
        lokal, domaene = wert.rsplit("@", 1)
        if domaene != self.domaene:
            return ""
        lokal = lokal.split("+", 1)[0]
        if not (3 <= len(lokal) <= 64):
            return ""
        if not all(z.isalnum() or z == "-" for z in lokal) or lokal.startswith("-"):
            return ""
        return lokal

    # -- SMTP --------------------------------------------------------------

    async def handle_RCPT(self, server, session, envelope, address,  # noqa: N802,ARG002
                          rcpt_options):  # noqa: ARG002
        """Kein Relay: nur bekannte Adressen kommen durch.

        Die Reihenfolge der Prüfungen ist Absicht — erst das billige
        Rate-Limit auf die IP, dann Form und Domäne (kein Netz), erst
        zuletzt die Auflösung über babu-web. Wer den Dienst mit
        Zufallsadressen bewirft, erzeugt damit keine HTTP-Last.
        """
        # Das Rate-Limit steht VOR der Empfängerzählung, nicht dahinter:
        # sonst dürfte jemand in einer offenen Sitzung endlos RCPTs
        # nachschieben und bekäme sie umsonst mit 452 beantwortet.
        if not self.rate_ip.erlaubt(self._ip(session)):
            return ANTWORT_ZUVIEL
        if len(envelope.rcpt_tos) >= self.grenzen.empfaenger_max:
            return ANTWORT_EMPFAENGER
        lokal = self._lokal(address)
        if not lokal:
            return ANTWORT_UNBEKANNT
        if not self.rate_adresse.erlaubt(lokal):
            return ANTWORT_ZUVIEL
        try:
            mandant_id = self.babu.aufloesen(lokal)
        except BabuFehler as ex:
            print(f"[posteingang] Auflösung fehlgeschlagen: {ex}", flush=True)
            # NICHT 550: babu-web ist weg, die Adresse gibt es womöglich
            # sehr wohl. Der absendende Server hebt die Mail auf.
            return ANTWORT_ZUVIEL
        if mandant_id is None:
            return ANTWORT_UNBEKANNT
        # Ist `handle_RCPT` da, trägt der Handler die Empfänger selbst ein —
        # so will es aiosmtpd. Was hier nicht angehängt wird, kommt in
        # `handle_DATA` nicht an.
        envelope.rcpt_tos.append(address)
        return ANTWORT_RCPT_OK

    async def handle_DATA(self, server, session, envelope):  # noqa: N802,ARG002
        """Zerlegen und weiterreichen — je Empfänger einmal.

        Die Zuordnung wird hier NEU gefragt und nicht aus `handle_RCPT`
        mitgeschleppt. Ein Zwischenspeicher am Handler lebte über alle
        Verbindungen hinweg (aiosmtpd hält genau eine Handler-Instanz) und
        wäre damit ein Zustand, den niemand aufräumt. Teuer ist die zweite
        Frage nicht: `Babu.aufloesen` antwortet 60 Sekunden lang aus seinem
        eigenen Zwischenspeicher, ohne Netz.
        """
        rohdaten = envelope.content or b""
        if isinstance(rohdaten, str):
            rohdaten = rohdaten.encode("utf-8", "replace")
        if not rohdaten:
            return ANTWORT_KEIN_INHALT
        if len(rohdaten) > self.grenzen.sendung_max:
            return ANTWORT_GROSS
        sendung = zerlegen(rohdaten, self.grenzen)
        for rcpt in envelope.rcpt_tos:
            lokal = self._lokal(rcpt)
            try:
                mandant_id = self.babu.aufloesen(lokal) if lokal else None
            except BabuFehler as ex:
                print(f"[posteingang] Auflösung fehlgeschlagen: {ex}", flush=True)
                return ANTWORT_ZUVIEL
            if mandant_id is None:
                # Nur erreichbar, wenn die Adresse zwischen RCPT und DATA
                # stillgelegt wurde — oder wenn jemand `handle_DATA` ohne
                # `handle_RCPT` fährt. Dann ist Ablegen genau falsch.
                continue
            try:
                self.ausliefern(sendung, mandant_id, rcpt)
            except BabuFehler as ex:
                print(f"[posteingang] Ablegen fehlgeschlagen: {ex}", flush=True)
                return ANTWORT_ZUVIEL
        return ANTWORT_OK

    # -- Weiterreichen -----------------------------------------------------

    def ausliefern(self, sendung: Sendung, mandant_id: int, an: str) -> list[str]:
        """Anhänge zuerst, der Mailtext zuletzt.

        Die Reihenfolge ist nicht beliebig: der Mailtext trägt das Protokoll
        dessen, was mit den Anhängen geschah, und kann es erst danach
        kennen. Bricht etwas mittendrin ab, wiederholt der absendende Server
        die Mail — babu-web legt bytegleiche Dateien nicht zweimal ab.
        """
        ergebnis: list[str] = []
        for name, daten in sendung.anhaenge:
            antwort = self.babu.beleg(mandant_id, name, daten)
            if antwort.get("dublette"):
                ergebnis.append(f"{name}: war schon da")
            else:
                ergebnis.append(f"{name}: {antwort.get('datei') or 'abgelegt'}")
        stempel = time.strftime("%Y%m%d-%H%M%S")
        titel = f"E-Mail · {sendung.betreff or sendung.absender or 'ohne Betreff'}"
        self.babu.dokument(mandant_id, f"mail-{stempel}.txt",
                           mailtext(sendung, an, ergebnis).encode("utf-8"),
                           titel)
        return ergebnis


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

def tls_kontext() -> ssl.SSLContext | None:
    """STARTTLS, wenn Zertifikat und Schlüssel da sind — sonst ohne.

    Kein Abbruch ohne Zertifikat: eingehendes SMTP zwischen Fremdservern ist
    im Netz überwiegend opportunistisch verschlüsselt. Ein Dienst, der ohne
    Zertifikat gar nicht startet, nimmt gar keine Post an — das ist
    schlechter als unverschlüsselt angenommene Post.
    """
    zert = (os.environ.get("POSTEINGANG_TLS_ZERT") or "").strip()
    schluessel = (os.environ.get("POSTEINGANG_TLS_SCHLUESSEL") or "").strip()
    if not zert or not schluessel:
        return None
    kontext = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    kontext.load_cert_chain(zert, schluessel)
    return kontext


def controller(handler: Posteingang | None = None, host: str | None = None,
               port: int | None = None):
    """Der aiosmtpd-Controller — lazy importiert.

    Der Import steht hier und nicht oben, damit der ganze Empfangsweg
    (Zerlegen, Grenzen, Rate-Limit, Weiterreichen) ohne die Bibliothek
    prüfbar bleibt.
    """
    from aiosmtpd.controller import Controller  # noqa: PLC0415

    handler = handler or Posteingang()
    # `port is not None` und nicht `port or …`: Port 0 heißt „such dir einen
    # freien" (so fährt der Test einen echten Server) und ist falsy — mit
    # `or` landete er auf 25, und der Test scheiterte an fehlenden Rechten
    # statt an seiner Sache.
    return Controller(
        handler,
        hostname=host or os.environ.get("POSTEINGANG_HOST") or "0.0.0.0",  # noqa: S104
        port=port if port is not None else _zahl("POSTEINGANG_PORT", 25),
        # Die SIZE-Ankündigung: ein Absender erfährt die Grenze, bevor er
        # 25 MB durch die Leitung schiebt.
        data_size_limit=handler.grenzen.sendung_max,
        tls_context=tls_kontext(),
        ident="babu posteingang")


def main() -> None:  # pragma: no cover — der Betriebsweg
    handler = Posteingang()
    if not handler.babu.pat or not handler.babu.token:
        raise SystemExit("BABU_POSTEINGANG_PAT und BABU_POSTEINGANG_TOKEN "
                         "müssen gesetzt sein — ohne sie kommt keine Post an.")
    c = controller(handler)
    c.start()
    print(f"[posteingang] nimmt Post für @{handler.domaene} an "
          f"({c.hostname}:{c.port}, TLS: "
          f"{'ja' if tls_kontext() else 'nein'})", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        c.stop()


if __name__ == "__main__":  # pragma: no cover
    main()
