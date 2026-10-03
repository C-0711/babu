#!/usr/bin/env python3
"""stripe_einrichten — babu in einem Stripe-Konto einrichten (seit 03.10.2026).

Läuft auf der H200V (Host, nicht im Container), nur Standardbibliothek:

    python3 stripe_einrichten.py --modus test   # Dev-Spur: ~/babu-src/server/docker/.env
    python3 stripe_einrichten.py --modus live   # Betrieb:  ~/babu-docker/docker/.env

Den Schlüssel liest es aus der Umgebung `STRIPE_KEY`, sonst aus einer systemd-Unit
(`--unit`, Standard: die von Camp45 — babu teilt sich seit 03.10.2026 das Konto
„0711.io“ mit Camp45, Entscheidung Auftraggeber). Er wird nie ausgegeben.

Legt an (idempotent, Kennzeichen metadata.app=babu): drei Produkte mit Monatspreis
netto, Steuersatz 19 % exklusiv, den Webhook (ein vorhandener für dieselbe Adresse
wird ersetzt — sein Geheimnis gibt Stripe nur beim Anlegen heraus). Schreibt in der
.env NUR die BABU_STRIPE_*-Zeilen (Sicherung daneben);
Rechte eines eingeschränkten Schlüssels (rk_…) für babu: Checkout Sessions, Customer
portal, Webhook Endpoints, Products, Prices, Tax Rates = Schreiben; Subscriptions,
Invoices, Invoice Payments, Charges, Events, Customers = Lesen. im Testmodus zusätzlich
BABU_ABO=1, im Betrieb bleibt BABU_ABO, wie es ist. Danach den Container neu starten:
`docker compose up -d babu-web` (bzw. `-f compose-dev.yml up -d`).
"""
import argparse
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request

EREIGNISSE = ["checkout.session.completed", "checkout.session.async_payment_failed",
              "invoice.paid", "invoice.payment_failed", "customer.subscription.created",
              "customer.subscription.updated", "customer.subscription.deleted",
              "charge.dispute.created", "charge.refunded"]
p = argparse.ArgumentParser()
p.add_argument("--modus", choices=("test", "live"), required=True)
p.add_argument("--unit", default=None, help="systemd-Unit mit STRIPE_SECRET_KEY")
args = p.parse_args()
LIVE = args.modus == "live"
WEBHOOK_URL = ("https://mybabu.io" if LIVE else "https://dev.mybabu.io") + "/api/stripe/webhook"
PAKETE = [("solo", "babu Solo", 3900), ("salon", "babu Salon", 7900),
          ("plus", "babu Salon Plus", 14900)]
ENV = os.path.expanduser("~/babu-docker/docker/.env" if LIVE
                         else "~/babu-src/server/docker/.env")

praefixe = ("sk_live_", "rk_live_") if LIVE else ("sk_test_", "rk_test_")
KEY = os.environ.get("STRIPE_KEY", "").strip()
if not KEY:
    unit_name = args.unit or ("ib-platform.service" if LIVE else "ib-platform-dev.service")
    unit = subprocess.run(["systemctl", "--user", "cat", unit_name],
                          capture_output=True, text=True).stdout
    funde = [m.group(1) for m in re.finditer(r'^Environment="?STRIPE_SECRET_KEY=([^"\s]+)', unit, re.M)]
    KEY = ([k for k in funde if k.startswith(praefixe)] or [""])[-1]
if not KEY.startswith(praefixe):
    raise SystemExit(f"kein {args.modus}-Schlüssel gefunden (STRIPE_KEY oder --unit)")


def formular(daten, praefix=""):
    paare = []
    for k, v in daten.items():
        name = f"{praefix}[{k}]" if praefix else k
        if isinstance(v, dict):
            paare += formular(v, name)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                if isinstance(x, dict):
                    paare += formular(x, f"{name}[{i}]")
                else:
                    paare.append((f"{name}[{i}]", str(x)))
        else:
            paare.append((name, "true" if v is True else "false" if v is False else str(v)))
    return paare


def stripe(methode, pfad, daten=None):
    url = "https://api.stripe.com/v1" + pfad
    kopf = {"Authorization": f"Bearer {KEY}"}
    rumpf = None
    if methode == "GET" and daten:
        url += "?" + urllib.parse.urlencode(formular(daten))
    elif daten is not None:
        rumpf = urllib.parse.urlencode(formular(daten)).encode()
    anfrage = urllib.request.Request(url, data=rumpf, method=methode, headers=kopf)
    try:
        with urllib.request.urlopen(anfrage, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as ex:
        fehler = json.loads(ex.read() or b"{}").get("error", {})
        raise SystemExit(f"Stripe {ex.code} bei {methode} {pfad}: {fehler.get('message')}")


# Ein eingeschränkter Schlüssel darf das Konto oft nicht lesen — dann ohne Namen weiter.
try:
    konto = stripe("GET", "/account")
except SystemExit:
    konto = {"id": "(mit diesem Schlüssel nicht lesbar)"}
print(f"Konto: {(konto.get('settings') or {}).get('dashboard', {}).get('display_name') or (konto.get('business_profile') or {}).get('name')} "
      f"({konto.get('id')}), {'LIVE' if LIVE else 'Testmodus'}, Abbuchungstext: "
      f"{((konto.get('settings') or {}).get('payments') or {}).get('statement_descriptor')}")

# API-Version: die des Kontos (aus dem jüngsten Ereignis), sonst die des Webhooks
ev = stripe("GET", "/events", {"limit": 1}).get("data") or []
version = ev[0].get("api_version") if ev else None

# Produkte + Preise
produkte = stripe("GET", "/products", {"limit": 100, "active": "true"}).get("data", [])
preise = {}
for schl, name, cent in PAKETE:
    p = next((x for x in produkte if (x.get("metadata") or {}).get("babu_paket") == schl), None)
    if p is None:
        p = stripe("POST", "/products", {"name": name, "metadata": {"app": "babu", "babu_paket": schl}})
    vorhanden = stripe("GET", "/prices", {"product": p["id"], "active": "true", "limit": 10}).get("data", [])
    pr = next((x for x in vorhanden if x.get("unit_amount") == cent and x.get("currency") == "eur"
               and (x.get("recurring") or {}).get("interval") == "month"), None)
    if pr is None:
        pr = stripe("POST", "/prices", {"product": p["id"], "currency": "eur", "unit_amount": cent,
                                        "recurring": {"interval": "month"},
                                        "tax_behavior": "exclusive",
                                        "metadata": {"app": "babu", "babu_paket": schl}})
    preise[schl] = pr["id"]
    print(f"Preis {schl}: {pr['id']} ({cent / 100:.2f} € netto/Monat)")

# Steuersatz
saetze = stripe("GET", "/tax_rates", {"limit": 100, "active": "true"}).get("data", [])
satz = next((x for x in saetze if (x.get("metadata") or {}).get("app") == "babu"), None)
if satz is None:
    satz = stripe("POST", "/tax_rates", {"display_name": "USt", "description": "babu USt 19 %",
                                         "percentage": 19, "inclusive": False, "country": "DE",
                                         "jurisdiction": "DE", "tax_type": "vat",
                                         "metadata": {"app": "babu"}})
print(f"Steuersatz: {satz['id']} (19 %, exklusiv)")

# Webhook (Geheimnis gibt es nur beim Anlegen → vorhandenen ersetzen)
for w in stripe("GET", "/webhook_endpoints", {"limit": 100}).get("data", []):
    if w.get("url") == WEBHOOK_URL:
        stripe("DELETE", f"/webhook_endpoints/{w['id']}")
        print(f"alter Webhook {w['id']} ersetzt")
daten = {"url": WEBHOOK_URL, "enabled_events": EREIGNISSE,
         "description": "babu " + ("mybabu.io (live)" if LIVE else "Dev-Spur"), "metadata": {"app": "babu"}}
if version:
    daten["api_version"] = version
hook = stripe("POST", "/webhook_endpoints", daten)
version = hook.get("api_version") or version
print(f"Webhook: {hook['id']} → {WEBHOOK_URL}, API-Version {version}")

# .env: nur die Stripe-Zeilen ersetzen, alles andere bleibt; im Betrieb BABU_ABO NICHT
werte = {**({} if LIVE else {"BABU_ABO": "1"}), "BABU_STRIPE_SCHLUESSEL": KEY,
         "BABU_STRIPE_WEBHOOK_GEHEIMNIS": hook["secret"],
         "BABU_STRIPE_PREIS_SOLO": preise["solo"], "BABU_STRIPE_PREIS_SALON": preise["salon"],
         "BABU_STRIPE_PREIS_PLUS": preise["plus"], "BABU_STRIPE_STEUERSATZ": satz["id"],
         "BABU_STRIPE_VERSION": version or ""}
alt_zeilen = open(ENV).read().splitlines() if os.path.exists(ENV) else []
if os.path.exists(ENV):
    sicherung = ENV + ".bak-vor-stripe-" + time.strftime("%Y%m%d-%H%M%S")
    with open(sicherung, "w") as f:
        f.write("\n".join(alt_zeilen) + "\n")
    os.chmod(sicherung, 0o600)
behalten = [z for z in alt_zeilen if z.split("=", 1)[0].strip() not in werte]
neu_inhalt = behalten + [f"# Stripe {args.modus} (Konto {konto.get('id')}) — eingerichtet "
                         + time.strftime("%Y-%m-%d")] + [f"{k}={v}" for k, v in werte.items()]
fd = os.open(ENV + ".neu", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("\n".join(neu_inhalt) + "\n")
os.replace(ENV + ".neu", ENV)
print(f".env aktualisiert: {ENV} (0600), {len(behalten)} bestehende Zeilen behalten, "
      f"Schlüssel {len(KEY)} Zeichen, Geheimnis {len(hook['secret'])} Zeichen"
      + ("; BABU_ABO unverändert" if LIVE else "; BABU_ABO=1"))
