"""Das Übergabepaket — Belege, Buchungsstapel und Kassenbuch als ZIP an das
Steuerbüro (seit 10.10.2026).

Der Weg ohne Portal und ohne Kanzlei-Zugang: die Inhaberin tippt „An mein
Steuerbüro geben", babu schickt dem Büro eine Mail mit allem, was es zum
Buchen braucht. Beim ersten Mal fragt babu die Adresse, danach steht sie in
den Einstellungen (`steuerbuero_email`). Kein OneClick, kein DATEV-Konto
auf unserer Seite — eine Mail, die jedes Büro lesen kann.

Was im Paket liegt:

    LIESMICH.txt                          was das ist, wie es eingelesen wird
    EXTF_<stempel>[_NachtragN].csv        der Buchungsstapel (DATEV-Format, derselbe
                                          wie in der Belegbox unter export/<monat>/)
    belege/<JJJJ-MM>/<datei>              jeder Beleg des Stapels als Bild oder PDF
    kassenbuch/<JJJJ-MM>.csv              die Kassentage des Stapels
    inhalt.json                           Liste und Zahlen, maschinenlesbar

Mailserver nehmen keine beliebig großen Anhänge. Ein Paket über
`ANHANG_MAX` geht deshalb in Teilen: Teil 1 trägt Stapel, Kassenbuch und so
viele Belege, wie hineinpassen, jeder weitere Teil nur Belege. Jeder Teil
hat sein eigenes LIESMICH, damit auch Teil 3 allein verständlich ist. Reine
Logik ohne I/O — `tests/test_datev_senden.py`.
"""
from __future__ import annotations

import csv
import io
import json
import os
import zipfile

#: Ab hier wird geteilt (Bytes, vor dem Packen gerechnet — Fotos lassen sich
#: nicht kleiner packen). 18 MB lässt Platz für Mail-Kopf und Base64.
ANHANG_MAX = int(os.environ.get("BABU_PAKET_ANHANG_MAX", str(18 * 1024 * 1024)))


def zeitraum_text(monate: list[str]) -> str:
    return monate[0] if len(monate) == 1 else f"{monate[0]} bis {monate[-1]}"


def paket_name(monate: list[str], nachtrag: int = 0,
               teil: int | None = None, teile: int | None = None) -> str:
    name = "babu_Uebergabe_" + (monate[0] if len(monate) == 1
                                else f"{monate[0]}_bis_{monate[-1]}")
    if nachtrag:
        name += f"_Nachtrag{nachtrag}"
    if teil and teile and teile > 1:
        name += f"_Teil{teil}von{teile}"
    return name + ".zip"


def kassenbuch_csv(blaetter: list[dict]) -> str:
    """Die Kassentage als CSV, ein Tag je Zeile, Semikolon, deutsche Zahlen.

    Die Spalten sind die Felder der Blätter (Datum zuerst), nicht eine
    feste Liste — ein Feld, das babu morgen dazulernt, fehlt dann nicht."""
    zeilen = [b for b in blaetter if isinstance(b, dict)]
    zeilen.sort(key=lambda b: str(b.get("datum") or ""))
    felder: list[str] = ["datum"]
    for b in zeilen:
        for k, v in b.items():
            if k not in felder and not isinstance(v, (dict, list)):
                felder.append(k)
    aus = io.StringIO()
    w = csv.writer(aus, delimiter=";", lineterminator="\r\n")
    w.writerow(felder)
    for b in zeilen:
        w.writerow([_de(b.get(k)) for k in felder])
    return aus.getvalue()


def _de(wert) -> str:
    if wert is None:
        return ""
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if isinstance(wert, float):
        return f"{wert:.2f}".replace(".", ",")
    return str(wert)


def liesmich(*, betrieb: str, zeitraum: str, bezeichnung: str, stapel_datei: str,
             rahmen: str, belege: int, kassentage: int, buchungen: int,
             nachtrag: int, teil: int = 1, teile: int = 1,
             belege_in_diesem_teil: int | None = None) -> str:
    anzahl = belege if belege_in_diesem_teil is None else belege_in_diesem_teil
    zeilen = [
        f"Buchhaltung {betrieb} — {zeitraum}",
        "=" * 60,
        "",
        f"Erzeugt von babu (mybabu.io). Stapel: {bezeichnung}.",
    ]
    if teile > 1:
        zeilen.append(f"Dies ist Teil {teil} von {teile}. Der Buchungsstapel und das "
                      "Kassenbuch liegen in Teil 1; die Belege verteilen sich auf alle Teile.")
    if nachtrag:
        zeilen.append(f"Nachtrag {nachtrag}: nur, was seit der letzten Übergabe dazukam.")
    zeilen += [
        "",
        "Inhalt",
        "------",
    ]
    if teil == 1:
        zeilen += [
            f"  {stapel_datei}",
            f"      Buchungsstapel im DATEV-Format (EXTF, Kontenrahmen {rahmen}, "
            f"{buchungen} Buchungen). Einlesen in DATEV Kanzlei-Rechnungswesen über "
            "Stapelverarbeitung → Import; in Addison über den Buchungsimport "
            "(DATEV-Format). Belegfeld 1 trägt babus Belegnummer — sie steht auch "
            "im Dateinamen des Belegs.",
        ]
        if kassentage:
            zeilen += [
                "  kassenbuch/<Monat>.csv",
                f"      {kassentage} Kassentage (Bar, Karte, Ausgaben je Tag). Die "
                "Tageseinnahmen stehen bereits als Buchungen im Stapel.",
            ]
    zeilen += [
        "  belege/<Monat>/",
        f"      {anzahl} Belege als Foto oder PDF" + (f" (gesamt {belege})" if teile > 1 else "") + ".",
        "  inhalt.json",
        "      dieselbe Liste, maschinenlesbar.",
        "",
        "Was später noch dazukommt, schickt babu als Nachtrag — nur die neuen",
        "Belege, nie denselben Stapel zweimal.",
        "",
        "Rückfragen bitte an den Betrieb (Antwortadresse dieser Mail).",
        "",
    ]
    return "\n".join(zeilen)


def teile_bauen(*, monate: list[str], nachtrag: int, stapel_datei: str,
                stapel_roh: bytes, belege: list[tuple[str, bytes]],
                kassen: dict[str, str], betrieb: str, bezeichnung: str,
                rahmen: str, buchungen: int, kassentage: int,
                grenze: int | None = None) -> list[tuple[str, bytes]]:
    """Die ZIP-Dateien, die verschickt werden: eine — oder mehrere, wenn
    die Belege nicht in eine Mail passen. `belege` sind (Pfad im Paket,
    Bytes), die Pfade beginnen mit `belege/`."""
    grenze = ANHANG_MAX if grenze is None else grenze
    # Zuerst verteilen, dann packen: welcher Beleg in welchen Teil.
    teile_belege: list[list[tuple[str, bytes]]] = [[]]
    kopf = len(stapel_roh) + sum(len(c.encode("utf-8")) for c in kassen.values()) + 4096
    stand = kopf
    for pfad, daten in belege:
        if teile_belege[-1] and stand + len(daten) > grenze:
            teile_belege.append([])
            stand = 4096
        teile_belege[-1].append((pfad, daten))
        stand += len(daten)
    teile = len(teile_belege)
    zeitraum = zeitraum_text(monate)
    aus: list[tuple[str, bytes]] = []
    for i, inhalt in enumerate(teile_belege, 1):
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
            text = liesmich(betrieb=betrieb, zeitraum=zeitraum, bezeichnung=bezeichnung,
                            stapel_datei=stapel_datei, rahmen=rahmen,
                            belege=len(belege), kassentage=kassentage,
                            buchungen=buchungen, nachtrag=nachtrag, teil=i, teile=teile,
                            belege_in_diesem_teil=len(inhalt))
            z.writestr("LIESMICH.txt", text.encode("utf-8"))
            if i == 1:
                z.writestr(stapel_datei, stapel_roh)
                for monat, csv_text in sorted(kassen.items()):
                    z.writestr(f"kassenbuch/{monat}.csv", csv_text.encode("utf-8-sig"))
            for pfad, daten in inhalt:
                z.writestr(pfad, daten, compress_type=zipfile.ZIP_STORED)
            z.writestr("inhalt.json", json.dumps({
                "betrieb": betrieb, "zeitraum": zeitraum, "bezeichnung": bezeichnung,
                "nachtrag": nachtrag, "teil": i, "teile": teile,
                "stapel": stapel_datei if i == 1 else None,
                "kassenbuch": sorted(kassen) if i == 1 else [],
                "belege": [p for p, _ in inhalt],
                "belege_gesamt": len(belege), "buchungen": buchungen,
                "kassentage": kassentage,
            }, ensure_ascii=False, indent=1).encode("utf-8"))
        aus.append((paket_name(monate, nachtrag, i, teile), puffer.getvalue()))
    return aus


def mailtext(*, betrieb: str, zeitraum: str, belege: int, kassentage: int,
             buchungen: int, nachtrag: int, teil: int, teile: int) -> str:
    was = (f"Teil {teil} von {teile} des Übergabepakets" if teile > 1
           else "das Übergabepaket")
    zeilen = [
        "Hallo,",
        "",
        f"im Anhang {was} für {betrieb}, Zeitraum {zeitraum}"
        + (f" (Nachtrag {nachtrag})" if nachtrag else "") + ":",
        "",
    ]
    if teil == 1:
        zeilen.append(f"• Buchungsstapel im DATEV-Format ({buchungen} Buchungen)")
        if kassentage:
            zeilen.append(f"• Kassenbuch ({kassentage} Tage)")
    zeilen += [
        f"• {belege} Belege als Foto oder PDF" + (", verteilt auf die Teile" if teile > 1 else ""),
        "",
        "Die Datei LIESMICH.txt im Paket sagt, wie der Stapel in DATEV oder Addison",
        "eingelesen wird. Rückfragen gehen mit „Antworten“ direkt an den Betrieb.",
        "",
        "Viele Grüße",
        "babu",
        "",
    ]
    return "\n".join(zeilen)
