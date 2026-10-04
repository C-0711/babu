"""Bank — Freigabe, Dateiimport und Kanzleiansicht (seit 04.10.2026).

Plan Kanzleiansicht, Schritte B1–B3. Dieses Modul hängt sich wie die
anderen Familien per `setup(app, bw)` an den Kern.

B1: Der Betrieb gibt seiner Kanzlei die Kontoumsätze zum LESEN frei — mit
Fassung des Texts (`recht.BANK_FREIGABE`), widerrufbar, nachvollziehbar im
Audit-Log. Die Kanzlei kann anfragen; der Betrieb bekommt dann eine Mail.
Ob die Freigabe schon gebraucht wird, entscheidet der Schalter
`BABU_BANK_FREIGABE` (siehe `bankrecht`); die Freigabe selbst lässt sich
auch vorher schon erteilen.
"""
from __future__ import annotations

import json

import time
from datetime import datetime, timedelta, timezone

from fastapi import Request
from fastapi.responses import JSONResponse, Response

import audit
import bankrecht
import mandanten
import recht

bw = None   # der Kern, gesetzt von setup()

#: Wie oft eine Kanzlei höchstens anfragt: einmal am Tag.
ANFRAGE_ABSTAND = timedelta(hours=24)


def setup(app, kern):
    """Der Kern reicht sich selbst herein — siehe kern_warteliste.setup."""
    global bw
    bw = kern
    for methode, pfad, fn in _ROUTEN:
        getattr(app, methode.lower())(pfad)(fn)


def _fehler(text: str, code: int) -> JSONResponse:
    return JSONResponse({"fehler": text}, status_code=code)


def _kontext(request: Request):
    """Angemeldet, Betrieb bekannt — und ob eine Kanzlei fragt."""
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler:
        return None, None, False, fehler
    mandant_id = bw._AKTIVER_MANDANT.get(None)  # noqa: SLF001
    if mandant_id is None:
        return None, None, False, _fehler(
            "Für diesen Zugang gibt es keinen Betrieb mit Kontoumsätzen.", 409)
    return un, mandant_id, bool(bw._ALS_KANZLEI.get()), None  # noqa: SLF001


def _mandant(mandant_id: int) -> dict:
    with mandanten.sitzung(None) as c:
        z = c.execute("SELECT m.besitzer_un, m.name, k.name FROM mandant m "
                      "JOIN kanzlei k ON k.id = m.kanzlei_id WHERE m.id=?",
                      (mandant_id,)).fetchone()
    return ({"besitzer": z[0], "betrieb": z[1], "kanzlei": z[2]} if z
            else {"besitzer": None, "betrieb": None, "kanzlei": None})


def _stand_aussen(mandant_id: int) -> dict:
    stand = mandanten.bank_stand(mandant_id)
    titel, text = recht.BANK_FREIGABE
    aktuell = recht.fassung("bank_freigabe")
    m = _mandant(mandant_id)
    return {
        "freigegeben": stand["freigegeben"],
        "am": stand["bank_freigabe_am"], "von": stand["bank_freigabe_von"],
        "fassung": stand["bank_freigabe_fassung"], "fassung_aktuell": aktuell,
        "neue_fassung": bool(stand["freigegeben"]
                             and stand["bank_freigabe_fassung"] != aktuell),
        "widerrufen_am": stand["bank_widerruf_am"],
        "angefragt_am": stand["bank_anfrage_am"],
        "noetig": bankrecht.freigabe_pflicht(),
        "kanzlei": m["kanzlei"], "betrieb": m["betrieb"],
        "titel": titel, "text": text,
    }


def api_freigabe(request: Request) -> Response:
    """Stand der Freigabe — für den Betrieb und für seine Kanzlei."""
    un, mandant_id, _, fehler = _kontext(request)
    if fehler:
        return fehler
    return JSONResponse(_stand_aussen(mandant_id))


async def api_freigeben(request: Request) -> Response:
    """Der Betrieb gibt frei — genau der Fassung, die er gelesen hat."""
    un, mandant_id, als_kanzlei, fehler = _kontext(request)
    if fehler:
        return fehler
    if als_kanzlei or bw.rolle(un) == "mitarbeit":
        return _fehler("Freigeben kann nur die Inhaberin des Betriebs.", 403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    aktuell = recht.fassung("bank_freigabe")
    if str((body or {}).get("fassung") or "") != aktuell:
        return _fehler("Der Text hat sich geändert — bitte noch einmal lesen.", 409)
    mandanten.bank_freigeben(mandant_id, un, aktuell)
    audit.audit(un, "bank_freigabe", mandant_id=str(mandant_id), fassung=aktuell)
    return JSONResponse({"ok": True, **_stand_aussen(mandant_id)})


async def api_widerrufen(request: Request) -> Response:
    """Der Betrieb nimmt die Freigabe zurück."""
    un, mandant_id, als_kanzlei, fehler = _kontext(request)
    if fehler:
        return fehler
    if als_kanzlei or bw.rolle(un) == "mitarbeit":
        return _fehler("Widerrufen kann nur die Inhaberin des Betriebs.", 403)
    mandanten.bank_widerrufen(mandant_id)
    audit.audit(un, "bank_widerruf", mandant_id=str(mandant_id))
    return JSONResponse({"ok": True, **_stand_aussen(mandant_id)})


def _senden(an: str, betreff: str, text: str) -> None:
    import postfach  # noqa: PLC0415
    try:
        ok, hinweis = postfach.senden(an, betreff, text,
                                      stempel=time.strftime("%Y%m%d-%H%M%S"))
        print(f"[bank] Mail an {an}: {hinweis}", flush=True)
    except Exception as ex:  # noqa: BLE001
        print(f"[bank] Mail an {an} fehlgeschlagen: {ex!r}", flush=True)


async def api_anfragen(request: Request) -> Response:
    """Die Kanzlei bittet um die Freigabe — der Betrieb bekommt eine Mail."""
    un, mandant_id, als_kanzlei, fehler = _kontext(request)
    if fehler:
        return fehler
    if not als_kanzlei:
        return _fehler("Anfragen kann das Steuerbüro.", 403)
    stand = mandanten.bank_stand(mandant_id)
    if stand["freigegeben"]:
        return _fehler("Der Betrieb hat schon freigegeben.", 409)
    zuletzt = stand["bank_anfrage_am"]
    if zuletzt:
        try:
            if datetime.now(timezone.utc) - datetime.fromisoformat(zuletzt) < ANFRAGE_ABSTAND:
                return _fehler("Heute wurde schon angefragt — der Betrieb hat "
                               "die Mail.", 429)
        except ValueError:
            pass
    mandanten.bank_anfragen(mandant_id)
    m = _mandant(mandant_id)
    if m["besitzer"] and "@" in m["besitzer"]:
        _senden(m["besitzer"], "babu — dein Steuerbüro bittet um die Kontoumsätze",
                f"Hallo,\n\n{m['kanzlei'] or 'Dein Steuerbüro'} möchte in babu die "
                "Umsätze deiner Geschäftskonten ansehen — um Belege und Zahlungen "
                "abzugleichen und fehlende Belege zu finden. Ansehen heißt nur "
                "lesen: niemand kann damit eine Zahlung auslösen.\n\n"
                "Freigeben oder ablehnen kannst du im Portal unter „Bank“:\n"
                f"{bw.PORTAL_ORIGIN}/portal#bank\n\n"
                "Dein babu-Team")
    audit.audit(un, "bank_anfrage", mandant_id=str(mandant_id))
    return JSONResponse({"ok": True, **_stand_aussen(mandant_id)})


_ROUTEN = [
    ("GET", "/api/bank/freigabe", api_freigabe),
    ("POST", "/api/bank/freigabe", api_freigeben),
    ("POST", "/api/bank/freigabe/widerrufen", api_widerrufen),
    ("POST", "/api/bank/freigabe/anfragen", api_anfragen),
]


# ---------------------------------------------------------------------------
# B2: Bankdateien ablegen, Konten und Umsätze lesen
# ---------------------------------------------------------------------------

import re  # noqa: E402
import threading  # noqa: E402

from fastapi.concurrency import run_in_threadpool  # noqa: E402

import bank_anbindung as ba  # noqa: E402
import bank_camt  # noqa: E402

IMPORT_MAX = 20 * 1024 * 1024
_SCHLOESSER: dict[str, threading.Lock] = {}
_SCHLOSS = threading.Lock()


def _schloss() -> threading.Lock:
    """Lesen-Rechnen-Schreiben je Box nacheinander — zwei Importe zugleich
    überschrieben sonst einer den anderen."""
    with _SCHLOSS:
        return _SCHLOESSER.setdefault(str(bw._box().store), threading.Lock())  # noqa: SLF001


def _json(pfad: str, leer):
    roh = bw.git_show(pfad)
    if not roh:
        return leer
    try:
        return json.loads(roh)
    except ValueError:
        return leer


def _ablegen(un: str, gelesen: dict, roh: bytes, name: str) -> dict:
    import boxschreiber  # noqa: PLC0415
    with _schloss():
        konten = _json("bank/konten.json", [])
        dateien: dict[str, bytes] = {}
        neu_gesamt, monate = 0, set()
        je_konto: dict[str, list] = {}
        for u in gelesen["umsaetze"]:
            je_konto.setdefault(u["konto"], []).append(u)
        for kid, liste in je_konto.items():
            for monat, teil in ba.je_monat(liste).items():
                pfad = f"bank/umsaetze/{kid}/{monat}.json"
                alle, neu = ba.zusammenfuehren(_json(pfad, []), teil)
                if neu:
                    dateien[pfad] = json.dumps(alle, ensure_ascii=False, indent=1).encode()
                    neu_gesamt += neu
                    monate.add(monat)
        doppelt = len(gelesen["umsaetze"]) - neu_gesamt
        if not dateien:
            return {"neu": 0, "doppelt": doppelt, "monate": [], "commit": None}
        stempel = time.strftime("%Y%m%d-%H%M%S")
        sicher = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "datei")[-80:]
        ablage = f"bank/importe/{stempel}-{sicher}"
        for k in gelesen["konten"]:
            konten = ba.konto_dazu(konten, k["iban"], k.get("von"), k.get("bis"),
                                   gelesen["art"], ablage, k.get("saldo"))
        dateien["bank/konten.json"] = json.dumps(konten, ensure_ascii=False,
                                                 indent=1).encode()
        dateien[ablage] = roh
        commit = boxschreiber.schreiben(bw._box(), dateien, None,  # noqa: SLF001
                                        f"bank: {neu_gesamt} Umsätze aus {sicher}", un)
    with bw._box().index_schloss:  # noqa: SLF001
        bw._box().invalidieren()  # noqa: SLF001
    return {"neu": neu_gesamt, "doppelt": doppelt, "monate": sorted(monate),
            "commit": commit}


async def api_import(request: Request) -> Response:
    """Eine Datei der Bank ablegen (CAMT.053, ZIP oder CSV) — nur der Betrieb.

    Die Kanzlei sperrt `bankrecht` schon in der Wache (Phase 0). Dieselbe
    Datei zweimal legt nichts doppelt an.
    """
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    if bw.rolle(un) == "mitarbeit":
        return _fehler("Kontoumsätze legt die Inhaberin ab.", 403)
    form = await request.form()
    datei = form.get("datei")
    if datei is None or not hasattr(datei, "read"):
        return _fehler("Bitte eine Datei wählen.", 400)
    roh = await datei.read(IMPORT_MAX + 1)
    if len(roh) > IMPORT_MAX:
        return _fehler("Die Datei ist größer als 20 MB.", 413)
    try:
        spalten = json.loads(str(form.get("spalten") or "null"))
    except ValueError:
        spalten = None
    try:
        gelesen = bank_camt.lesen(roh, datei.filename or "", str(form.get("iban") or "") or None,
                                  spalten if isinstance(spalten, dict) else None)
    except bank_camt.ImportFehler as f:
        return JSONResponse({"fehler": str(f), "spalten": f.spalten}, status_code=400)
    import boxschreiber  # noqa: PLC0415
    try:
        ergebnis = await run_in_threadpool(_ablegen, un, gelesen, roh, datei.filename or "")
    except boxschreiber.SchreibFehler:
        return _fehler("Gerade nicht speicherbar — gleich noch einmal.", 503)
    return JSONResponse({"ok": True, "art": gelesen["art"],
                         "konten": [ba.iban_kurz(k["iban"]) for k in gelesen["konten"]],
                         **ergebnis})


def api_konten(request: Request) -> Response:
    """Die Konten des Betriebs mit Abdeckung und letztem Saldo."""
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    konten = _json("bank/konten.json", [])
    return JSONResponse({"konten": [
        {"id": k["id"], "iban": ba.iban_kurz(k["iban"]), "saldo": k.get("saldo"),
         "abdeckung": k.get("abdeckung") or []} for k in konten]})


def api_umsaetze(request: Request, monat: str = "", konto: str = "") -> Response:
    """Die Umsätze eines Monats aus den Bankdateien, neueste zuerst."""
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    if not re.fullmatch(r"\d{4}-\d{2}", monat or ""):
        return _fehler("Monat als JJJJ-MM.", 400)
    konten = _json("bank/konten.json", [])
    aus = []
    for k in konten:
        if konto and k["id"] != konto:
            continue
        aus.extend(_json(f"bank/umsaetze/{k['id']}/{monat}.json", []))
    aus.sort(key=lambda u: (u["buchung"], u["id"]), reverse=True)
    return JSONResponse({"monat": monat, "umsaetze": aus})


_ROUTEN += [
    ("POST", "/api/bank/import", api_import),
    ("GET", "/api/bank/konten", api_konten),
    ("GET", "/api/bank/umsaetze", api_umsaetze),
]


# ---------------------------------------------------------------------------
# B3: Abgleich für die Kanzlei — Zahlungen ohne Beleg UND Belege ohne Zahlung
# ---------------------------------------------------------------------------

def _folgemonat(monat: str) -> str:
    j, m = int(monat[:4]), int(monat[5:7])
    return f"{j + (m == 12)}-{(m % 12) + 1:02d}"


def _zahlbar(idx: dict, z: dict) -> bool:
    """Ein Eingangsbeleg, der über das Konto bezahlt wird (nicht bar, keine
    eigene Rechnung, ein Betrag über null)."""
    import extf  # noqa: PLC0415
    review = idx["reviews"].get(z["stamm"]) or {}
    return (bool(review) and (z.get("brutto") or 0) > 0
            and extf.zahlungsart(review) != "bar" and not extf.ist_ausgang(review))


def bank_abgleich(idx: dict, monat: str) -> dict:
    """Der Monat aus Sicht des Kontos — für Kanzleiansicht und Cockpit.

    Die Positionen sind dieselben wie in `/api/abgleich` (kontoauszug.abgleich).
    Neu: welche bezahlbaren Belege des Monats auf dem Konto keine Zahlung
    haben — gesucht im Monat und im Folgemonat, weil eine Rechnung vom 28.
    oft erst im nächsten Monat abgebucht wird.
    """
    import kontoauszug as ka  # noqa: PLC0415
    umsaetze = idx["umsaetze"].get(monat) or []
    if not umsaetze:
        return {"monat": monat, "auszug_da": False}
    ab = ka.abgleich(umsaetze, bw._abgleich_belege(idx))  # noqa: SLF001
    kandidaten = [dict(z) for z in idx["belege"].values()
                  if z["monat"] == monat and z["status"] in ("geprüft", "exportiert")
                  and _zahlbar(idx, z)
                  # Auslagen hat die Mitarbeiterin privat bezahlt (D1) — zu
                  # ihnen gibt es keine Abbuchung, nur die Erstattung.
                  and z["stamm"] not in (idx.get("auslagen") or {})]
    gefunden = ka.abgleich(umsaetze + (idx["umsaetze"].get(_folgemonat(monat)) or []),
                           kandidaten)
    bezahlt = {g["stamm"] for g in gefunden["gedeckt"]}
    ohne = [{"stamm": z["stamm"], "datum": z.get("datum"), "lieferant": z.get("lieferant"),
             "brutto": z.get("brutto")} for z in kandidaten if z["stamm"] not in bezahlt]
    je: dict[str, dict] = {}
    kred = idx.get("kreditor_je_beleg") or {}
    if (idx.get("kreditoren") or {}).get("modus") == "einzeln":
        for z in kandidaten:
            k = kred.get(z["stamm"]) or {}
            nummer = k.get("nummer") or "sammel"
            e = je.setdefault(nummer, {"nummer": k.get("nummer"), "name": k.get("name"),
                                       "belege": 0, "bezahlt": 0, "offen_summe": 0.0})
            e["belege"] += 1
            if z["stamm"] in bezahlt:
                e["bezahlt"] += 1
            else:
                e["offen_summe"] = round(e["offen_summe"] + float(z.get("brutto") or 0), 2)
    stati = [p["status"] for p in ab["positionen"]]
    return {
        "monat": monat, "auszug_da": True, "positionen": ab["positionen"],
        "zaehler": {"umsaetze": len(stati), "mit_beleg": stati.count("gedeckt"),
                    "ohne_beleg": stati.count("fehlt"), "bank": stati.count("bank"),
                    "eingaenge": stati.count("einnahme"),
                    "belege_ohne_zahlung": len(ohne)},
        "fehlend_summe": ab["fehlend_summe"],
        "belege_ohne_zahlung": ohne,
        "je_kreditor": sorted(je.values(), key=lambda e: (-e["offen_summe"],
                                                          e["name"] or "")),
    }


def zahlung_fuer(idx: dict, stamm: str) -> dict | None:
    """Die Abbuchung zu einem Beleg — für „Bezahlt am …“ in der Einzelansicht."""
    import kontoauszug as ka  # noqa: PLC0415
    z = idx["belege"].get(stamm)
    if not z or not z.get("monat") or not _zahlbar(idx, z):
        return None
    umsaetze = ((idx["umsaetze"].get(z["monat"]) or [])
                + (idx["umsaetze"].get(_folgemonat(z["monat"])) or []))
    if not umsaetze:
        return None
    treffer = ka.abgleich(umsaetze, [dict(z)])["gedeckt"]
    if not treffer:
        return None
    u = treffer[0]["umsatz"]
    return {"datum": u.get("datum"), "betrag": u.get("betrag"),
            "gegenpartei": u.get("gegenpartei")}


def api_abgleich(request: Request, monat: str) -> Response:
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    if not re.fullmatch(r"\d{4}-\d{2}", monat or ""):
        return _fehler("Monat als JJJJ-MM.", 400)
    return JSONResponse(bank_abgleich(bw.index_aktuell(), monat))


_ROUTEN += [("GET", "/api/bank/abgleich/{monat}", api_abgleich)]
