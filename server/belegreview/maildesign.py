#!/usr/bin/env python3
"""Das babu-E-Mail-Design — eine Funktion, alle Mails.

Die Portal-Startseite (mybabu.io) ist die Vorlage, seit 16.09.2026 mit
Bildern: warmes Papier (#faf9f5), Serifen-Überschrift (Georgia als
Playfair-Ersatz), Beige #857b61 als EINE Signalfarbe, grüner Haken für
Vertrauen. Die Fotos der Startseite liegen unter
{ursprung}/bilder/*.jpg — extern geladen (https, mit Alt-Text und
Höhenangabe, damit das Layout ohne Bild nicht springt). Ein Bild, das
nicht lädt, ist kein Verlust: die Mail steht auch ohne.

Wie auf der Startseite gilt: kein Chamfer, kein grelles Orange, keine
Webfonts. `mail(kopf, text)` baut eine Multipart-Alternative (text + html)
— die Textfassung bleibt Wort für Wort erhalten, schlichte Clients,
Bildschirmleser und Spam-Filter sehen dieselben Wörter wie vorher.
"""
from __future__ import annotations

import html
import re
from email.message import EmailMessage

# Palette wie index.html :root — bewusst abgeschrieben, damit Mail und
# Seite dieselbe Handschrift haben.
FARBE = {
    "canvas": "#faf9f5", "bg": "#ffffff", "fg": "#111111",
    "body": "#333333", "desc": "#555555", "muted": "#999999",
    "accent": "#857b61", "accent_hover": "#736950",
    "accent_subtle": "#f0ebe3", "ok": "#6f8a6e",
    "border": "#e5e7eb", "gold": "#c9b98d", "warn": "#b0821f",
    "desk": "#efece6",
}
SANS = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
SERIF = "Georgia,'Times New Roman',serif"

# Die Fotos der Startseite — dieselben Dateien, dieselbe Stimmung.
# urprung ist die Wurzel der Umgebung (PORTAL_ORIGIN); default die
# Produktiv-Domain, damit auch die Dev-Lane ihre eigenen Bilder lädt.
def _bilder(ursprung: str) -> dict[str, str]:
    w = (ursprung or "https://mybabu.io").rstrip("/")
    return {
        "hero": f"{w}/bilder/start-2-anmelden.jpg",
        "foto": f"{w}/bilder/start-3-foto.jpg",
        "fertig": f"{w}/bilder/start-4-fertig.jpg",
    }


def _adressat_gruss(text: str) -> str:
    """„Hallo Nina, …" → Vorname für die Anrede-Zeile, leer ohne Gruß."""
    m = re.match(r"^\s*(?:Hallo|Guten Tag|Hi)\s+([A-Za-zÄÖÜäöüß][\w-]*)\s*,", text)
    return m.group(1) if m else ""


def _koerper_html(text: str, bilder: dict[str, str]) -> str:
    """Der Textkörper als HTML: Absätze, eingerückte Blöcke (4 Leerzeichen
    oder Tab), Schritt-Listen, Listen, fette **Wörter**."""
    absaetze = re.split(r"\n\s*\n", text.strip())
    teile: list[str] = []
    for absatz in absaetze:
        zeilen = [z.rstrip() for z in absatz.splitlines()]
        # Einzugsblock (Einladungslink, Wartelisten-Angaben, Start-up-Guide):
        # 4 Leerzeichen oder Tab am Anfang — als abgesetzte Karte bzw.
        # Schrittliste. Ein Link darin wird zum Knopf MIT sichtbarer URL.
        eingerueckt = (zeilen and (zeilen[0].startswith("    ")
                                   or zeilen[0].startswith("\t")))
        laeufer: list[str] = []
        punkte: list[str] = []
        liste: list[str] = []
        schritte_liste: list[str] = []
        for z in zeilen:
            gestutzt = z.strip()
            schritt_m = re.match(r"^(\d+[.)])\s+(.+)$", gestutzt) if eingerueckt else None
            if schritt_m:
                if laeufer:
                    punkte.append(" ".join(laeufer)); laeufer = []
                schritte_liste.append(schritt_m.group(2))
            elif re.match(r"^\s*([-•]|\d+[.)])\s+", z) and not eingerueckt:
                if laeufer:
                    punkte.append(" ".join(laeufer)); laeufer = []
                liste.append(re.sub(r"^\s*([-•]|\d+[.)])\s+", "", z))
            elif not z:
                if laeufer:
                    punkte.append(" ".join(laeufer)); laeufer = []
            elif eingerueckt and re.match(r"^https?://", gestutzt) and len(gestutzt) > 24:
                if laeufer:
                    punkte.append(" ".join(laeufer)); laeufer = []
                punkte.append("KARTE:" + gestutzt)
            elif eingerueckt and not schritte_liste:
                laeufer.append(gestutzt)
            elif eingerueckt and schritte_liste and not re.match(r"^\d+[.)]", gestutzt):
                # Fortsetzungszeile eines Schritts (Umbruch im Text) — anhängen.
                schritte_liste[-1] += " " + gestutzt
            else:
                laeufer.append(gestutzt)
        if laeufer:
            punkte.append(" ".join(laeufer))
        # **fett** — das schreibt babu_web vereinzelt in Mailtexte
        esc = lambda s: html.escape(s).replace("**", "<b>", 1).replace("**", "</b>", 1) if "**" in s else html.escape(s)  # noqa: E731
        inner = ""
        if schritte_liste:
            # Der Start-up-Guide: nummerierte Schritte mit Kreis-Ziffern in
            # Beige — dieselbe Zählweise wie die „So funktioniert babu"-
            # Schritte der Startseite. Schritt mit Kamera/Foto zeigt das
            # Foto aus der Startseite daneben.
            for nr, s in enumerate(schritte_liste, 1):
                ist_foto = any(w in s for w in ("fotografier", "Kamera", "abfotograf"))
                inner += (
                    "<div style='margin:16px 0'>"
                    "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
                    "<td style='vertical-align:top;width:34px'>"
                    "<div style='width:26px;height:26px;border-radius:50%;"
                    "background:#857b61;color:#fff;text-align:center;"
                    f"font:600 13px/26px {SANS}'>{nr}</div></td>"
                    f"<td style='vertical-align:top;padding-top:1px;font:15px/1.55 {SANS};color:#333'>"
                    + html.escape(s))
                if ist_foto:
                    inner += (
                        "<img src='" + bilder["foto"] + "' alt='Beleg abfotografieren'"
                        " width='520' height='647' "
                        "style='display:block;width:100%;max-width:520px;height:auto;"
                        "border-radius:14px;margin-top:10px;border:1px solid #e5e7eb'>")
                inner += "</td></tr></table></div>"
        if liste:
            inner += "<ul style='margin:6px 0 10px;padding-left:20px;color:#333'>"
            inner += "".join(f"<li style='margin:3px 0'>{esc(p)}</li>" for p in liste)
            inner += "</ul>"
        for i, p in enumerate(punkte):
            if not p:
                continue
            if p.startswith("KARTE:"):
                url = p[6:]
                inner += ("<div style='margin:14px 0;padding:16px;"
                          "background:#f0ebe3;border-radius:12px;text-align:center'>"
                          "<a href='" + html.escape(url, quote=True) + "' "
                          "style='display:inline-block;padding:13px 28px;"
                          "background:#111;color:#fff;text-decoration:none;"
                          "border-radius:10px;font:600 14px " + SANS + "'>"
                          "Jetzt öffnen ›</a>"
                          "<div style='font-size:12px;color:#857b61;margin-top:8px;"
                          "word-break:break-all'>" + html.escape(url) + "</div></div>")
            elif eingerueckt and i == 0:
                inner += ("<div style='margin:10px 0;padding:12px 16px;"
                          "background:#f0ebe3;border-radius:10px;"
                          "font-size:15px;color:#111'>" + esc(p) + "</div>")
                eingerueckt = False
            else:
                inner += ("<p style='margin:10px 0;color:#333;font-size:15px'>"
                          + esc(p) + "</p>")
        teile.append(inner)
    return "".join(teile)


def mail(an: str, betreff: str, text: str, *, von: str,
          ursprung: str = "https://mybabu.io") -> EmailMessage:
    """Die fertige Nachricht: Text UND Design-HTML, dieselben Wörter.

    `ursprung` ist die Wurzel, unter der /bilder/ liegt — im Betrieb
    PORTAL_ORIGIN, damit Dev-Mails Dev-Bilder laden.
    """
    m = EmailMessage()
    m["From"] = von
    m["To"] = an
    m["Subject"] = betreff
    bilder = _bilder(ursprung)
    vorname = _adressat_gruss(text)
    grusszeile = (f"Für {vorname}" if vorname
                  else "babu — dein Papierkram macht sich von selbst")
    html_koerper = f"""<!doctype html>
<html lang="de"><body style="margin:0;padding:0;background:#efece6">
<div style="display:none;max-height:0;overflow:hidden">Dein Papierkram macht sich von selbst.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#efece6;padding:24px 12px"><tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%">
<tr><td style="padding:2px 12px 10px;font:600 20px {SERIF};color:#111;letter-spacing:-.02em">
  <span style="color:#857b61">babu</span></td></tr>
<tr><td style="padding:0;border-radius:14px 14px 0 0;overflow:hidden">
  <img src="{bilder['hero']}" alt="babu — Beleg fotografieren, fertig" width="560" height="698"
       style="display:block;width:100%;height:auto"></td></tr>
<tr><td style="background:#faf9f5;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;padding:26px 26px 8px">
  <div style="font:600 11px {SANS};letter-spacing:.14em;text-transform:uppercase;color:#857b61;margin:0 0 12px">{html.escape(grusszeile)}</div>
  <h1 style="font:600 24px/1.22 {SERIF};color:#111;margin:0 0 6px;letter-spacing:-.015em">{html.escape(betreff)}</h1>
  <div style="width:44px;height:3px;background:#c9b98d;border-radius:2px;margin:10px 0 14px"></div>
</td></tr>
<tr><td style="background:#faf9f5;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;padding:6px 26px 10px">
{_koerper_html(text, bilder)}
</td></tr>
<tr><td style="background:#faf9f5;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 14px 14px;padding:14px 26px 18px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
  <td style="font:15px {SERIF};color:#6f8a6e;font-weight:600;width:26px;vertical-align:top">✓</td>
  <td style="font:600 13px {SANS};color:#6f8a6e;vertical-align:top;padding-top:1px">
    Alles erledigt — mehr musst du nicht wissen.</td></tr></table>
</td></tr>
<tr><td style="padding:16px 12px 6px;font:12px/1.55 {SANS};color:#999">
  babu · 0711 Intelligence · Stuttgart · <a href="https://mybabu.io" style="color:#857b61;text-decoration:none">mybabu.io</a><br>
  babu ersetzt keine individuelle Steuerberatung.
</td></tr>
</table></td></tr></table>
</body></html>"""
    m.set_content(text)
    m.add_alternative(html_koerper.strip(), subtype="html")
    return m
