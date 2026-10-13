#!/usr/bin/env python3
"""Der gemeinsame Hero aller babu-Startseiten: die Welten.

Friseur (/), Barber (/barber), Werkstatt (/werkstatt) — jede Welt hat ihren
Helden (Babs, Moe, Mario). Ganz oben auf jeder Seite steht EIN Hero: das Bild
der eigenen Welt breit, darauf Überschrift, Text und Knöpfe; die anderen Welten
schauen daneben herein und führen per Klick (oder Wischen) hinüber — und von
dort genauso zurück. Reihenfolge überall gleich, damit man sich orientiert.

Eine Quelle für alle drei Seiten: dieses Modul schreibt den Block zwischen die
Marken `welten:start`/`welten:ende` (HTML), `welten-css:…` und `welten-js:…`.

    python3 werbung/welten.py        # schreibt server/babu-web/index.html (Friseur)

Barber und Werkstatt bauen ihre Seiten aus der Friseur-Seite und rufen
`einsetzen(html, "<welt>")` (werbung/barber/seite_bauen.py, werbung/werkstatt/…).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

WELTEN = [
    {"schluessel": "friseur", "pfad": "/", "bild": "/bilder/fr-held.jpg",
     "alt": "Babs lacht in ihrem hellen Salon mit einer Stammkundin, die einen Kaffee hält",
     "name": "Friseursalons", "held": "Babs",
     "lbl": "babu · für deinen Salon",
     "sub": ("Beleg fotografieren — fertig. babu liest ihn, prüft ihn und\n  legt ihn sicher ab. "
             "Am Monatsende ist deine Buchhaltung fertig — ganz ohne\n  eigenes Steuerbüro. "
             "Du schneidest weiter Haare.")},
    {"schluessel": "barber", "pfad": "/barber", "bild": "/bilder/ba-held.jpg",
     "alt": "Moe lacht in seinem Barbershop mit einem Stammkunden im Stuhl, der ein Glas Tee hält",
     "name": "Barbershops", "held": "Moe",
     "lbl": "babu · für deinen Barbershop",
     "sub": ("Beleg fotografieren — fertig. babu liest ihn, prüft ihn und legt ihn sicher ab. "
             "Am Monatsende ist deine Buchhaltung fertig — ganz ohne eigenes Steuerbüro. "
             "Du kümmerst dich um Fades und Bärte.")},
    {"schluessel": "werkstatt", "pfad": "/werkstatt", "bild": "/bilder/ws-held.jpg",
     "alt": "Mario lacht in seiner Werkstatt mit einem Stammkunden, beide mit einem Tässchen Kaffee, das Auto steht auf der Hebebühne",
     "name": "Kfz-Werkstätten", "held": "Mario",
     "lbl": "babu · für deine Werkstatt",
     "sub": ("Beleg fotografieren — fertig. babu liest ihn, prüft ihn und legt ihn sicher ab. "
             "Am Monatsende ist deine Buchhaltung fertig — ganz ohne eigenes Steuerbüro. "
             "Du schraubst weiter.")},
]

HAKEN_SVG = ('<svg viewBox="0 0 16 16" fill="none"><path d="M3.5 8.5l3 3 6-7" stroke="#fff" '
             'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>')

UMSCHALTER = """
      <div class="sprache welt-oben" role="group" aria-label="Sprache">
        <button type="button" data-sprache="de" aria-pressed="true">Deutsch</button>
        <button type="button" data-sprache="tr" aria-pressed="false">Türkçe</button>
      </div>"""


def html(aktiv: str, umschalter: bool = False) -> str:
    teile = []
    ai = next(i for i, w in enumerate(WELTEN) if w["schluessel"] == aktiv)
    for i, w in enumerate(WELTEN):
        if i == ai:
            teile.append(f"""    <div class="welt aktiv">
      <img src="{w['bild']}" width="1600" height="893" alt="{w['alt']}">{UMSCHALTER if umschalter else ''}
      <div class="welt-inhalt">
        <div class="lbl">{w['lbl']}</div>
        <h1>Dein Papierkram<br>macht sich von selbst.</h1>
        <p class="sub">{w['sub']}</p>
        <div class="cta">
          <a class="knopf voll" href="/app">App laden</a>
          <a class="knopf zart" href="/portal">Anmelden</a>
        </div>
        <div class="haken">
          <span class="hakenkreis">{HAKEN_SVG}</span>
          Grüner Haken = alles erledigt. Mehr musst du nicht wissen.
        </div>
      </div>
    </div>""")
        else:
            pfeil = f"← mit {w['held']}" if i < ai else f"mit {w['held']} →"
            teile.append(f"""    <a class="welt" href="{w['pfad']}">
      <img src="{w['bild']}" width="1600" height="893" loading="lazy" alt="{w['alt']}">
      <span class="welt-text"><b>{w['name']}</b><span>{pfeil}</span></span>
    </a>""")
    return ("<!-- welten:start — geschrieben von werbung/welten.py, nicht von Hand ändern -->\n"
            '<section class="welten-hero" aria-label="babu für Friseursalons, Barbershops und Kfz-Werkstätten">\n'
            '  <div class="welten-bahn">\n' + "\n".join(teile) + "\n  </div>\n</section>\n"
            "<!-- welten:ende -->")


CSS = """/* welten-css:start — werbung/welten.py */
/* ── Welten-Hero: eine Welt breit mit Überschrift, die anderen schauen herein ── */
.welten-hero{padding:18px 18px 0}
@media(min-width:720px){.welten-hero{padding:22px 22px 0}}
.welten-bahn{display:flex;gap:10px;height:640px}
.welt{position:relative;flex:1 1 0;min-width:0;border-radius:22px;overflow:hidden;
  display:block;text-decoration:none;color:#fff;background:#1f1d1b;
  transition:flex-grow .45s ease}
.welt.aktiv{flex-grow:5}
a.welt:hover,a.welt:focus-visible{flex-grow:1.5}
.welt img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;
  object-position:48% 30%;transition:transform .6s ease}
a.welt:hover img{transform:scale(1.05)}
.welt::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(to top,rgba(18,16,12,.86) 0%,rgba(18,16,12,.55) 38%,rgba(18,16,12,0) 68%)}
a.welt::after{background:linear-gradient(to top,rgba(18,16,12,.82),rgba(18,16,12,.25))}
.welt-inhalt{position:absolute;left:0;right:0;bottom:0;z-index:1;padding:0 34px 30px;text-align:left}
.welt-inhalt .lbl{color:#e8d9b5;margin-bottom:12px}
.welt-inhalt h1{color:#fff;font-size:clamp(34px,5.2vw,62px);line-height:1.04;margin-bottom:14px;
  text-shadow:0 2px 18px rgba(0,0,0,.35)}
.welt-inhalt .sub{color:rgba(255,255,255,.9);font-size:16px;max-width:560px;margin-bottom:20px}
.welt-inhalt .cta{justify-content:flex-start}
.welt-inhalt .knopf.voll{background:#fff;color:var(--gc-fg)}
.welt-inhalt .knopf.zart{background:rgba(255,255,255,.16);color:#fff;border:1px solid rgba(255,255,255,.45)}
.welt-inhalt .haken{display:inline-flex;align-items:center;gap:10px;margin-top:18px;
  color:#cfe3cd;font-weight:600;font-size:14px}
.welt-text{position:absolute;left:16px;right:12px;bottom:18px;z-index:1;display:flex;flex-direction:column;gap:3px}
.welt-text b{font:600 clamp(15px,1.7vw,21px) "Playfair Display",Georgia,serif;letter-spacing:-.01em}
.welt-text span{font-size:12.5px;opacity:.92}
.welt-oben{position:absolute;top:16px;right:16px;z-index:2}
@media(max-width:719px){
  .welten-bahn{flex-wrap:wrap;height:auto}
  .welt.aktiv{flex:1 1 100%;height:600px;order:-1}
  a.welt{flex:1 1 40%;height:120px}
  a.welt:hover,a.welt:focus-visible{flex-grow:1}
  .welt-inhalt{padding:0 20px 22px}
  .welt-inhalt .sub{font-size:15px}
}
@media (prefers-reduced-motion:reduce){.welt,.welt img{transition:none}}
/* welten-css:ende */"""

JS = """/* welten-js:start — werbung/welten.py */
/* ── Welten: Wischen wechselt wie ein Klick auf die Nachbarwelt. ───────── */
(function(){
  var bahn=document.querySelector('.welten-bahn'); if(!bahn) return;
  var welten=[].slice.call(bahn.querySelectorAll('.welt')), x0=null;
  var hier=welten.findIndex(function(w){return w.classList.contains('aktiv');});
  bahn.addEventListener('touchstart',function(e){x0=e.touches[0].clientX;},{passive:true});
  bahn.addEventListener('touchend',function(e){
    if(x0===null) return; var dx=e.changedTouches[0].clientX-x0; x0=null;
    if(Math.abs(dx)<60) return;
    var ziel=welten[hier+(dx<0?1:-1)];
    if(ziel&&ziel.getAttribute('href')) location.href=ziel.getAttribute('href');
  },{passive:true});
})();
/* welten-js:ende */"""


def _zwischen(t: str, start: str, ende: str, neu: str) -> str:
    a, b = t.index(start), t.index(ende) + len(ende)
    # die Zeile mit der Start-/Ende-Marke gehört ganz dazu
    return t[:a] + neu + t[b:]


def einsetzen(t: str, aktiv: str, umschalter: bool = False) -> str:
    t = _zwischen(t, "<!-- welten:start", "<!-- welten:ende -->", html(aktiv, umschalter))
    t = _zwischen(t, "/* welten-css:start", "/* welten-css:ende */", CSS)
    t = _zwischen(t, "/* welten-js:start", "/* welten-js:ende */", JS)
    return t


def main() -> int:
    p = REPO / "server" / "babu-web" / "index.html"
    t = p.read_text(encoding="utf-8")
    t = einsetzen(t, "friseur")
    p.write_text(t, encoding="utf-8")
    print(f"{p.relative_to(REPO)}: Welten-Hero geschrieben ({len(t) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
