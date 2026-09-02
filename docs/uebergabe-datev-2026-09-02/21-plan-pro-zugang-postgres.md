<!-- Planungsagent (Sonnet), 02.09.2026, Stand d163ac6 -->

# Implementierungsplan: Pro-Zugang für Kanzleien mit hunderten Mandanten (Postgres + Docker)

Alle Zeilenangaben beziehen sich auf `server/belegreview/babu_web.py` (Commit `d163ac6`, gegen den aktuellen Stand stichprobenartig verifiziert) bzw. `server/belegreview/boxschreiber.py`, sofern nicht anders angegeben.

## 0. Vorab-Entscheidungen (mit Empfehlung, aber vom Nutzer zu bestätigen)

| # | Frage | Empfehlung |
|---|---|---|
| D1 | Postgres für **alle** 18 Portal-Tabellen oder Hybrid (Postgres nur Mandantenverwaltung/Auth/Audit, SQLite bleibt je Mandant)? | **Voll migrieren.** Begründung unten (Abschnitt 1). Hybrid würde N SQLite-Dateien erzeugen — genau die Skalierungsgrenze, die der Auftrag beheben soll, plus zwei Konsistenzmodelle parallel. |
| D2 | Postgres im selben Compose-Netz mit `network_mode: host` für babu-web, oder eigenes Compose-Netzwerk? | **Eigenes Docker-Netzwerk `babu-net` für babu-web↔postgres, `network_mode: host` für babu-web bleibt zusätzlich bestehen** (Compose erlaubt beides: ein Service kann `network_mode: host` haben und trotzdem per `127.0.0.1` auf einen Port eines zweiten Containers zugreifen, wenn der Postgres-Container seinen Port auf `127.0.0.1` published — siehe Abschnitt 2). Kein eigenes Bridge-Netz für babu-web nötig, das würde `insp-app`/vLLM-Erreichbarkeit über `127.0.0.1` aus dem Container brechen. |
| D3 | Tests laufen gegen echtes Postgres oder gegen SQLite-Fallback? | **DB-Zugriffsschicht unterstützt beide Dialekte** (siehe `db.py` unten); Tests laufen per Default gegen eine **lokale Wegwerf-Postgres-Instanz** (`docker run --rm -d -p 55432:5432 postgres:16`, per Fixture gestartet/geprüft), mit `pytest.mark.skipif`, falls kein Docker verfügbar ist, dann Fallback auf SQLite-Dialekt derselben Abstraktionsschicht. Grund: die Postgres-spezifischen Dinge (Fremdschlüssel, `SELECT … FOR UPDATE`, Enum-Typen) sollen vor dem Produktivgang mindestens einmal echt getestet werden. |
| D4 | Box-Provisionierung automatisieren? | **Nein — insp-app ist tabu.** `mandant.status = 'box_ausstehend'` bleibt ein manueller Schritt (Abschnitt 5). Bitte bestätigen, dass das für "hunderte Mandanten" akzeptabel ist (ggf. später ein eigenes, von insp-app getrenntes Onboarding-Tool — außerhalb dieses Auftrags). |
| D5 | `rolle()`-Fallback bei leerem `BABU_ROLLEN` von `"kanzlei"` auf `"salon"` ändern (`babu_web.py:3153`)? | **Ja, sofort und unabhängig vom Rest** (siehe Abschnitt 7) — fail-open auf die mächtigste Rolle ist ein Sicherheitsfehler, der durch die neue Kanzlei-Mandanten-Fläche gravierender wird. |

---

## 1. Datenmodell

### 1.1 Warum volle Migration statt Hybrid

- `_DB_LOCK` (`babu_web.py:53`) ist ein **einziger, prozessweiter Mutex für jeden SQLite-Schreibzugriff** — nicht nur pro Mandant. Bei hunderten Mandanten mit gleichzeitigen Kanzlei-Sitzungen wird das zum seriellen Flaschenhals, unabhängig davon, ob man 1 oder N SQLite-Dateien hätte (die Kanzlei-Ansicht selbst — Warteschlange über alle Mandanten — bräuchte ohnehin plattformweite Aggregation, die über N SQLite-Dateien nur mit eigenem Fan-out-Code ginge).
- Referentielle Integrität (Mandant → Kanzlei-Mitgliedschaft → Nutzer → Audit-Log) lässt sich in SQLite nur disziplinarisch, in Postgres deklarativ mit `FOREIGN KEY` durchsetzen — genau das, was die Mandantentrennung robust macht.
- Blast Radius ist überschaubar: **alle** SQL-Zugriffe laufen durch **eine** Funktion `_db()` (`babu_web.py:56`) und **111** `c.execute(...)`-Aufrufe, davon **86×** im Muster `with _DB_LOCK, _db() as c:`. Es gibt keine zweite Datei, die SQLite direkt anfasst. Das ist ein einzelner, geschlossener Änderungsradius.
- Dialektunterschiede sind klein und geprüft:
  - Platzhalter: SQLite `?` vs. Postgres `%s` — **355** `?`-Vorkommen, aber **keine** SQL-Zeichenkette enthält einen literalen `%` oder ein wildcard-`?` außerhalb eines Platzhalters (geprüft per `grep`), eine simple `?`→`%s`-Übersetzung in der Abstraktionsschicht ist sicher.
  - `INSERT OR REPLACE` — nur **3×**, wird zu `INSERT … ON CONFLICT (...) DO UPDATE SET …`.
  - `AUTOINCREMENT`/`INTEGER PRIMARY KEY` — **13×**, wird zu `GENERATED ALWAYS AS IDENTITY` bzw. `SERIAL`.
  - `PRAGMA` — **0 Treffer**, kein Migrationsaufwand.
  - `sqlite3.Row`/dynamische Spaltenlisten (f-string UPDATE) — **2× row_factory**, **2× f-string UPDATE** (`:6910`, `:7276`) — beide bauen nur Spaltennamen aus einer festen Allowlist zusammen, keine Nutzereingabe im SQL-Text; unverändert portierbar.
- `CREATE TABLE IF NOT EXISTS` bei jedem `_db()`-Aufruf ist in Postgres genauso gültig (idempotent), bleibt für Dev/Test so; für den produktiven Postgres kommt zusätzlich ein Alembic-artiges, aber schlankes **`migrations/`-Verzeichnis mit nummerierten SQL-Dateien** dazu (kein neues Framework nötig — bei diesem Umfang genügt ein `db.py`-Runner, der `schema_version` in einer Tabelle führt).

### 1.2 Neue Mandanten-/Kanzlei-Tabellen (Postgres)

Neue Datei `server/belegreview/mandanten.py` kapselt Schema + Zugriffe, analog zu `einladung.py`.

```sql
CREATE TABLE kanzlei (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name          TEXT NOT NULL,
  inhaber_un    TEXT NOT NULL REFERENCES nutzer(email),  -- der "kanzlei"-Account, der die Kanzlei anlegt
  angelegt      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mandant (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  kanzlei_id    BIGINT NOT NULL REFERENCES kanzlei(id),
  name          TEXT NOT NULL,               -- Anzeigename, ex "nutzer.salon"
  besitzer_un   TEXT NOT NULL REFERENCES nutzer(email),  -- der Salon-Account, dem die Box gehört
  box_ref       TEXT,                        -- z.B. "inspektor/ws-<mandant>/babu" — NULL solange box_ausstehend
  kontenrahmen  TEXT,                        -- SKR03/SKR04, überschreibt Default falls gesetzt
  berater_nr    TEXT,
  mandant_nr    TEXT,
  status        TEXT NOT NULL DEFAULT 'box_ausstehend'
                  CHECK (status IN ('box_ausstehend','aktiv','pausiert','beendet')),
  angelegt      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (kanzlei_id, besitzer_un)
);
CREATE INDEX mandant_kanzlei ON mandant (kanzlei_id, status);

CREATE TABLE kanzlei_mitglied (          -- welche kanzlei-Nutzer (Sachbearbeiter) dürfen für diese Kanzlei arbeiten
  kanzlei_id    BIGINT NOT NULL REFERENCES kanzlei(id),
  un            TEXT NOT NULL REFERENCES nutzer(email),
  rolle         TEXT NOT NULL DEFAULT 'sachbearbeiter' CHECK (rolle IN ('inhaber','sachbearbeiter')),
  angelegt      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (kanzlei_id, un)
);

ALTER TABLE nutzer ADD COLUMN mandant_id BIGINT REFERENCES mandant(id);
-- gesetzt für Team-Mitglieder EINES Mandanten (ersetzt/ergänzt gehoert_zu perspektivisch,
-- gehoert_zu bleibt für Rückwärtskompatibilität bestehen und wird NICHT entfernt)

CREATE TABLE audit_log (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  zeit          TIMESTAMPTZ NOT NULL DEFAULT now(),
  akteur_un     TEXT NOT NULL,
  kanzlei_id    BIGINT REFERENCES kanzlei(id),
  mandant_id    BIGINT REFERENCES mandant(id),
  aktion        TEXT NOT NULL,           -- "rolle_geaendert","passwort_reset_angefordert","export","box_freigeben",…
  ziel_un       TEXT,
  details       JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX audit_log_kanzlei ON audit_log (kanzlei_id, zeit DESC);
```

**Bewusst nicht** in `mandant` abgebildet: die 17 sqlite-Tabellen bleiben mandantenneutral (weiter `un`-Spalte) — `mandant_id` ist zunächst nur ein Auflösungs-Schlüssel für "welche Box/welcher Kontenrahmen", nicht eine zweite Fremdschlüsselkaskade durch alle Tabellen (kein "Row-Level-Security jetzt überall", das wäre ein eigener, größerer Auftrag; hier reicht Auflösung über `salon_von`/`box_von`, siehe Abschnitt 3/4).

### 1.3 DB-Zugriffsschicht `server/belegreview/db.py` (neu)

```python
DIALEKT = "postgres" if BABU_DB_URL else "sqlite"   # BABU_DB_URL z.B. postgresql://…

def verbindung():
    if DIALEKT == "postgres":
        return psycopg.connect(BABU_DB_URL, row_factory=dict_row)  # psycopg3
    return sqlite3.connect(PORTAL_DB)

def platzhalter(sql: str) -> str:
    return sql.replace("?", "%s") if DIALEKT == "postgres" else sql

def upsert(tabelle, spalten, konflikt_spalten):
    # baut je Dialekt "INSERT OR REPLACE" bzw. "INSERT … ON CONFLICT … DO UPDATE"
```

`_db()` in `babu_web.py:56` wird zu einem dünnen Wrapper, der `db.verbindung()` liefert und beim Erststart die `CREATE TABLE`-Statements über den Migrations-Runner laufen lässt statt sie inline auszuführen (siehe 1.4). Alle 111 `c.execute(...)`-Aufrufe bleiben **textuell fast unverändert** — sie laufen weiterhin durch dieselbe `_db()`-Stelle, nur dass `_db()` jetzt `db.platzhalter(sql)` anwendet, bevor `execute` läuft (ein zentraler Interceptor, kein Editieren an 111 Stellen). Die 3 `INSERT OR REPLACE`-Stellen und die 2 `sqlite3.Row`-Stellen (`:2927`, `:3079`) werden explizit umgeschrieben (dict-artiger Row-Zugriff funktioniert mit `dict_row` aus psycopg3 gleich).

### 1.4 Migrationsschema-Runner

Neues Verzeichnis `server/belegreview/migrations/0001_initial.sql` … — reine SQL-Dateien, ein `schema_version`-Table, angewendet beim Start von `db.py`. Kein neues Framework (Alembic wäre für 20 Tabellen Overkill und eine neue Abhängigkeit, die das gepinnte `requirements.txt`-Ritual sprengt).

### 1.5 Migrationsskript SQLite → Postgres

Neues Skript `server/belegreview/werkzeuge/migrate_sqlite_to_pg.py` (nur unter `werkzeuge/`, kein Server-Code):
- Liest `~/babu-web/portal.db` Tabelle für Tabelle, schreibt in Postgres in derselben Reihenfolge wie die FK-Abhängigkeiten (`nutzer` zuerst, dann alles mit `un`-Spalte).
- **Idempotent**: `TRUNCATE … CASCADE` vor jedem Lauf, dann Vollimport — kein inkrementelles Diffing nötig, da Migrationsfenster kurz (Wartungsfenster, siehe Rollout).
- Erzeugt danach für jeden bestehenden Salon-Account mit `box=1` und `rolle in (kanzlei,admin)` **keine** automatischen `kanzlei`/`mandant`-Zeilen — das ist ein bewusster manueller Schritt (Abschnitt 5), sonst würde die Migration altes 1-Box-Modell heimlich in ein Mandantenmodell pressen ohne Kontenrahmen/Berater-Nr., die eine Kanzlei tatsächlich braucht.
- Läuft **einmal**, dokumentiert im Deploy-Ritual (Abschnitt 9), nicht bei jedem Container-Start.

---

## 2. Docker / Compose

### 2.1 `server/docker/compose.yml` — Diff (konzeptionell)

```yaml
services:
  postgres:
    image: postgres:16
    container_name: babu-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: babu
      POSTGRES_USER: babu
      POSTGRES_PASSWORD_FILE: /run/secrets/babu_pg_passwort   # oder ENV aus gemounteter Datei, kein Klartext im compose.yml
    volumes:
      - babu-pg-daten:/var/lib/postgresql/data
      - ./postgres/init:/docker-entrypoint-initdb.d:ro   # optional: Erstanlage der Rolle
    ports:
      - "127.0.0.1:55432:5432"     # NUR localhost — babu-web (host network) erreicht es über 127.0.0.1
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U babu -d babu"]
      interval: 5s
      timeout: 3s
      retries: 10

  babu-web:
    # unverändert: network_mode: host, User 1001:1000, bestehende Volumes
    environment:
      BABU_DB_URL: "postgresql://babu:${BABU_PG_PASSWORT}@127.0.0.1:55432/babu"
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  babu-pg-daten:
```

Begründung `network_mode: host` **bleibt** für babu-web: der Container erreicht heute `insp-app :7808` und vLLM/Gemma `:11435` über `127.0.0.1` auf dem Host — das darf laut CLAUDE.md/HANDOVER.md nicht angefasst werden. Ein eigenes Bridge-Netz für babu-web würde diese Erreichbarkeit brechen oder zusätzliche Netzwerk-Aliasse/Port-Mappings für Host-Dienste erfordern, die nicht in diesem Auftrag liegen. Postgres bekommt stattdessen einen **auf `127.0.0.1` gebundenen Port** und ist damit aus dem `host`-Netz von babu-web genauso erreichbar wie jeder andere Host-Dienst — ohne dass Postgres selbst `network_mode: host` braucht (Postgres lauscht intern auf `0.0.0.0:5432`, published wird nur auf `127.0.0.1:55432`).

### 2.2 Secrets

Passwort **nicht** im Klartext in `compose.yml` (Sicherheitsregel: nie Passwörter/Token entgegennehmen/ausgeben). Empfehlung: `~/babu-web/.pg_passwort` (0600, wie `.session_geheimnis`) wird gemountet und beim ersten Start gelesen; Docker-Secrets (`secrets:`-Block) sind die sauberere Variante, wenn Compose-Version das unterstützt — als offene technische Detailentscheidung markieren, funktional äquivalent.

### 2.3 Backups

- `pg_dump` als Cron **auf dem Host** (H200V), analog zum bestehenden `~/babu-sichern.sh` (tägliches Belegbox-Spiegeln, `HANDOVER.md` Abschnitt 6.4): neuer Cron-Eintrag `pg_dump -Fc babu > ~/backups/babu-pg-$(date +%F).dump`, Aufbewahrung z.B. 14 Tage rollierend. Kein Backup-Container — ein zusätzlicher Dienst nur für Cron ist unnötige Komplexität, der Host hat bereits ein Cron-Ritual für die Box-Sicherung.
- Ergänzt (nicht ersetzt) das bestehende Box-Backup — Postgres und Belegbox sind getrennte Sicherungsziele.

### 2.4 Tests ohne Postgres in CI

- `db.py` bleibt dialektfähig (Abschnitt 1.3). Test-Fixture `pg_verfuegbar()` versucht, eine Wegwerf-Postgres-Instanz zu erreichen (`BABU_TEST_DB_URL`, sonst `docker run --rm -d -p 55432:5432 postgres:16` falls Docker lokal verfügbar ist), sonst `pytest.skip` für Postgres-spezifische Tests und Fallback auf SQLite-Dialekt für die bestehenden 1608 Tests — **die bestehende Suite darf nicht neu Docker voraussetzen**, das würde CLAUDE.md's `Bauen & Testen`-Rezept brechen.
- Neuer Marker `@pytest.mark.pg` für Tests, die echtes Postgres brauchen (FK-Verletzungen, `ON CONFLICT`, Enum-Constraints).

### 2.5 `requirements.txt`

Ergänzen: `psycopg[binary]==3.2.x` (gepinnt wie die anderen Einträge), Kommentarzeile mit Datum/Grund wie beim bestehenden Header.

---

## 3. Box-Kontext (`Box`-Objekt statt Modulkonstanten)

### 3.1 Neue Datei `server/belegreview/box.py`

```python
@dataclass(frozen=True)
class Box:
    mandant_id: int | None      # None = Alt-Modus / Einzelbetrieb-Kompatibilität
    store: Path                 # ersetzt STORE
    ref: str                    # ersetzt BABU_REF-Literal
    klon: Path                  # ersetzt boxschreiber.KLON
    schloss: threading.Lock     # ersetzt boxschreiber._SCHLOSS (Registry, siehe unten)

_BOX_REGISTRY: dict[int | None, Box] = {}
_BOX_REGISTRY_LOCK = threading.Lock()

def box_von(un: str, mandant_id: int | None = None) -> Box:
    """Löst Box anhand un + optional aktivem Mandanten (acting-as) auf.
    Fällt ohne mandant_id auf salon_von(un)/bestehendes 1-Box-Verhalten
    zurück — Alt-Verhalten für Owner bleibt bit-identisch."""
```

- Pro Box: eigener Eintrag in `_BOX_REGISTRY` mit **eigenem** `_INDEX`-Dict, `_INDEX_LOCK`, `_BELEG_VEKTOREN`, `_BLOB_STAND`, `_SEITEN_CACHE`, `_RECHNUNG_SCHLOSS`, `_TERMIN_SCHLOSS`. LRU-Begrenzung (z.B. 50 aktive Boxen im Speicher, TTL-Verdrängung) verhindert unbegrenztes Wachstum bei hunderten Mandanten, von denen nur wenige gleichzeitig aktiv sind.
- `boxschreiber.py` bekommt eine Parametrisierung: `KLON`, `REMOTE`, `REF`, `_SCHLOSS` werden Felder von `Box` statt Modulkonstanten; `schreiben()`/`loeschen()` nehmen `box: Box` als erstes Argument. `PAT_PFAD` bleibt **ein** Service-PAT (Autorisierung pro Ref regelt der Gateway, das ist insp-app-Innenleben — tabu).

### 3.2 Request-scoped Kontext statt 104 Routen anfassen

`_box_wache` (`babu_web.py:1141`) wird erweitert:

```python
_AKTIVE_BOX: contextvars.ContextVar[Box] = contextvars.ContextVar("aktive_box")

def _box_wache(request):
    un, fehler = _api_wache(request)
    if fehler: return None, fehler
    mandant_id = _mandant_aus_kontext(request, un)   # Header X-Mandant oder Cookie-Claim, s. Abschnitt 4
    if not box_mitglied(un, mandant_id):
        return None, JSONResponse({"fehler": BOX_GESPERRT}, status_code=403)
    _AKTIVE_BOX.set(box_von(un, mandant_id))
    return un, None
```

Alle 104 Routen, die heute `un, fehler = _box_wache(request)` aufrufen und danach `index_aktuell()`, `_git(...)`, `boxschreiber.schreiben(...)` ohne Box-Parameter nutzen, **bleiben unverändert im Aufruf** — die betroffenen Funktionen lesen die aktive Box intern:

```python
def index_aktuell() -> dict:
    return _index_aktuell_fuer(_AKTIVE_BOX.get())

def _git(args, timeout=30):
    return _git_fuer(_AKTIVE_BOX.get(), args, timeout)
```

**Funktionen, die intern umgestellt werden (Signatur bleibt außen gleich, Body liest contextvar):**
| Funktion | Zeile | Änderung |
|---|---|---|
| `_git` | `:568` | `-C str(STORE)` → `-C str(_AKTIVE_BOX.get().store)` |
| `git_show` | `:527` | dito |
| `_blobs_lesen` | `:575` | dito |
| `review_pfad` | `:540` | dito |
| `_index_bauen`/`index_aktuell` | `:721`/`:1014` | Registry-Lookup statt Modul-`_INDEX` |
| `boxschreiber.schreiben`/`loeschen` | `:113`/`:135` | erstes Argument `box: Box` (hier **muss** die Signatur sich ändern, da `boxschreiber.py` ein eigenes Modul ohne Zugriff auf `babu_web`s contextvar ist — die ~72 Aufrufstellen in `babu_web.py` bekommen `_AKTIVE_BOX.get()` als erstes Argument ergänzt) |
| `_beleg_vektoren`/semantische Suche | `:2139` | Registry-Lookup je Box |
| `historie_lesen` (`historie.py`) | — | bekommt `store: Path`-Parameter statt eigenen Import von `STORE` |
| `_INDEX["geprueft"]=0.0`-Invalidierungen (29 Stellen) | diverse | werden zu `_AKTIVE_BOX.get().invalidieren()` — ein Wrapper, kein manuelles Suchen-Ersetzen an 29 Stellen mit Fehlerrisiko |

Dieser Ansatz ist der zentrale Hebel, um die 104-Routen-Fläche **nicht** einzeln anfassen zu müssen — nur die ~10 tiefliegenden Funktionen ändern sich, alle Routen bleiben textgleich.

### 3.3 Alt-Verhalten für Owner bleibt bit-identisch

Für den bestehenden Einzelbetrieb (Nina, `christoph0711.io`) muss `box_von(un, mandant_id=None)` exakt denselben `STORE`/`REF`/`KLON` liefern wie heute — sonst bricht der Golden-Diff im Deploy-Ritual. Deshalb: Default-Box-Eintrag in der Registry wird **aus den bestehenden Env-Variablen** (`BABU_STORE`, `BABU_REF`, `BABU_BOX_KLON`) initialisiert, nicht aus der neuen `mandant`-Tabelle — die neue Tabelle kommt nur für **zusätzliche** Mandanten zum Tragen.

---

## 4. Acting-as (Kanzlei arbeitet "als" ein Mandant)

### 4.1 Session/Header

- **Kein neuer Cookie-Claim** (würde Session-Signatur-Format ändern, Migrationsrisiko für alle bestehenden Sessions). Stattdessen: **`X-Mandant: <mandant_id>`-Header**, geprüft in `_box_wache` gegen `kanzlei_mitglied`/`mandant.kanzlei_id`-Mitgliedschaft. Vorteil: zustandslos, kein Cookie-Redesign, Frontend kann pro `fetch()` den Header setzen (der aktuell gewählte Mandant lebt im Portal-JS-State, wie heute `meineRolle`).
- `_mandant_aus_kontext(request, un)`: liest Header, prüft `SELECT 1 FROM kanzlei_mitglied km JOIN mandant m ON m.kanzlei_id=km.kanzlei_id WHERE km.un=? AND m.id=?`; fehlt der Header oder ist `un` kein Kanzlei-Nutzer, bleibt `mandant_id=None` (Alt-Verhalten, eigene Box).
- `box_mitglied(un, mandant_id)` (`babu_web.py:510`) wird erweitert: wenn `mandant_id` gesetzt ist, prüft sie die Kanzlei-Mitgliedschaft statt der heutigen pauschalen `rolle in (admin, kanzlei) → True`-Regel (**das schließt die im Erkundungsdokument benannte Lücke**, dass jede Kanzlei-Rolle jede Box sieht).

### 4.2 `salon_von` beim Acting-as

`salon_von(un)` (`:3156`) bekommt eine kontextabhängige Variante:

```python
def salon_von_aktiv(un: str) -> str:
    box = _AKTIVE_BOX.get(None)
    if box and box.mandant_id:
        return mandant_besitzer_un(box.mandant_id)   # der Mandant, nicht die Kanzlei
    return salon_von(un)   # Alt-Verhalten
```

Alle **60** Aufrufstellen von `salon_von(un)` werden auf `salon_von_aktiv(un)` umgestellt (mechanisches, aber notwendiges Refactoring — sonst sieht eine Kanzlei beim Acting-as weiterhin ihre **eigenen** leeren Team/Kundinnen/Einstellungen statt die des Mandanten, exakt der im Erkundungsdokument benannte Fehler unter Abschnitt 5 "kanzlei bekommt die Box, aber nicht die SQLite-Daten des Mandanten").

### 4.3 Normalisierung `db_einstellungen(un)` vs. `db_einstellungen(salon_von(un))`

17 rohe `db_einstellungen(un)`-Aufrufstellen (Zeilen `2730, 3207, 4331, 4393, 4442, 4976, 4999, 5019, 6806, 6932, 6964, 7230, 7377, 7450, 7536, 8471, 8691, 8805`) werden geprüft und, wo sie **finanzielle/betriebliche** Werte lesen (Kontenrahmen, Umsatzprofil, Öffnungszeiten, Marke, Abschluss-Art), auf `db_einstellungen(salon_von_aktiv(un))` umgestellt. Ausnahmen bleiben bewusst roh (z.B. persönliche UI-Einstellungen eines Mitarbeitenden, falls vorhanden) — jede Zeile wird einzeln kommentiert, warum sie roh bleibt, nach demselben Dokumentationsstil wie der Rest der Datei.

### 4.4 `kontenrahmen_von`/Export mit Mandanten-Stammdaten

`kontenrahmen_von` (`:2810`) und `BABU_MANDANT`/`extf.BERATER` (`:3353`) werden beim Export (`GET /api/export/{monat}.csv`, `:3330`) durch die `mandant`-Zeile ersetzt, wenn eine aktive Box mit `mandant_id` vorliegt: `berater_nr`, `mandant_nr`, `kontenrahmen` kommen dann aus der Tabelle statt aus Env-Variablen — das ist zugleich die Antwort auf die Anforderung "Export mit dem Kontenrahmen und Berater-/Mandant-Nummern des Mandanten".

---

## 5. Provisionierung (bewusst manuell)

- `mandant.status = 'box_ausstehend'` ist der Normalzustand nach Anlage durch die Kanzlei.
- Neue Route `POST /api/kanzlei/mandanten` (Kanzlei legt einen Mandanten an: Name, E-Mail des Salons) erzeugt `mandant`-Zeile mit `box_ref = NULL`, verschickt eine Einladung nach dem **bestehenden Muster aus `einladung.py`** (Link, kein Klartext-Passwort) an die Salon-Adresse.
- Solange `box_ref IS NULL`, zeigt die Kanzlei-Ansicht "Belegbox wird eingerichtet" statt der Mandanten-Detailansicht — Portal-Text analog zu `a-gesperrt` (`portal.html:934-948`), aber ohne den Mailto-Umweg: der Kanzlei-Sachbearbeiter sieht stattdessen intern, welche Mandanten offen sind ("N Mandanten warten auf Box-Einrichtung").
- Der Mensch, der die Box tatsächlich über insp-app anlegt, trägt danach `box_ref` und setzt `status='aktiv'` — über eine einfache Verwaltungsroute (nicht insp-app selbst), z.B. `POST /api/kanzlei/mandanten/{id}/box-verknuepfen {box_ref}`, geschützt durch `admin`-Rolle, nicht durch jede Kanzlei.
- **Diese Grenze ist eine Entscheidung, die der Nutzer bestätigen muss** (D4 oben): kein API-Weg in diesem Auftrag automatisiert das Anlegen im Gateway.

---

## 6. Frontend (`portal.html`)

Neue Ansicht `a-mandanten` (Kanzlei-Rolle), analog zur bestehenden View-Struktur (`ladeVerwaltung`-Muster, `portal.html:4970`):

- **Tabelle** mit Suche (Name/Nr.), Pagination (nicht die heutige `ladeVerwaltung`-Flachliste, die bei hunderten Zeilen unbrauchbar ist — vgl. Erkundungspunkt 31), Status-Chips (`box_ausstehend`/`aktiv`/`pausiert`), Spalte "offene Rückfragen".
- **Mandant-Switcher** im Header: Chip "Mandant: Salon X · wechseln" — setzt den `X-Mandant`-Header für alle folgenden `fetch()`-Aufrufe (zentrale JS-Variable `aktiverMandant`, analog zu `meineRolle` (`:3355`)); "wechseln" öffnet die Mandantenliste erneut.
- **Arbeits-Warteschlange** (neue Ansicht oder Tab in `a-mandanten`): aggregiert über alle Mandanten einer Kanzlei — offene Rückfragen, Monate ohne Freigabe, Export fällig; serverseitig eine neue Route `GET /api/kanzlei/warteschlange`, die pro Mandant kurz `index_aktuell()` der jeweiligen Box abfragt (mit Zeitbudget/Timeout, damit ein einzelner langsamer Mandant die Übersicht nicht blockiert).
- **Zugänge scoped**: `ladeVerwaltung()` (`:4970`) wird für Kanzlei-Rolle auf "meine Mandanten + deren Team" eingeschränkt (serverseitig, s. Abschnitt 7), nicht mehr global.
- iOS-App bleibt **unverändert** (nur Owner-Zugriff, kein Mandanten-Switch dort) — bestätigt in `HANDOVER.md` ("Die App bekommt KEINEN eigenen v13-Writer" u.ä., generelles Prinzip: Kanzlei-Funktionen sind Portal-only).

---

## 7. Sicherheit

- **Audit-Log**: jede Kanzlei-Aktion (`POST /api/nutzer-aktion`, `POST /api/kanzlei/mandanten*`, Export, Rollenänderung) schreibt eine Zeile nach `audit_log` — ein zentraler Helfer `audit(akteur_un, aktion, ziel_un=None, mandant_id=None, **details)`, aufgerufen an den bestehenden Verwaltungsrouten (`:3211, :3231, :3275`) und den neuen Kanzlei-Routen.
- **Kein Klartext-Passwort-Reset über Mandantengrenzen**: `passwort_neu` (`:3266`) wird für den Kanzlei-Fall (Ziel-Nutzer gehört zu einem fremden Mandanten) durch einen **Reset-Link** nach dem `einladung.py`-Muster ersetzt (Hash speichern, Link verschicken, einmalig einlösbar, 2 Wochen gültig wie das bestehende Muster) — der Aufrufer sieht das Passwort nie. Für den eigenen Betrieb (Owner setzt sein eigenes Team-Passwort zurück) kann das bestehende Verhalten bleiben, wird aber ebenfalls auditiert.
- **`GET /api/nutzer` / `POST /api/nutzer-aktion` scoping**: für `rolle=kanzlei` liefert `/api/nutzer` künftig nur Nutzer, deren `mandant_id` zu einer Kanzlei gehört, in der der Aufrufer Mitglied ist (`kanzlei_mitglied`-Join); für `rolle=admin` bleibt der globale Blick (Betreiber-Ebene). `_verwalter_wache` (`:3180`) wird um eine Variante `_kanzlei_wache` ergänzt, die zusätzlich die Mandanten-Zugehörigkeit prüft, statt pauschal `darf_verwalten`.
- **Rate Limits**: bestehendes Muster `_LOGIN_VERSUCHE` (`:1179`) wird auf die neuen Reset-Link-Anforderungen übertragen (analog zu `gebremst()` in `einladung.py:141`).
- **`rolle()`-Fallback fail-closed** (`:3153`): `"kanzlei" if not ROLLEN else "salon"` → **`"salon"` immer als Default**, unabhängig von `ROLLEN`. Prod setzt `BABU_ROLLEN` explizit (`compose.yml:24`), daher **kein Prod-Verhaltensunterschied** zu erwarten — muss aber im Golden-Diff verifiziert werden (Abschnitt 9). Diese Änderung sollte **vor** oder **mit** Phase 0 kommen, unabhängig vom Postgres-Umbau.
- Rollenauswahl im Frontend (`portal.html:5015`) ergänzt `mitarbeit` (Erkundungspunkt 32) — kleine, unabhängige Korrektur.

---

## 8. Phasierung

Reihenfolge nach **frühestem Nutzen + grüner Suite nach jeder Phase**. Postgres kommt **vor** dem Mehr-Box-Umbau, weil das Tenancy-Modell (Kanzlei/Mandant/Audit) ohnehin relationale Integrität braucht und die 111 bestehenden SQL-Stellen sonst zweimal angefasst würden (einmal für Postgres, einmal für neue Tabellen).

**Phase 0 — Sicherheits-Sofortmaßnahme (unabhängig, < 1 Tag)**
- `rolle()`-Fallback fail-closed (Abschnitt 7).
- Test: `rolle()` ohne `BABU_ROLLEN` liefert `"salon"`.

**Phase 1 — DB-Abstraktionsschicht + Postgres-Infrastruktur, Verhalten unverändert**
- `db.py`, `migrations/0001_initial.sql` (Abbild der 18 heutigen Tabellen, 1:1), `compose.yml`-Postgres-Service, Migrationsskript `migrate_sqlite_to_pg.py`.
- `_db()` wird zum Wrapper, alle Zeilen laufen unverändert weiter, nur der Ziel-Dialekt wechselt.
- Tests: komplette bestehende Suite (1608) grün gegen SQLite-Dialekt **und** gegen Postgres-Dialekt (neuer CI-Lauf/Marker); neue Tests für `db.upsert`/Platzhalter-Übersetzung.
- Deploy: Postgres-Container hochfahren, Migrationsskript einmal laufen lassen, `BABU_DB_URL` setzen, Golden-Diff.

**Phase 2 — Tenancy-Tabellen + Box-Kontext, weiter EINE Box aktiv**
- `mandant.py`, `box.py`, `_AKTIVE_BOX`-Contextvar, `boxschreiber.py`-Parametrisierung.
- Noch **keine** zweite echte Box im Betrieb — nur der Umbau, mit dem Default-Box-Eintrag aus den bestehenden Env-Variablen (Abschnitt 3.3).
- Tests: `welt`-Fixture (`tests/test_mehrseiten_buendel.py:28`) erweitern um eine **zweite** synthetische Box (`welt2`), prüfen, dass Schreiben/Lesen/Index sich nicht überschneiden; bestehende Tests bleiben unverändert grün (Beweis für Bit-Identität des Alt-Pfads).

**Phase 3 — Acting-as + Mandanten-Scoping der Verwaltung**
- `X-Mandant`-Header, `salon_von_aktiv`, Normalisierung der 17 `db_einstellungen(un)`-Stellen, `/api/nutzer`-Scoping, Audit-Log, Reset-Link statt Klartext.
- Tests: zwei Mandanten unter einer Kanzlei, Acting-as liest korrekt Mandant B, nicht Kanzlei-eigene Daten; Kanzlei A sieht nicht Mandant von Kanzlei B (Cross-Tenant-Test, direkt aus `test_zugriff.py`-Tradition).

**Phase 4 — Provisionierung + Frontend**
- `POST /api/kanzlei/mandanten`, Einladung, "Box wird eingerichtet"-Zustand, Mandanten-Tabelle + Switcher + Warteschlange in `portal.html`.
- Tests: Einladungsfluss (Hash, kein Klartext-Link in DB), Warteschlange aggregiert über 2+ Boxen mit Timeout-Verhalten bei einer "hängenden" Box.

**Phase 5 — Härtung/Rollout**
- Rate Limits auf neue Routen, Backup-Cron für Postgres, Lasttest mit synthetisch vielen Mandanten (z.B. 50 Boxen) gegen die LRU-Registry aus Abschnitt 3.1, Doku-Update (`HANDOVER.md`, `server/belegreview/README.md`).

---

## 9. Rollout / Deploy-Ritual / Rollback

- Golden-Diff-Ritual (`CLAUDE.md`) bleibt **exakt** wie beschrieben, zusätzlich **vor** Phase 1: Golden-Snapshot auch von `/api/nutzer` und `/api/ich` für den bestehenden Kanzlei-Testaccount, um zu beweisen, dass sich am bestehenden Ein-Betrieb-Verhalten nichts ändert.
- Reihenfolge je Deploy: Golden vorher → `rsync` → `docker compose build && docker compose up -d` (Postgres-Service kommt zuerst hoch, `depends_on: condition: service_healthy` sorgt dafür) → Migrationsskript **einmalig** von Hand ausführen (nicht Teil von `CMD`, damit es nicht bei jedem Container-Neustart erneut TRUNCATEt) → Golden nachher byte-diffen → geänderte Routen live durchrufen.
- **Rollback**: `BABU_DB_URL` env entfernen → `_db()` fällt auf SQLite/`portal.db` zurück (die Datei bleibt bis zum Vertrauen in Postgres unangetastet, **nicht löschen**) → `docker compose down`, alter pm2-Eintrag `babu-web` als Rückweg (bestehendes Muster). Postgres-Container kann parallel weiterlaufen, ist beim Rollback nicht im Weg.
- `insp-app`/`belege-review` werden zu keinem Zeitpunkt angefasst — kein Deploy-Schritt berührt sie.

## Risiken

- **`salon_von_aktiv`-Umstellung an 60 Stellen** ist die größte mechanische Fläche — Risiko von übersehenen Stellen, die weiterhin `salon_von` statt `salon_von_aktiv` nutzen und beim Acting-as stillschweigend falsche (Kanzlei- statt Mandanten-)Daten zeigen. Gegenmaßnahme: `salon_von` für neuen Code deprecaten (Lint/Grep-Check im CI: kein neuer Aufruf von `salon_von(` außerhalb `salon_von_aktiv` selbst).
- **`?`→`%s`-Übersetzung** ist safe nach heutiger Prüfung, muss aber bei jeder neuen SQL-Zeile künftig beachtet werden (Code-Review-Hinweis, ggf. Kommentar in `db.py`).
- **Global-Lock-Ablösung** (`_RECHNUNG_SCHLOSS`, `_TERMIN_SCHLOSS` etc. pro Box) ändert Nebenläufigkeitsverhalten — Tests für Race Conditions bei Rechnungsnummern-Vergabe pro Box nötig, nicht nur pro Prozess.
- **Kosten/Umfang**: Dies ist der größte Umbau des Projekts bisher (Auth-Modell, Datenschicht, Docker-Topologie gleichzeitig) — realistisch mehrere Wochen, nicht Tage; Phasierung ist so gewählt, dass nach jeder Phase ein sicherer Zwischenstand mit grüner Suite existiert.

---

### Critical Files for Implementation
- server/belegreview/babu_web.py
- server/belegreview/boxschreiber.py
- server/docker/compose.yml
- server/belegreview/tests/test_mehrseiten_buendel.py
- server/belegreview/einladung.py