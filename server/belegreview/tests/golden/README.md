# Golden-Fixtures (Stand 13.08.2026)

Baseline vor dem Portal-Umbau — die iOS-Verträge sind eingefroren.

- `review_weingaertle.json` — `GET /review/20260812-225200-c781d6-beleg_2026-07-21_weingaerty_22bf8b36`,
  `python3 -m json.tool --sort-keys`-normalisiert. **Muss nach jedem Deploy byte-gleich bleiben**
  (Vergleich: gleicher curl + json.tool, dann `diff`).
- `chat_sse_mitschnitt.txt` — `POST /chat` mit `{"stream":true}`. Antwort-**Text** ist nicht
  deterministisch (Temperatur 0.2); geprüft wird die **Protokollform**: Zeilen `data: {"d": …}`,
  Abschluss `data: [DONE]`, Content-Type `text/event-stream`.

Abruf (auf der H200V, Service-PAT):

```bash
PAT=$(tr -d '[:space:]' < ~/gitchain-eingang/.pat_babu)
curl -s -H "Authorization: Bearer $PAT" http://127.0.0.1:7844/review/<stamm> | python3 -m json.tool --sort-keys
```
