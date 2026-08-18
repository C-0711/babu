# babu Landing-Page (Startseite babu.0711.io)

Self-contained Marketing-/Landing-Page in einfacher Sprache: Hero, 3 Schritte,
App-Screenshots, Kostenvergleich (Beispielrechnung), Salon-Nutzen, Kassenbuch,
Steuerberater-Wechsel (Buhl als steuerliches Backend), App-laden, Konto &
Finanzamt-Post, FAQ, Profi-Upload im Footer, Babu-Chat-Widget.

## Dateien

- `index.html` — Quelle (referenziert `bilder/*.png`), für lokale Arbeit.
- `bilder/` — echte App-Screenshots aus dem Simulator (simctl, sips -Z 860).

## Deploy (Static-Swap, kein pm2-Restart)

```
ssh h200v 'cp ~/babu-web/index.html ~/babu-web/index.html.vor-landing-JJJJMMTT'
scp index-deploy.html h200v:~/babu-web/index.html
```

`GET /` liefert die Datei direkt (babu_web.py, Env `BABU_SEITE`).
Live seit 18.08.2026; Backup: `~/babu-web/index.html.vor-landing-20260818`.

⚠️ Die Landing muss in den Portal-Branch
(`claude/project-handover-context-7bfaa2`) übernommen werden, sonst
überschreibt deren nächstes Deploy die Startseite (Task-Chip existiert).

## Babu-Chat

Das Widget ruft `POST /api/babu-chat` (SSE, Golden-Format). Bis der öffentliche
Endpoint existiert (Spec 2026-08-18-landing-onboarding.md, Auftrag 2),
antwortet es aus einem eingebauten Fragen-Katalog. Der öffentliche Bot darf
NIE Belegdaten-Kontext bekommen.
