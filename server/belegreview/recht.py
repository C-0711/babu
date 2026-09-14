"""Impressum, Datenschutz, AGB — eine Quelle für Portal, Landing, App und die
drei eigenen Seiten (`/impressum`, `/datenschutz`, `/agb`).

Die Seiten braucht die Beta App Review bei Apple (eine Datenschutz-URL ist
Pflicht), die App verlinkt sie unter „Rechtliches", das Portal zeigt sie im
Blatt, die Landing-Seite in der Fußzeile. Bis 14.09.2026 lagen die Texte nur
im Portal — als Platzhalter.

**Die Texte hier sind Platzhalter und sagen das selbst.** Pflichtangaben nach
§ 5 DDG, Art. 13 DSGVO und AGB kann und darf niemand erfinden; sie kommen von
der Anwältin und werden in `TEXTE` eingesetzt — sonst nirgends. Solange ein
Text mit `PLATZHALTER` beginnt, meldet `fertig()` False, die Seite sagt es
selbst, und `ios/archiv.sh` warnt vor jedem Upload: so ein Build ist nur für
interne Tester, nicht für die Beta App Review.
"""
from __future__ import annotations

import html

PLATZHALTER = "Text folgt."

TEXTE: dict[str, tuple[str, str]] = {
    "impressum": ("Impressum",
        f"{PLATZHALTER} Hier stehen die Angaben zum Anbieter dieser Seite: "
        "Name, Anschrift, wer vertritt, wie man erreicht, Eintrag im Register "
        "und Steuernummer. Den verbindlichen Wortlaut setzt die Anwältin ein."),
    "datenschutz": ("Datenschutz",
        f"{PLATZHALTER} Hier steht, welche deiner Angaben babu verarbeitet, wofür, "
        "wie lange sie bleiben, wer sie sonst noch sieht und welche Rechte du "
        "hast — Belege und Kontoauszüge, Personalangaben, das Lesen auf einem "
        "eigenen Rechner, Rückmeldungen. Den verbindlichen Wortlaut setzt die "
        "Anwältin ein."),
    "agb": ("Nutzungsbedingungen",
        f"{PLATZHALTER} Hier stehen die Bedingungen für die Erprobung von babu: "
        "was babu tut und was nicht (keine Steuerberatung), was kostenlos ist "
        "und bis wann, wie es endet, wer wofür haftet. Den verbindlichen "
        "Wortlaut setzt die Anwältin ein."),
}

ARTEN = tuple(TEXTE)


def fertig(art: str | None = None) -> bool:
    """Ist der Text kein Platzhalter mehr? Ohne Art: alle drei."""
    arten = [art] if art else list(ARTEN)
    return all(not TEXTE[a][1].startswith(PLATZHALTER) for a in arten)


def als_json() -> dict:
    return {a: {"titel": t, "text": x, "fertig": fertig(a)} for a, (t, x) in TEXTE.items()}


def seite(art: str) -> str:
    """Eine eigenständige Seite im Ton der Landing-Seite — ohne Skript, ohne
    Anmeldung, damit Apple und jede Nutzerin sie ohne Konto lesen können."""
    titel, text = TEXTE[art]
    absaetze = "".join(f"<p>{html.escape(a.strip())}</p>"
                       for a in text.split("\n\n") if a.strip())
    hinweis = ("" if fertig(art) else
               '<p class="hinweis">Dieser Text ist noch ein Platzhalter. '
               'Der verbindliche Wortlaut folgt vor dem Start.</p>')
    links = " · ".join(f'<a href="/{a}">{html.escape(TEXTE[a][0])}</a>' for a in ARTEN)
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(titel)} · babu</title>
<style>
  body{{margin:0;background:#faf8f3;color:#2b2a26;font:16px/1.55 -apple-system,system-ui,Georgia,serif}}
  main{{max-width:680px;margin:0 auto;padding:40px 22px 60px}}
  h1{{font:600 30px/1.2 Georgia,'Times New Roman',serif;margin:0 0 18px}}
  p{{margin:0 0 14px}} .hinweis{{padding:12px 14px;background:#f1ebdc;border-radius:10px;font-size:14px}}
  nav{{font-size:13px;color:#736950;margin-bottom:26px}} nav a,footer a{{color:#736950}}
  footer{{margin-top:40px;font-size:13px;color:#8a8273}}
</style></head><body><main>
<nav><a href="/">babu</a> · {links}</nav>
<h1>{html.escape(titel)}</h1>
{hinweis}
{absaetze}
<footer>babu · 0711 Intelligence · Stuttgart · babu ersetzt keine individuelle Steuerberatung.</footer>
</main></body></html>
"""
