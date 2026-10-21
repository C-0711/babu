#!/usr/bin/env python3
"""Was vor dem Einreichen stimmen muss — gelesen, nicht erinnert.

Zwei Ablehnungen (24.09. und 05.10.2026) scheiterten an Formularen, nicht
am Code. Diese Liste geht jeden Punkt durch, liest ihn über die API und
sagt, was fehlt. Sie ändert nichts.

    asc_pruefung.py          # alles
    asc_pruefung.py kurz     # nur, was noch offen ist

Jede Zeile trägt ihren Grund: warum Apple das verlangt oder woran es
schon einmal gescheitert ist. Was hier grün ist, wurde geprüft — nicht
angenommen.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asc_api as a  # noqa: E402

APP = "6811956687"
#: Die Größen, die Apple für iPhone-Screenshots nimmt.
SCREENSHOT_SETS = ("APP_IPHONE_67", "APP_IPHONE_65")

befunde: list[tuple[bool, str, str]] = []


def pruefe(ok: bool, was: str, grund: str = "") -> bool:
    befunde.append((ok, was, grund))
    return ok


def v2(pfad: str):
    req = urllib.request.Request("https://api.appstoreconnect.apple.com/v2" + pfad,
                                 headers={"Authorization": "Bearer " + a.token()})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError:
        return None


def seiten(pfad: str) -> list:
    aus = []
    while pfad:
        r = a.api("GET", pfad)
        if not r["ok"]:
            return aus
        aus += r["daten"]["data"]
        nxt = r["daten"].get("links", {}).get("next")
        pfad = nxt.split("/v1", 1)[1] if nxt else None
    return aus


# ---------------------------------------------------------------------------
# Das Konto: ohne das verkauft die App nichts
# ---------------------------------------------------------------------------

def konto() -> None:
    d = v2(f"/appAvailabilities/{APP}/territoryAvailabilities?limit=200")
    gebiete = d["data"] if d and "data" in d else []
    kann = [g for g in gebiete
            if "CANNOT_SELL" not in (g["attributes"].get("contentStatuses") or [])]
    # Was hier gemessen wird, ist Apples `CANNOT_SELL` — NICHT der Vertrag
    # selbst. Den gibt die API nicht her (/paidApplicationsAgreements,
    # /agreements, /taxForms, /bankAccounts antworten alle 404). Der
    # Zusammenhang ist erschlossen, nicht belegt, und am 17.10.2026 stand
    # CANNOT_SELL noch in allen 175 Gebieten, waehrend der Auftraggeber den
    # Vertrag als erledigt meldete. Beides kann stimmen: Apple traegt es
    # verzoegert nach. Deshalb sagt der Befund jetzt, was er sieht, und
    # nicht, was er daraus schliesst.
    pruefe(bool(kann), "Apple erlaubt den Verkauf (kein CANNOT_SELL)",
           "CANNOT_SELL in allen Gebieten. Haeufigster Grund ist das Paid "
           "Applications Agreement (Business → Agreements: muss Active "
           "sein, nicht Pending) — den Vertrag selbst kann diese Pruefung "
           "nicht sehen"
           if not kann else f"verkaufbar in {len(kann)} Gebieten")
    ohne = [g for g in gebiete
            if "TRADER_STATUS_NOT_PROVIDED" in (g["attributes"].get("contentStatuses") or [])]
    pruefe(not ohne, "Trader Status gesetzt",
           f"fehlt in {len(ohne)} EU-Gebieten — ohne ihn fällt die App aus "
           "den EU-Storefronts (Business → Trader Status)" if ohne else "")
    an = [g for g in gebiete if g["attributes"].get("available")]
    pruefe(len(an) >= 1, "App ist irgendwo verfügbar", f"{len(an)} Gebiete")


# ---------------------------------------------------------------------------
# Der laufende Pruefvorgang — der blockiert stiller als alles andere
# ---------------------------------------------------------------------------

#: Zustaende, in denen Apple keine neue Einreichung annimmt. UNRESOLVED_ISSUES
#: heisst: eine Einreichung wurde abgelehnt und liegt offen; der Grund steht
#: NUR im Resolution Center der Weboberflaeche, die API gibt ihn nicht her
#: (appStoreVersionForReview und submittedByActor antworten 403).
#:
#: `READY_FOR_REVIEW` steht NICHT darin, und das ist der Unterschied, der
#: am 15.10.2026 einen Fehlalarm erzeugt hat: so heisst auch die leere,
#: vorbereitete Huelle, die App Store Connect selbst anlegt und in die die
#: Abos erst hinein sollen. Sie traegt kein `submittedDate` — daran, und nur
#: daran, lassen sich die beiden auseinanderhalten.
BLOCKIERT = {"UNRESOLVED_ISSUES", "WAITING_FOR_REVIEW", "IN_REVIEW"}


def pruefvorgang() -> None:
    """Haengt noch eine alte Einreichung offen?

    Am 14.10.2026 stand hier eine Ablehnung vom 08.10. — die Version war
    PREPARE_FOR_SUBMISSION und sah damit sauber aus, /appStoreVersionSubmission
    gab 404, und doch nahm Apple nichts Neues an. Deshalb wird der Vorgang
    getrennt von der Version geprueft.
    """
    r = a.api("GET", f"/apps/{APP}/reviewSubmissions?limit=10")
    if not r["ok"]:
        pruefe(False, "Pruefvorgaenge lesbar", f"HTTP {r['status']}")
        return
    offen = [s for s in (r["daten"].get("data") or [])
             if s["attributes"].get("state") in BLOCKIERT
             and s["attributes"].get("submittedDate")]
    if not offen:
        pruefe(True, "Kein alter Pruefvorgang offen")
        return
    for s in offen:
        at = s["attributes"]
        abgelehnt = 0
        it = a.api("GET", f"/reviewSubmissions/{s['id']}/items")
        if it["ok"]:
            abgelehnt = sum(1 for i in (it["daten"].get("data") or [])
                            if i["attributes"].get("state") == "REJECTED")
        pruefe(False, "Kein alter Pruefvorgang offen",
               f"{at.get('state')} vom {(at.get('submittedDate') or '?')[:10]}"
               + (f", {abgelehnt} abgelehnt" if abgelehnt else "")
               + " — in App Store Connect unter App Review die Nachricht "
                 "lesen und beantworten oder die Einreichung zuruecknehmen")

# ---------------------------------------------------------------------------
# Die Version und ihr Build
# ---------------------------------------------------------------------------

def version() -> dict:
    vs = a.api("GET", f"/apps/{APP}/appStoreVersions?limit=1")["daten"]["data"]
    if not vs:
        pruefe(False, "Es gibt eine Version", "keine gefunden")
        return {}
    v = vs[0]
    at = v["attributes"]
    pruefe(at["appStoreState"] in ("PREPARE_FOR_SUBMISSION", "REJECTED",
                                   "DEVELOPER_REJECTED", "READY_FOR_REVIEW"),
           f"Version {at['versionString']} ist bearbeitbar", at["appStoreState"])
    b = a.api("GET", f"/appStoreVersions/{v['id']}/build")
    build = b["daten"].get("data") if b["ok"] else None
    pruefe(bool(build), "Ein Build hängt an der Version",
           f"Build {build['attributes']['version']}, "
           f"{build['attributes']['processingState']}" if build
           else "keiner — ohne Build keine Einreichung")
    if build:
        pruefe(build["attributes"]["processingState"] == "VALID",
               "Der Build ist verarbeitet", build["attributes"]["processingState"])
        pruefe(build["attributes"].get("usesNonExemptEncryption") is False,
               "Export-Compliance beantwortet",
               "sonst fragt Apple nach und die Prüfung steht")
    return v


# ---------------------------------------------------------------------------
# Die Texte — hier liegt die Pflicht aus 3.1.2
# ---------------------------------------------------------------------------

def texte(v: dict, stufen: list[dict]) -> None:
    locs = a.api("GET", f"/appStoreVersions/{v['id']}/appStoreVersionLocalizations"
                 )["daten"]["data"]
    pruefe(bool(locs), "Es gibt Store-Texte")
    for loc in locs:
        at = loc["attributes"]
        sp = at["locale"]
        text = (at.get("description") or "") + " " + (at.get("promotionalText") or "")
        pruefe(len(at.get("description") or "") > 200,
               f"Beschreibung ({sp}) ist gefüllt",
               f"{len(at.get('description') or '')} Zeichen")
        # App Store Review 3.1.2: Titel, Laufzeit und Preis jedes Abos
        # müssen in der Beschreibung oder im Programm selbst stehen.
        preise = [f"{s['cent'] // 100},{s['cent'] % 100:02d}" for s in stufen]
        fehlend = [p for p in preise if p not in text]
        pruefe(not fehlend, f"Beschreibung ({sp}) nennt jeden Abo-Preis",
               f"fehlt: {', '.join(fehlend)} — App Store Review 3.1.2"
               if fehlend else "")
        pruefe(re.search(r"\bMonat\b|\bmonatlich\b|\bmonth\b", text, re.I) is not None,
               f"Beschreibung ({sp}) nennt die Laufzeit",
               "3.1.2 verlangt die Länge des Abo-Zeitraums")
        pruefe(re.search(r"kündig|cancel", text, re.I) is not None,
               f"Beschreibung ({sp}) sagt, wie man kündigt")
        pruefe(bool(at.get("supportUrl")), f"Support-Adresse ({sp})",
               at.get("supportUrl") or "fehlt — Pflichtfeld")
        # Screenshots je Sprache
        sets = a.api("GET", f"/appStoreVersionLocalizations/{loc['id']}"
                     "/appScreenshotSets?include=appScreenshots&limit=20")
        vorhanden = {s["attributes"]["screenshotDisplayType"]:
                     len(s["relationships"]["appScreenshots"].get("data") or [])
                     for s in (sets["daten"]["data"] if sets["ok"] else [])}
        for art in SCREENSHOT_SETS:
            pruefe(vorhanden.get(art, 0) >= 1, f"Screenshots {art} ({sp})",
                   f"{vorhanden.get(art, 0)} Stück")


# ---------------------------------------------------------------------------
# Was der Prüfer bekommt
# ---------------------------------------------------------------------------

def pruefangaben(v: dict) -> None:
    r = a.api("GET", f"/appStoreVersions/{v['id']}/appStoreReviewDetail")
    d = r["daten"].get("data") if r["ok"] else None
    if not pruefe(bool(d), "Es gibt Prüfangaben"):
        return
    at = d["attributes"]
    for feld, name in (("contactFirstName", "Vorname"), ("contactLastName", "Name"),
                       ("contactPhone", "Telefon"), ("contactEmail", "E-Mail")):
        pruefe(bool(at.get(feld)), f"Kontakt: {name}", at.get(feld) or "fehlt")
    notiz = at.get("notes") or ""
    pruefe(len(notiz) > 100, "Prüfnotiz ist gefüllt", f"{len(notiz)} Zeichen")
    # Die Antwort auf die Ablehnung vom 05.10. argumentierte, babu brauche
    # KEINE In-App-Käufe, weil es nur an Unternehmer verkauft. Seit dem
    # 10.10. hat die App welche — der Satz widerspräche dem, was der
    # Prüfer sieht.
    alt = re.search(r"businesses only|entrepreneurs|B2B", notiz, re.I)
    pruefe(not alt, "Prüfnotiz ohne das alte B2B-Argument",
           f"steht noch drin: „{alt.group(0)}“" if alt else "")
    # Und sie muss sagen, WIE man an den Kaufweg kommt: mit dem Portal-Konto
    # sieht der Prüfer die Stufen nie (paket.stand prüft herkunft='app').
    pruefe(re.search(r"Los geht|storage|Ablage|subscription", notiz, re.I) is not None,
           "Prüfnotiz erklärt den Weg zum Kauf",
           "sonst sucht der Prüfer die Stufen und findet sie nicht")
    if at.get("demoAccountRequired"):
        pruefe(bool(at.get("demoAccountName")) and bool(at.get("demoAccountPassword")),
               "Prüfkonto hinterlegt", at.get("demoAccountName") or "fehlt")


# ---------------------------------------------------------------------------
# Die drei Stufen
# ---------------------------------------------------------------------------

def abos() -> list[dict]:
    g = a.api("GET", f"/apps/{APP}/subscriptionGroups?include=subscriptions&limit=10")
    gruppen = g["daten"]["data"] if g["ok"] else []
    if not pruefe(len(gruppen) == 1, "Genau eine Abo-Gruppe", f"{len(gruppen)}"):
        return []
    subs = [i for i in g["daten"].get("included", []) if i["type"] == "subscriptions"]
    pruefe(len(subs) == 3, "Drei Stufen", f"{len(subs)}")
    stufen = []
    for s in subs:
        at, sid = s["attributes"], s["id"]
        pid = at["productId"]
        # `READY_TO_SUBMIT` heisst „fertig konfiguriert" — und genau NICHT
        # „der Einreichung beigelegt". Beides zu verwechseln hat am
        # 15.10.2026 eine Ablehnung gekostet (3.1.1/3.1.3(c)): der Pruefer
        # sah eine App ohne jeden In-App-Kauf. Darum zaehlt der Zustand
        # unten noch einmal eigens.
        pruefe(at["state"] in ("READY_TO_SUBMIT", "WAITING_FOR_REVIEW",
                               "IN_REVIEW", "APPROVED"),
               f"{pid}: bereit", at["state"])
        pruefe(at["subscriptionPeriod"] == "ONE_MONTH", f"{pid}: monatlich",
               at["subscriptionPeriod"])
        pruefe(bool(at.get("reviewNote")), f"{pid}: Prüfnotiz")
        bild = a.api("GET", f"/subscriptions/{sid}/appStoreReviewScreenshot")
        pruefe(bool((bild["daten"] or {}).get("data")), f"{pid}: Prüfbild")
        locs = a.api("GET", f"/subscriptions/{sid}/subscriptionLocalizations?limit=10")
        sprachen = {x["attributes"]["locale"] for x in locs["daten"]["data"]} \
            if locs["ok"] else set()
        pruefe("de-DE" in sprachen, f"{pid}: deutscher Text", ", ".join(sorted(sprachen)))
        preise = seiten(f"/subscriptions/{sid}/prices?limit=200")
        pruefe(len(preise) >= 170, f"{pid}: Preise in allen Gebieten",
               f"{len(preise)} — Apple verlangt jeden Markt, auch ungenutzte")
        # Ablehnung vom 22.10.2026 (2.1(b)): Abos nur in DEU, der Pruefer
        # testet mit einer Sandbox-Kennung aus einem anderen Land, StoreKit
        # liefert ihm nichts — „wir finden die In-App-Kaeufe nicht". Die App
        # bleibt in DEU; die Abos muessen ueberall stehen.
        av = a.api("GET", f"/subscriptions/{sid}/subscriptionAvailability")
        av_id = ((av["daten"] or {}).get("data") or {}).get("id") if av["ok"] else None
        gebiete = seiten(f"/subscriptionAvailabilities/{av_id}/availableTerritories"
                         "?limit=200") if av_id else []
        pruefe(len(gebiete) >= 170, f"{pid}: in jeder Storefront verfügbar",
               f"{len(gebiete)} — sonst sieht ein Prüfer aus einem anderen Land "
               "keine Produkte (asc_abos.py ueberall)")
        deu = a.api("GET", f"/subscriptions/{sid}/prices?filter[territory]=DEU"
                    "&include=subscriptionPricePoint&limit=5")
        cent = None
        for inc in (deu["daten"].get("included", []) if deu["ok"] else []):
            if inc["type"] == "subscriptionPricePoints":
                cent = round(float(inc["attributes"]["customerPrice"]) * 100)
        stufen.append({"pid": pid, "cent": cent or 0, "state": at["state"]})
    return stufen


# ---------------------------------------------------------------------------

def abos_eingereicht(stufen: list[dict]) -> None:
    """Liegen die Abos einer Einreichung bei?

    **Nicht am Zustand des Abos ablesbar.** Das war mein erster Versuch und
    er war falsch: ein Abo bleibt `READY_TO_SUBMIT`, auch wenn es einer
    Einreichung beiliegt — der Zustand wandert erst, wenn Apple es wirklich
    prueft. Am 17.10.2026 meldete die Pruefung deshalb „liegt nicht bei",
    obwohl alle drei seit dem 15.10. in der Einreichung standen.

    Was es wirklich sagt, sind die Eintraege der Einreichung. Ihre IDs
    tragen eine Typmarke: `|6|` ist die App-Version, `|18|` ein Abo. Die
    Marke ist undokumentiert, also wird sie nur zum Zaehlen benutzt und nie
    zum Entscheiden ueber einen einzelnen Eintrag — die Frage hier lautet
    bloss: haengt ausser der Version noch etwas drin?

    Der Einzelabruf eines Eintrags (`/reviewSubmissionItems/<id>`) gibt 403,
    die Zuordnung Eintrag -> Abo ist also nicht zu haben.
    """
    r = a.api("GET", f"/apps/{APP}/reviewSubmissions?limit=10")
    if not r["ok"]:
        pruefe(False, "Die Abos liegen einer Einreichung bei",
               f"Einreichungen nicht lesbar (HTTP {r['status']})")
        return
    beigelegt = 0
    for s in (r["daten"].get("data") or []):
        if s["attributes"].get("state") == "COMPLETE":
            continue
        it = a.api("GET", f"/reviewSubmissions/{s['id']}/items")
        if not it["ok"]:
            continue
        beigelegt += sum(1 for i in (it["daten"].get("data") or [])
                         if "|18|" in i["id"]
                         or "|18|" in _entschluesselt(i["id"]))
    pruefe(beigelegt >= len(stufen) and len(stufen) > 0,
           "Die Abos liegen einer Einreichung bei",
           f"{beigelegt} von {len(stufen)} — in App Store Connect: Version "
           "1.0, Abschnitt In-App-Kaeufe und Abos, zur Ueberpruefung "
           "hinzufuegen (die API kann das nicht)"
           if beigelegt < len(stufen) else f"{beigelegt} Eintraege")


def _entschluesselt(ident: str) -> str:
    """Die Eintrags-ID ist base64; die Typmarke steht erst darin."""
    import base64  # noqa: PLC0415
    try:
        return base64.urlsafe_b64decode(
            ident + "=" * (-len(ident) % 4)).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def main(kurz: bool = False) -> int:
    print("App Store Connect — babu Belege\n")
    konto()
    pruefvorgang()
    v = version()
    st = abos()
    abos_eingereicht(st)
    if v:
        texte(v, st)
        pruefangaben(v)
    offen = [b for b in befunde if not b[0]]
    for ok, was, grund in befunde:
        if kurz and ok:
            continue
        zeichen = "✓" if ok else "✗"
        print(f"  {zeichen} {was}" + (f"  — {grund}" if grund else ""))
    print(f"\n{len(befunde) - len(offen)} von {len(befunde)} in Ordnung.")
    if offen:
        print(f"{len(offen)} offen:")
        for _ok, was, _g in offen:
            print(f"  • {was}")
    return 1 if offen else 0


if __name__ == "__main__":
    sys.exit(main(kurz=len(sys.argv) > 1 and sys.argv[1] == "kurz"))
