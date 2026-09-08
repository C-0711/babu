# Posteingang — ein eigener Mailserver für babu

babu versprach die digitale Erfassung des ganzen Schriftverkehrs und konnte
bis hierher nur **senden** (`server/belegreview/postfach.py`). Post kam nur
ins System, wenn Nina sie abfotografiert hat. Dieser Dienst nimmt sie direkt
an: jeder Betrieb bekommt eine eigene Empfangsadresse, alles, was dorthin
geschickt wird, landet in seiner Belegbox.

**Stand: gebaut und lokal geprüft, NICHT in Betrieb.** Der Dienst steht im
Compose hinter einem Profil und startet bei einem gewöhnlichen
`docker compose up -d` nicht mit. Was der Betreiber dafür noch tun muss,
steht unten unter „Was noch fehlt".

---

## Wie es zusammenhängt

```
Absender ──SMTP:25──▶  posteingang (eigener Container)
                            │  nur HTTP, nie git
                            ├─ GET  /api/posteingang/aufloesen   welcher Betrieb?
                            ├─ POST /api/aufnahme                jeder Anhang
                            └─ POST /api/dokumente               der Mailtext
                                     │
                                babu-web ──▶ Belegbox (git)
```

Drei Entscheidungen, die nicht verhandelbar sind — die ausführliche
Begründung steht im Kopf von `posteingang.py`:

1. **Eigener Dienst, nicht eine Route in babu-web.** Port 25 braucht andere
   Rechte, und ein Absturz im Mailempfang darf die Belegannahme nicht
   mitreißen.
2. **Der Dienst schreibt NIE in die Belegbox.** Die Box ist ein
   Git-Repository mit einer Arbeitskopie und einem Index; das Schloss darum
   (`boxschreiber`, `Box.schloss`) schützt nur innerhalb eines Prozesses.
   Zwei Schreiber auf demselben Klon committen einander fremden Inhalt.
   Genau ein Dienst darf Eigentümer sein, und das ist babu-web.
3. **Die Zuordnung hängt an einer nicht erratbaren Adresse.** An diese
   Adresse schreiben Lieferanten und Ämter — es kann keine Absenderliste
   geben. Also ist die Nichterratbarkeit die Zugangskontrolle: der lokale
   Teil ist ein Zufallswort aus `post_adresse` (16 Zeichen, ~79 Bit), kein
   Name. Wäre er erratbar (`nina@…`), könnte jeder Fremde Belege in eine
   fremde Belegbox schicken.

## Was der Dienst abwehrt

| Prüfung | Grenze (Vorgabe) | Umgebungsvariable |
|---|---|---|
| Rate-Limit je absendender IP | 60 Empfänger / Stunde | `POSTEINGANG_RATE_IP` |
| Rate-Limit je Empfangsadresse | 120 / Stunde | `POSTEINGANG_RATE_ADRESSE` |
| Fensterlänge | 3600 s | `POSTEINGANG_FENSTER` |
| Empfänger je Sendung | 5 | `POSTEINGANG_EMPFAENGER_MAX` |
| Ganze Sendung | 25 MB (auch als SMTP-`SIZE`) | `POSTEINGANG_SENDUNG_MAX` |
| Ein Anhang | 15 MB | `POSTEINGANG_ANHANG_MAX` |
| Anhänge je Sendung | 25 | `POSTEINGANG_ANHAENGE_MAX` |
| Formate | `.pdf .jpg .jpeg .png .heic` | fest im Code |

**Kein Relay:** Post an eine Adresse, die nicht aktiv in `post_adresse`
steht, wird mit **550** abgewiesen und nirgends abgelegt. Das ist der
einzige Fall, in dem der Dienst 5xx antwortet. Alles andere — babu-web
nicht erreichbar, Rate-Limit, Fehler beim Ablegen — wird ein **4xx**, damit
der absendende Server die Mail aufhebt und später erneut zustellt. Ein 5xx
an dieser Stelle wäre verlorene Post. Wiederholung ist ungefährlich:
babu-web legt bytegleiche Dateien nicht zweimal ab.

**Nichts wird still geschluckt.** Ein Anhang im falschen Format oder über
der Grenze wird mit Namen und Grund in den abgelegten Mailtext geschrieben.
Der Mailtext selbst wird immer abgelegt — mit Absender, Betreff und Datum,
auch wenn kein Anhang dabei war: eine Kündigung steht selten im Anhang.

**Was der Dienst NICHT tut** (und was ihn deshalb nicht ersetzt):
kein Spamfilter, keine Virenprüfung, keine SPF-/DKIM-/DMARC-Prüfung der
Absender, keine Antwort an den Absender, keine Weiterleitung. Er liest auch
nichts — die Deutung eines Belegs ist babu-webs Aufgabe und steht dort
genau einmal.

## Adressen anlegen

Eine Adresse entsteht nie von selbst, sondern nur auf Zuruf — wie die
Belegbox. Als Kanzlei oder Betreiber:

```
POST /api/posteingang/adresse/<mandant_id>        neue Adresse würfeln
GET  /api/posteingang/adresse/<mandant_id>        alle, auch stillgelegte
POST /api/posteingang/adresse/<mandant_id>/stilllegen   {"lokal": "…"}
```

Der lokale Teil kommt aus dem Zufallsgenerator und kann **nicht** gewählt
werden — ein Wunschname hätte die Nichterratbarkeit abgeschafft, auf der die
ganze Zuordnung steht. Höchstens fünf aktive Adressen je Betrieb.
Stillgelegt statt gelöscht: steht die Adresse einmal auf einem Briefkopf,
kommt Post noch Monate später, und derselbe Zufallswert darf nie neu
vergeben werden.

---

## Was noch fehlt — die Handgriffe des Betreibers

Der Dienst ist fertig und geprüft, **das Netz ist es nicht.** Die H200V hat
keine öffentliche IP (192.168.145.10 im LAN, dazu Tailscale); auf dem
NAT-Ausgang 185.28.96.86 ist von außen nichts erreichbar, auch nicht 80
oder 443. In dieser Reihenfolge:

### 1. Geheimnisse anlegen

Zwei Werte, beide in `server/docker/.env` auf der H200V (0600, nicht ins
Repo):

```
BABU_POSTEINGANG_TOKEN=<32 zufällige Zeichen>   # gemeinsam mit babu-web
BABU_POSTEINGANG_PAT=<PAT eines Zugangs>        # nur für den Mailserver
```

* Das **Token** teilen babu-web und der Mailserver. Ohne es antwortet
  `/api/posteingang/aufloesen` grundsätzlich nicht — das ist der richtige
  Ruhezustand, solange kein Mailserver läuft.
* Der **PAT** gehört einem Zugang, der in der betreuenden Kanzlei Mitglied
  ist (`kanzlei_mitglied`). Der Mailserver hat keine eigene Berechtigung:
  er schickt `X-Mandant: <id>` mit und geht damit durch dieselbe Wache wie
  ein Mensch im Portal (`babu_web._box_wache`). **Admin allein reicht
  nicht** — Mitgliedschaft in der Kanzlei des Mandanten ist die Bedingung.

Danach babu-web neu bauen und hochfahren, damit es das Token kennt
(Deploy-Ritual aus CLAUDE.md: **immer `rsync server/` komplett**).

### 2. DNS bei Cloudflare

Die Zone `0711.io` liegt bei Cloudflare.

```
post.babu.0711.io.   A    185.28.96.86      ← Proxy AUS (graue Wolke)
babu.0711.io.        MX   10 post.babu.0711.io.
```

**Der A-Eintrag darf NICHT über den Cloudflare-Proxy laufen.** Cloudflare
proxiet kein SMTP — mit oranger Wolke zeigt der Name auf Cloudflares
Adressen, und dort nimmt niemand Port 25 an. MX-Einträge selbst sind nie
proxierbar, aber der Name, auf den sie zeigen, muss „DNS only" stehen.

Welche Domäne die Adressen tragen, bestimmt `BABU_POST_DOMAENE` — in beiden
Containern derselbe Wert, sonst weist der Mailserver Post an Adressen ab,
die das Portal ausgibt.

### 3. Port 25 durchreichen

Zwei Sprünge:

* **Router/NAT:** 185.28.96.86:25 → 192.168.145.10:25. Viele Anschlüsse
  haben Port 25 ausgehend UND eingehend gesperrt — beim Anbieter freischalten
  lassen, bevor irgendetwas anderes probiert wird.
* **Host:** 25 → 2525, weil der Container als unprivilegierter Nutzer läuft
  und fremde Mail nicht mit Portrechten entgegennehmen soll, z. B.
  `iptables -t nat -A PREROUTING -p tcp --dport 25 -j REDIRECT --to-port 2525`
  (dauerhaft ablegen, sonst ist es nach dem nächsten Neustart weg).

### 4. Reverse-DNS (PTR)

`185.28.96.86` muss rückwärts auf `post.babu.0711.io` auflösen. Das kann
**nur der Anbieter der IP** setzen, nicht Cloudflare. Ohne PTR weisen
Google, Microsoft und die großen deutschen Anbieter eingehend zwar nichts
ab — aber jede Antwort, die babu später selbst verschickt, landet im Spam.

### 5. SPF und DMARC

Für `0711.io` **existiert beides bereits** (`p=none`). Beide sind reine
Absender-Regeln und für den Empfang bedeutungslos — dieser Dienst prüft sie
nicht. Zu tun ist hier also nichts; zu wissen ist:

* Solange `p=none` steht, sagt DMARC niemandem, was er mit gefälschter Post
  „von 0711.io" tun soll. Das anzuziehen (`p=quarantine`) ist eine eigene
  Entscheidung und betrifft den Versand, nicht diesen Dienst.
* Wenn babu später aus dem Posteingang heraus antworten soll, braucht es
  DKIM und einen SPF-Eintrag, der diese Maschine einschließt.

### 6. STARTTLS (optional, aber empfohlen)

Ein Zertifikat für `post.babu.0711.io` ablegen und den Container darauf
zeigen lassen:

```
POSTEINGANG_TLS_ZERT=/pfad/fullchain.pem
POSTEINGANG_TLS_SCHLUESSEL=/pfad/privkey.pem
```

Ohne die beiden startet der Dienst trotzdem und nimmt unverschlüsselt an.
Das ist Absicht: eingehendes SMTP zwischen fremden Servern ist im Netz
überwiegend opportunistisch verschlüsselt, und ein Dienst, der ohne
Zertifikat gar nicht startet, nimmt gar keine Post an.

### 7. Erst dann scharf schalten

```
cd ~/babu-docker/docker
docker compose --profile posteingang build posteingang
docker compose --profile posteingang up -d posteingang
docker compose logs -f posteingang
```

Rückweg: `docker compose stop posteingang`. babu-web bleibt davon
unberührt — das ist der Grund, warum es ein eigener Container ist.

---

## Prüfen, ohne dass das Netz steht

Der ganze Empfangsweg ist ohne Netz geprüft:

```
cd server/belegreview
/tmp/babu-venv/bin/python -m pytest tests/test_posteingang.py -q -p no:cacheprovider
```

29 Tests: guter Fall, unbekannte Adresse (550, nichts abgelegt), zwei
Betriebe ohne Übersprechen, Größen- und Formatgrenzen, Rate-Limit,
babu-web weg (4xx statt 550), und ein echter SMTP-Server auf 127.0.0.1.
`aiosmtpd` muss dafür im venv liegen (`pip install aiosmtpd`); fehlt es,
wird nur der letzte Test übersprungen.

Von Hand gegen einen laufenden Container:

```
python3 -c "
import smtplib, email.message
m = email.message.EmailMessage()
m['From']='ich@example.org'; m['To']='<lokal>@post.babu.0711.io'
m['Subject']='Probe'; m.set_content('Text')
m.add_attachment(open('rechnung.pdf','rb').read(),
                 maintype='application', subtype='pdf', filename='rechnung.pdf')
s = smtplib.SMTP('127.0.0.1', 2525); s.send_message(m); s.quit()"
```
