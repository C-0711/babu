# Tenant / Role model — current state (read-only survey)

All paths below are under `/Users/christophbertsch/babu/.claude/worktrees/project-handover-context-7bfaa2/`. Main file: `server/belegreview/babu_web.py` (9586 lines, 166 routes).

---

## 1. Authentication

**Config constants** — `server/belegreview/babu_web.py:39-45`
```python
39  SEITE          = BABU_SEITE            → ~/babu-web/index.html
40  STORE          = BABU_STORE            → ~/inspektor-store/inspektor/ws-christoph0711.io/babu.git
42  GEHEIMNIS_PFAD = BABU_SESSION_GEHEIMNIS→ ~/babu-web/.session_geheimnis
44  PORTAL_ORIGIN  = BABU_ORIGIN           → https://babu.0711.io
45  PORTAL_DB      = BABU_PORTAL_DB        → ~/babu-web/portal.db
250 ERLAUBT        = BABU_ERLAUBT          → {"christoph0711.io"}  (prod: "christoph0711.io,nina0711.io")
```

**Identity resolution chain**
| Function | Line | What it does |
|---|---|---|
| `wer_token(token)` | `babu_web.py:290` | PAT → `GET https://gitchain.de/auth/whoami`, returns `un` lowercase. 5-min cache in module global `_CACHE` (`:287`), keyed by SHA-256 of the token. |
| `app_schluessel_pruefen(token)` | `babu_web.py:315` | iOS device key → SHA-256 lookup in `app_schluessel` table, joined to `nutzer` where `aktiv=1`. |
| `wer(request)` | `babu_web.py:331` | Bearer header → device key first, then PAT. |
| `angemeldet(request)` | `babu_web.py:418` | Cookie **or** Bearer. Cookie path additionally enforces `_origin_ok` for non-GET (CSRF). |

**Session cookie** — `babu_web.py:348-352, 355-388`
- `SESSION_COOKIE = "babu_sitzung"`, `SESSION_DAUER = 30*24*3600` (sliding, refreshed in `/api/ich` `:1313`).
- Payload is only `base64(un|exp) + "." + HMAC-SHA256`, `_signieren` `:367`, `_pruefen` `:373`.
- **The cookie carries no tenant/box claim — only `un`.** Every request re-derives the box from `un`.
- `_geheimnis()` `:356` reads/creates `GEHEIMNIS_PFAD` (0600), single process-wide secret.

**Login routes**
| Route | Line | Notes |
|---|---|---|
| `POST /api/anmelden` | `babu_web.py:1157` | PAT / "Zugangscode". `wer_token` → **hard-gated on `un in ERLAUBT`** (`:1168`) — env allowlist only, no DB. |
| `POST /api/login` | `babu_web.py:1215` | email+password. `nutzer_holen` → `pw_pruefen` (scrypt n=16384,r=8,p=1, `:441-455`). Rate limit 5/min/IP via `_LOGIN_VERSUCHE` (`:1179`). Returns `{un, rolle, box}`. |
| `POST /api/app-anmelden` | `babu_web.py:1248` | same credentials → mints a device key (`app_schluessel`), returned exactly once. |
| `POST /api/passwort` | `babu_web.py:1283` | self-service change. |
| `POST /api/abmelden` | `babu_web.py:1306` | deletes cookie. |
| `GET /api/ich` | `babu_web.py:1313` | `{un, rolle: rolle(un), box: box_mitglied(un)}` — this is what the frontend keys the menu off. |
| `POST /api/signup` | `babu_web.py:2666` | self-registration → `nutzer_anlegen(..., box=False)`, logs the user in immediately but with no box. |
| `POST /api/registrierung` | `babu_web.py:2644` | lead form → `registrierungen` table only. |

**`nutzer` table** — `babu_web.py:64-68` plus ALTERs at `:91` and `:99`
```sql
CREATE TABLE nutzer (
  email TEXT PRIMARY KEY,      -- this IS the `un` for account logins
  name TEXT,
  salon TEXT,                  -- free-text label, NOT a tenant key
  rolle TEXT NOT NULL DEFAULT 'salon',
  pw TEXT NOT NULL,            -- scrypt$salt$hash
  aktiv INTEGER NOT NULL DEFAULT 1,
  angelegt TEXT,
  letzter_login TEXT,
  gehoert_zu TEXT,             -- ALTER :91 — employee → owner's `un`
  box INTEGER NOT NULL DEFAULT 1  -- ALTER :99 — "has a Belegbox?" boolean
);
```
Read by `nutzer_holen` `:468`, written by `nutzer_anlegen` `:481`.

**How `un` maps to a box — this is the crux**
```python
490  def zugelassen(un):     # ERLAUBT ∪ active account
510  def box_mitglied(un):   # babu_web.py:510-524
         inhaber = salon_von(un)
         if inhaber in ERLAUBT: return True
         n = nutzer_holen(un)
         if n and n["rolle"] in ("admin", "kanzlei"): return True    # ← :521-522
         besitzer = nutzer_holen(inhaber)
         return bool(besitzer and besitzer["box"])
3156 def salon_von(un):      # returns nutzer.gehoert_zu or un itself
```
`box_mitglied` returns a **boolean**, not a box identifier. There is no per-salon store lookup anywhere. `STORE` is a module constant; `git_show` `:527`, `_git` `:568`, `_blobs_lesen` `:575` all hardcode `-C str(STORE)`.

**Guards** — `_api_wache` `:1126` (logged in + active), `_box_wache` `:1141` (adds `box_mitglied`). Usage: `_box_wache` 104×, `_api_wache` 25×. `BOX_GESPERRT` message `:1137`.

---

## 2. Roles

**`NUTZER_ROLLEN = ("admin", "kanzlei", "salon", "mitarbeit")`** — `babu_web.py:436`

```python
3145 ROLLEN = {…}  from env BABU_ROLLEN, format "un:rolle,un:rolle"
3149 def rolle(un):
         n = nutzer_holen(un)
         if n: return n["rolle"]
         return ROLLEN.get(un, "kanzlei" if not ROLLEN else "salon")   # ← :3153
3156 def salon_von(un)
3163 def team_recht(un, recht)   # per-person darf_belege / darf_kasse from `team` table
3176 def darf_verwalten(un): return rolle(un) in ("admin", "kanzlei")
3180 def _verwalter_wache(request)
1710 def _mitarbeit_wache(un, recht, was)
```

Production role assignment: `server/docker/compose.yml:24` sets `BABU_ROLLEN: "christoph0711.io:kanzlei"`. Note the fallback at `:3153`: **if `BABU_ROLLEN` is empty, every unknown PAT user is `"kanzlei"`** — a fail-open default that only holds because prod sets the env var.

**What `kanzlei` can do today**
- `box_mitglied` → `True` unconditionally (`:521`) → all 104 `_box_wache` routes.
- `darf_verwalten` → `True` → `/api/export/{monat}.csv` (`:3330`, check at `:3333`), `POST /api/korrektur/{stamm}` (`:2462`, check at `:2465`), `GET /api/registrierungen` (`:2714`, check at `:2719`), and everything behind `_verwalter_wache`.
- Portal: sees the DATEV block on a Beleg (`portal.html:2075`).
- NOT `"mitarbeit"` → passes all 40+ `if rolle(un) == "mitarbeit"` blocks.

**"Zugänge" view — server-side backing routes**

| Route | Line | Guard | Returns |
|---|---|---|---|
| `GET /api/nutzer` | `babu_web.py:3193` | `_verwalter_wache` ✅ | **every row in `nutzer`, unfiltered**: email, name, salon, rolle, aktiv, angelegt, letzter_login, box + a `paket` computed from each user's settings |
| `POST /api/nutzer` | `babu_web.py:3211` | `_verwalter_wache` ✅ | creates account, returns `startpasswort` once |
| `POST /api/nutzer-aktion` | `babu_web.py:3231` | `_verwalter_wache` ✅ | `deaktivieren` / `aktivieren` / `rolle` / `box_freigeben` / `box_sperren` (`:3260`) / `passwort_neu` (`:3266`) — **on any email**, only self-protection at `:3238` |
| `GET /api/registrierungen` | `babu_web.py:2714` | inline `darf_verwalten` ✅ | all signup leads |
| `POST /api/registrierung-einrichten` | `babu_web.py:3275` | `_verwalter_wache` ✅ | lead → account + prefilled settings |

There is **no `/api/zugaenge` and no `/api/einladen`**. The employee-invite path is `POST /api/team-zugang` (`babu_web.py:8657`) — guarded only by `_api_wache` + `rolle != "mitarbeit"` (`:8669`); it creates a `mitarbeit` account and sets `gehoert_zu = un` (`:8697`). The `einladung` table / `einladung.py` is a different feature (free Auswertung leads).

**Answer to "guarded server-side or only hidden in the menu?"** — properly guarded server-side. The menu hiding is cosmetic: `portal.html:3416` `$("#menu-verwaltung").hidden = !(d.rolle === "admin" || d.rolle === "kanzlei")` and `portal.html:3357` for `#verwaltung-knopf`; `ladeVerwaltung()` at `portal.html:4970` even renders "Nur für die Verwaltung." on a 403 (`:4975`).

⚠️ **`passwort_neu` (`:3266`) lets any `kanzlei` user reset any other account's password and read the new one** — with hundreds of Mandanten that is account takeover across tenants, and there is no audit trail.

---

## 3. The index — single-box by construction

```python
553  BILD_ENDUNGEN / BELEG_ENDUNGEN
555  INDEX_TTL   = BABU_INDEX_TTL, default 5.0 s
557  _INDEX_LOCK = threading.Lock()
560  _RECHNUNG_SCHLOSS = threading.Lock()
562  _TERMIN_SCHLOSS   = threading.Lock()
563  _INDEX: dict = {"head": None, "geprueft": 0.0, "belege": {}, "reviews": {},
                     "dokumente": [], "freigaben": {}, "umsaetze": {},
                     "kassenblaetter": {}, "zeiten": {}, "oid_cache": {},
                     "rechnungen": {}}
721  def _index_bauen(head)   # `_git(["ls-tree","-r","HEAD"])` on STORE, fills _INDEX in place
1014 def index_aktuell()      # TTL check → rev-parse HEAD on STORE → rebuild
```
`_index_bauen` writes into `_INDEX` at `:919, 935, 953, 969, 996, 1007-1011`. Callers invalidate with `with _INDEX_LOCK: _INDEX["geprueft"] = 0.0` at ~20 sites (e.g. `:1591, 1703, 1750, 1801, 1979, 2344, 2386, 2423, 2492, 2543, 2606, 3377, 5459, 5474, 5949`).

**Everything module-level that assumes one box:**

| Global | Line | Why it breaks with N tenants |
|---|---|---|
| `STORE` | `:40` | one bare repo path, baked into `_git`, `git_show`, `_blobs_lesen`, `review_pfad` |
| `_INDEX` + `_INDEX_LOCK` | `:557, 563` | one in-memory index, one HEAD, one `oid_cache` |
| `INDEX_TTL` | `:555` | a 5-s TTL × 300 Mandanten = 300 `rev-parse` per 5 s |
| `_BLOB_STAND` | `:5727` | dedupe map `{kopf, pfade}` for one repo's blob OIDs |
| `_SEITEN_CACHE` | `:5755` | blob-OID→page-count; harmless collision-wise but unbounded |
| `_BELEG_VEKTOREN` | `:2139` | semantic-search vectors for one box |
| `_MELDUNGEN_CACHE` | `:5150` | GitLab feedback cache, one project |
| `_RECHNUNG_SCHLOSS` | `:560` | invoice-number lock is global → serializes all tenants |
| `_TERMIN_SCHLOSS`, `_WA_SCHLOSS`, `_NACHTRAG_LOCK`, `_ABSCHLUSS_LOCK` | `:562, 7205, 5055, 4066` | global, not per-tenant |
| `_LLM_SEMAPHORE = Semaphore(1)` | `:4202` | one concurrent LLM call for the whole server |
| `_ABSCHLUSS_JOBS` | `:4065` | in-memory job dict keyed by job id, not tenant |
| `_DB_LOCK` | `:53` | one sqlite writer lock |
| `ERLAUBT` | `:250` | env allowlist of GitChain usernames |
| `BABU_REF` literal `"inspektor/ws-christoph0711.io/babu"` | `:1689, 1706` | hardcoded default returned to the iOS app in the `/ablage` response |

`ABSCHLUSS_TMP` `:4062`, `AUSWERTUNG_TMP` `:4635` are shared scratch dirs. `LOGOS` `:8015`, `TEAM_FOTOS` `:8740`, `AUSWEISE` `:6822` are already sharded per-`un` via `sha256(un)[:16]` (`:8021, 8219, 8746, 6828`) — those are fine.

---

## 4. `boxschreiber.py` — the write path

`server/belegreview/boxschreiber.py`:
```python
23 KLON    = BABU_BOX_KLON     → ~/babu-web/box       # ONE working copy
24 GATEWAY = BABU_GATEWAY      → http://127.0.0.1:7808 (insp-app)
25 REF     = BABU_REF          → inspektor/ws-christoph0711.io/babu
26 PAT_PFAD= BABU_PUSH_PAT     → ~/gitchain-eingang/.pat_babu   # ONE service PAT
27 REMOTE  = BABU_BOX_REMOTE   → f"{GATEWAY}/git/{REF}.git"
38 _SCHLOSS = threading.Lock()  # ONE global write lock
```
Flow (`_commit_und_push` `:83`): `with _SCHLOSS` → `_bereit()` `:60` (clone if missing, `fetch origin`, `reset --hard origin/main`) → `vormerken()` → `git commit --author "<un> <portal@gitchain.local>"` → `git push origin main` → one retry after 0.7 s. Auth via `_pat_umgebung()` `:41`: `GIT_CONFIG_KEY_0=http.extraHeader`, `GIT_CONFIG_VALUE_0=Authorization: Bearer <pat>`.

Public API: `schreiben(rel_pfad|dict, inhalt, nachricht, autor_un)` `:113`, `loeschen(pfade, nachricht, autor_un)` `:135`, `beleg_dateiname(original)` `:188`. `_pfad_pruefen` `:75` rejects absolute paths and `..`.

**To address multiple boxes you would need:** all five module constants become per-box parameters; `KLON` becomes `KLON_BASIS / <box-id>`; `_SCHLOSS` becomes a per-box lock registry (today one Mandant's push blocks all others for the full fetch+reset+push round trip); `PAT_PFAD` either stays one service PAT with gateway-side authorization per ref, or becomes per-box. Note the docstring at `:9-15` explicitly documents "EINE Arbeitskopie mit EINEM Git-Index" as the reason the global lock exists.

Also: `_INDEX` invalidation after a write is unconditional — with N boxes each write would blow away the wrong tenant's cache unless keyed.

---

## 5. Einstellungen — per-user, inconsistently

`PORTAL_DB` = `~/babu-web/portal.db`, schema created on **every** `_db()` call (`babu_web.py:56-217`). Tables, all scoped by a `un TEXT` column (never by salon/tenant id):

`lesestatus` `:59` · `einstellungen` `:62` (PK `un, schluessel`) · `registrierungen` `:65` · `nutzer` `:68` · `abschluss_status` `:73` (PK `un`) · `team` `:76` (+ ALTER `darf_belege, darf_kasse, zugang` `:83-88`) · `termin` `:104` · `kundin` `:115` · `behandlung` `:120` · `leistung` `:128` · `mitarbeiter` `:137` · `wa_faden` `:159` · `wa_nachricht` `:165` · `gespraech` `:180` · `nachricht` `:183` · `app_schluessel` `:188` · `anlagegut` `:202` · `einladung` `:212`.

Accessors: `db_einstellungen(un)` `:236`, `db_einstellung_setzen(un, k, v)` `:240`, `EINSTELLUNG_SCHLUESSEL` allowlist `:2610` (includes `kanzlei_name`, `betrieb_name`).

**Inconsistency to flag:** the routes `GET/POST /api/einstellungen` (`:2741`, `:2749`) use raw `un`, but `kontenrahmen_von(un)` `:2810`, `_kontenrahmen_auskunft` `:2816`, `umsatz_profil` callers (`:3345`, `:6059`, `:9121`) and anything financial use `db_einstellungen(salon_von(un))`. So a `mitarbeit` account writes settings under its own `un` that the calculation layer never reads. `db_einstellungen(un)` appears 17× directly. Same split in `anlagegut` (`salon_von` at `:2988, 3051, 3077, 3119, 3137`) vs `team` (`:8598` uses raw `un`) vs `termin`/`kundin` (`salon_von` at `:6465, 6507, 7692, …`).

`umsatz_profil(einstellungen)` lives in `server/belegreview/monatsabschluss.py:71` — pure function over a settings dict, no tenant awareness needed.

⚠️ **`kanzlei` gets the box but not the Mandant's SQLite data.** Since `salon_von("kanzlei@x.de")` returns the kanzlei's own email, a tax advisor sees the salon's Belege/Dokumente/Kassenbuch (git) but their **own** empty Team, Kundinnen, Termine, Anlagegüter, Einstellungen, Kontenrahmen. `kontenrahmen_von(un)` at `:2810` for a kanzlei user returns the *kanzlei's* Kontenrahmen, and `/api/export` (`:3330`) is called by exactly that user — worth checking whether the exported EXTF uses the right frame.

---

## 6. Portal frontend

`server/belegreview/portal.html` (5292 lines, single file, hash routing).

- Role state: global `meineRolle`, set in `ladeEinstellungen()` `portal.html:3355` from `/api/ich`, and again in the account-menu handler `:3410-3417`.
- Menu item: `<button id="menu-verwaltung" hidden …>Zugänge verwalten</button>` at `:923-924`; unhidden at `:3416`. Second entry point `#verwaltung-knopf` at `:1157`, unhidden at `:3357`.
- View markup: `<section class="ansicht" id="a-verwaltung">` at `:1397-1403` — a heading "Zugänge" and an empty `#verwaltung-inhalt` div.
- JS: `ladeVerwaltung()` `:4970-5040` (registered in the view-loader map at `:1604`), `startpasswortKarte()` `:5041`, `anfrageEinrichten()` `:5047`, `nutzerAktion()` `:5064`, `nutzerAnlegen()` `:5079`. The role `<select>` offering `salon | kanzlei | admin` is at `:5015-5016` and `:5032`.
- Kanzlei-only UI: DATEV block `:2075`; `Meine Kanzlei` settings field `#einst-kanzlei` `:1180`, saved as `kanzlei_name` `:3382`; Kanzleiwechsel letter `:3704-3750` → `POST /api/kanzleiwechsel` (`babu_web.py:9033`).
- **No-box state:** `<section id="a-gesperrt">` at `portal.html:934-948` — literally *"legen wir für deinen Salon noch eine eigene Belegbox an — das machen wir von Hand"* with a mailto to hallo@0711.io.

**How boxes are created today (`insp-app` :7808)** — nowhere in this repo. The gateway is out of scope by policy:
- `HANDOVER.md:48-49` and `CLAUDE.md:32`: *"**Nie anfassen:** `insp-app` (Belegbox-Gateway :7808)"*
- `server/belegreview/README.md:16`: *"`insp-app` | pm2 | Belegbox-Gateway :7808 — **nie anfassen**, ohne ihn kommt nichts in die Box"*
- `server/docker/compose.yml:5, 33`: the container mounts `~/inspektor-store` **read-only**; all writes go through :7808.
- `babu_web.py:485-488` (`nutzer_anlegen` docstring): *"`box=False` ist der Selbstregistrierungs-Weg: das Konto steht, die Belegbox richten wir von Hand ein"*.
- `README.md:57-70` (belegreview): manual unlock is `POST /api/nutzer-aktion {"aktion":"box_freigeben"}` **or** `sqlite3 ~/babu-web/portal.db "UPDATE nutzer SET box=1 WHERE email='…';"`. That flag flips access **to the one existing box** — it does not create anything.

So: creating a new Mandant box = a human runs something against insp-app to create `ws-<name>/<repo>.git`, then flips `nutzer.box`. There is no API, no naming convention in code beyond the `ws-christoph0711.io` literal, and no provisioning record.

---

## 7. Existing notion of multiple Mandanten

Essentially none in running code:
- `mandant` only exists as the **DATEV EXTF header field**: `server/belegreview/extf.py:340, 369`; `babu_web.py:3353` `mandant=os.environ.get("BABU_MANDANT", extf.MANDANT)`; `server/belegreview/historie.py:102`; `kanzleiwechsel.py:101, 116-117` (`mandantennummer` on the letter); `portal.html:3713, 3749`.
- `salons` (plural): no hits. `salon` is a free-text label column and a role name.
- `ws-`: only the two hardcoded literals — `babu_web.py:41` (STORE) and `boxschreiber.py:25` / `babu_web.py:1689, 1706` (REF).
- Multi-tenancy exists only as **aspiration in docs**: `docs/build-plan.md:31` ("v1.x … Steuerberater-Portal mit Multi-Mandanten-Queue"), `:48` ("Mandanten-Scoping"), `:99` ("Alle Tabellen mandantenscoped; Row-Level-Security"), `:255`, `:274`, `:327`.
- And explicitly **ruled out** in `docs/superpowers/specs/2026-08-26-nina-meldeschleife-design.md:122`: *"Keine Mandantenfähigkeit — eine Belegbox, eine Nina (siehe Memory babu-eine-belegbox)"*, plus `docs/superpowers/specs/2026-08-13-salon-portal.md:89` ("eine Datei + scp schlägt jede Toolchain bis zur Multi-Mandanten-Phase").
- `server/belegreview/tests/test_zugriff.py:1-6` is the canonical statement of the current model.

---

## Single-tenant assumptions — the checklist

**A. Identity / session**
1. Session cookie carries only `{un, exp}` — no box claim, no "acting as Mandant X" (`babu_web.py:367`).
2. `box_mitglied(un)` returns a bool, not a box id (`:510`). There is no `box_von(un)`.
3. `POST /api/anmelden` gates on the env allowlist `ERLAUBT` only (`:1168`).
4. `zugelassen()` / `_api_wache` treat "active account" as global authorization (`:490, 1126`).
5. `rolle()` falls back to `"kanzlei"` when `BABU_ROLLEN` is unset (`:3153`) — fail-open.
6. `nutzer.salon` is a display string; the real hierarchy key is `gehoert_zu`, one level deep only (`:3156`) — no kanzlei→Mandant edge exists.
7. No table anywhere models "which advisor serves which client". `kanzlei` = serves *the* box.

**B. Storage / git**
8. `STORE` is a module constant used by `_git`, `git_show`, `_blobs_lesen`, `review_pfad` (`:527, 540, 568, 575`).
9. `boxschreiber.KLON`, `REMOTE`, `REF`, `PAT_PFAD`, `_SCHLOSS` are module constants (`boxschreiber.py:23-38`).
10. `BABU_REF` string literal returned to the iOS app (`babu_web.py:1689, 1706`).
11. One global push lock serializes all writes (`boxschreiber.py:38`).
12. Container mounts `~/inspektor-store` read-only and one PAT file (`server/docker/compose.yml:33-34`).

**C. Caches / concurrency**
13. `_INDEX` + `_INDEX_LOCK` + `INDEX_TTL` — one index, one HEAD, one oid_cache (`:555-563, 721, 1014`).
14. ~20 unconditional `_INDEX["geprueft"] = 0.0` invalidations.
15. `_BLOB_STAND` `:5727`, `_SEITEN_CACHE` `:5755`, `_BELEG_VEKTOREN` `:2139`, `_MELDUNGEN_CACHE` `:5150` — all single-box.
16. Global locks/semaphores: `_RECHNUNG_SCHLOSS` `:560`, `_TERMIN_SCHLOSS` `:562`, `_WA_SCHLOSS` `:7205`, `_NACHTRAG_LOCK` `:5055`, `_ABSCHLUSS_LOCK` `:4066`, `_LLM_SEMAPHORE = Semaphore(1)` `:4202`, `_DB_LOCK` `:53`.
17. `_ABSCHLUSS_JOBS` `:4065`, shared temp dirs `ABSCHLUSS_TMP` `:4062` / `AUSWERTUNG_TMP` `:4635`.

**D. Data model**
18. Every portal table is scoped by a bare `un TEXT` column, no tenant FK, no index on tenant (`:56-217`).
19. `abschluss_status` has PK `un` — one closing per user, no year dimension in the key (`:73`).
20. `db_einstellungen(un)` vs `db_einstellungen(salon_von(un))` used inconsistently (17 raw call sites).
21. `kontenrahmen_von(un)` `:2810` resolves to the caller's own salon — wrong for a kanzlei exporting a Mandant's DATEV stack (`:3330`).
22. `BABU_MANDANT` / `extf.BERATER` are single env values for the whole server (`:3353`, `extf.py:340`).

**E. Verwaltung / kanzlei surface**
23. `GET /api/nutzer` `:3193` returns **all** accounts globally — names, e-mails, salon, last login, package. No scoping to "my Mandanten".
24. `POST /api/nutzer-aktion` `:3231` acts on any e-mail: role change, deactivate, `box_freigeben`, and `passwort_neu` `:3266` returning the plaintext start password. No audit log.
25. `POST /api/registrierung-einrichten` `:3275` and `GET /api/registrierungen` `:2714` are likewise global.
26. `box_freigeben` `:3260` only sets a boolean; it cannot provision or point at a box.
27. Provisioning is out-of-band through insp-app :7808, undocumented in this repo, marked "nie anfassen" (`README.md:16`, `HANDOVER.md:48`, `CLAUDE.md:32`), and the user-facing story is a mailto (`portal.html:940-945`).
28. `POST /api/team-zugang` `:8657` is the only invite path and creates only `mitarbeit` under the caller's own `un`.
29. `/api/export` `:3330` and `/api/korrektur/{stamm}` `:2462` combine `_box_wache` + `darf_verwalten` — correct today, but both operate on "the" box with no Mandant parameter.

**F. Frontend**
30. `meineRolle` is a single global; there is no Mandant selector, no "currently viewing" state (`portal.html:3355, 3410`).
31. `ladeVerwaltung()` `:4970` renders a flat list of all accounts — no pagination, no search, no grouping. Unusable at hundreds of rows.
32. Role `<select>` at `:5015` hardcodes `salon|kanzlei|admin` (omits `mitarbeit`, which the server accepts at `:3255`).