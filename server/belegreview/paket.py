#!/usr/bin/env python3
"""Die Stufen: wie viel Platz ein Betrieb gebucht hat — und was frei ist.

Entschieden am 10.10.2026: **Funktionen trennen die Stufen nie, nur der
Speicher.** Jede Stufe kann alles; wer mehr ablegen will, bucht mehr Platz.
Bezahlt wird über das Apple-Abo, der Platz liegt in Deutschland.

Wer die App lädt, bekommt die ersten **zehn Belege frei** und entscheidet
danach. Diese Regel gilt nur für Konten, die über den App Store gekommen
sind (`mandant.herkunft = "app"`) — die Betriebe aus dem Portal arbeiten
unverändert weiter, mit Testmonat und Stripe wie bisher.

Reine Rechnung ohne Datenbank und ohne Netz, damit sie prüfbar bleibt.
"""
from __future__ import annotations

import uuid

GB = 1024 ** 3

#: Die Stufen in der Reihenfolge, in der sie jemandem angeboten werden.
#: `apple` ist die Produkt-Kennung im App Store, `cent` der Endpreis dort
#: (inklusive Umsatzsteuer — Apple zeigt nie netto).
STUFEN: dict[str, dict] = {
    "klein":  {"gb": 1,   "cent": 999,  "apple": "babu.speicher.1gb"},
    "mittel": {"gb": 5,   "cent": 1999, "apple": "babu.speicher.5gb"},
    "gross":  {"gb": 100, "cent": 9900, "apple": "babu.speicher.100gb"},
}

#: So viele Belege darf jemand ablegen, bevor er eine Stufe braucht.
BELEGE_FREI = 10

#: Ab diesem Anteil des Kontingents wird gewarnt — früh genug, um in Ruhe
#: zu wechseln, spät genug, um nicht zu nerven.
WARNUNG_AB = 0.9

#: Woher ein Betrieb kommt. Nur „app" unterliegt den Regeln dieses Moduls.
HERKUNFT_APP = "app"


def grenze(stufe: str | None) -> int | None:
    """Wie viele Bytes diese Stufe trägt — None heißt: keine Grenze."""
    eintrag = STUFEN.get(stufe or "")
    return eintrag["gb"] * GB if eintrag else None


def stufe_fuer_produkt(apple_produkt: str | None) -> str | None:
    """Vom Apple-Produkt zur Stufe. Unbekanntes bleibt None — eine fremde
    Kennung darf niemals stillschweigend zu einem Kontingent werden."""
    for name, eintrag in STUFEN.items():
        if eintrag["apple"] == apple_produkt:
            return name
    return None


#: Namensraum für `kauf_kennung`. Fest und für immer: aus ihm und der
#: Mandantennummer entsteht dieselbe UUID, solange es babu gibt. Er ist kein
#: Geheimnis — er muss nur eindeutig sein, damit die Kennung eines anderen
#: Dienstes nie zufällig dieselbe ist.
KAUF_NAMENSRAUM = uuid.UUID("7b3a0e22-6c41-5f8a-9d10-0711bab00001")


def kauf_kennung(mandant_id: int) -> str:
    """Die `appAccountToken`, die beim Kauf mitgeht — je Betrieb immer dieselbe.

    Apple nimmt beim Kauf eine UUID der Anwendung an, trägt sie in jeden
    Vorgang dieses Abos ein und schickt sie in jeder Server Notification
    zurück. Damit lässt sich ein Kauf einem Betrieb zuordnen, **ohne** dass
    die App dem Server etwas erzählen muss — und das ist der Fall, der sonst
    offen bleibt: Apples erste Meldung kommt manchmal, bevor die App ihren
    Kauf gemeldet hat, und ein neu aufgesetztes Telefon meldet gar nichts,
    bis sich jemand anmeldet.

    Abgeleitet und nicht gespeichert: eine UUIDv5 aus Namensraum und Nummer
    ist für denselben Betrieb immer dieselbe, über Neuinstallationen,
    Gerätewechsel und Datenbankumzüge hinweg. Eine Spalte hätte dieselbe
    Zahl noch einmal gehalten — und wäre irgendwann leer gewesen.

    Die Nummer selbst steht NICHT in der Kennung: UUIDv5 ist ein Hash,
    Apples Protokoll bekommt also keine fortlaufende Betriebsnummer zu sehen.
    """
    return str(uuid.uuid5(KAUF_NAMENSRAUM, f"mandant:{int(mandant_id)}"))


def mandant_aus_kauf_kennung(kennung: str | None,
                             kandidaten) -> int | None:
    """Zurück von der Kennung zum Betrieb — über die Kandidaten, nicht umgekehrt.

    Ein Hash lässt sich nicht umkehren, also wird vorwärts gerechnet und
    verglichen. Das kostet eine UUID je Betrieb und läuft nur auf dem
    Rückfallweg (Apples Meldung zu einem Abo, das noch keinem Betrieb
    gehört).
    """
    gesucht = str(kennung or "").strip().lower()
    if not gesucht:
        return None
    for nummer in kandidaten:
        if kauf_kennung(nummer) == gesucht:
            return int(nummer)
    return None


def angebot() -> list[dict]:
    """Die Stufen für die App — Name, Platz, Preis, Apple-Kennung."""
    return [{"stufe": name, "gb": e["gb"], "cent": e["cent"],
             "apple": e["apple"]} for name, e in STUFEN.items()]


def stand(*, herkunft: str | None, stufe: str | None,
          verbraucht: int | None, belege: int | None) -> dict | None:
    """Wie der Betrieb beim Platz dasteht — oder None, wenn ihn das nicht
    betrifft (alle Konten aus dem Portal).

    Rückgabe:
      `stufe`       die gebuchte Stufe oder None (noch im Freikontingent)
      `grenze`      Bytes, die zur Verfügung stehen
      `verbraucht`  Bytes, die belegt sind
      `voll`        kein Platz mehr für Neues
      `knapp`       über der Warnschwelle, aber noch Platz
      `belege`      abgelegte Belege (zählt nur im Freikontingent)
      `frei_offen`  wie viele der zehn freien noch übrig sind
    """
    if herkunft != HERKUNFT_APP:
        return None
    verbraucht = max(0, int(verbraucht or 0))
    belege = max(0, int(belege or 0))
    if stufe not in STUFEN:
        # Ohne gebuchte Stufe zählen die Belege, nicht die Bytes: „zehn
        # Belege frei" ist leichter zu verstehen als „50 Megabyte frei".
        offen = max(0, BELEGE_FREI - belege)
        return {"stufe": None, "grenze": None, "verbraucht": verbraucht,
                "voll": offen == 0, "knapp": offen <= 3 and offen > 0,
                "belege": belege, "frei_offen": offen}
    platz = grenze(stufe) or 0
    return {"stufe": stufe, "grenze": platz, "verbraucht": verbraucht,
            "voll": verbraucht >= platz,
            "knapp": platz > 0 and verbraucht >= platz * WARNUNG_AB
                     and verbraucht < platz,
            "belege": belege, "frei_offen": None}


def text(st: dict | None) -> str | None:
    """Was der Nutzerin dazu gesagt wird — in ihrer Sprache, ohne Technik.

    None heißt: es gibt nichts zu sagen, alles hat Platz."""
    if not st:
        return None
    if st["stufe"] is None:
        if st["voll"]:
            return ("Deine zehn freien Belege sind abgelegt. Such dir einen "
                    "Platz aus, dann geht es weiter — deine Belege bleiben, "
                    "wo sie sind.")
        if st["knapp"]:
            eins = st["frei_offen"] == 1
            return (f"Noch {st['frei_offen']} {'Beleg' if eins else 'Belege'} "
                    "frei.")
        return None
    if st["voll"]:
        return ("Deine Ablage ist voll. Mit der nächsten Stufe hast du sofort "
                "wieder Luft — alles Abgelegte bleibt, wo es ist.")
    if st["knapp"]:
        return "Deine Ablage wird knapp."
    return None
