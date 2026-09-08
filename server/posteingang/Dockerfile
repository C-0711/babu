# Der Posteingang als eigenes Image — eigener Dienst, eigener Update-Zyklus.
#
# Bewusst NICHT im babu-web-Image: Port 25 braucht andere Rechte, und ein
# Absturz im Mailempfang darf die Belegannahme nicht mitreißen.
FROM python:3.12-slim

# Kein git, kein libpq, nichts. Der Dienst spricht HTTP und SMTP, sonst
# nichts — jedes Paket mehr wäre Angriffsfläche auf einem Port, der offen
# im Netz steht.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY posteingang.py /app/posteingang.py
WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Nicht als root. Port 25 im Container braucht das nicht: der Dienst hört
# im Container auf 2525, und die Weiterleitung von 25 auf 2525 macht der
# Host (siehe README.md). Ein Prozess mit CAP_NET_BIND_SERVICE, der fremde
# Mail entgegennimmt, wäre der falsche Handel.
RUN useradd --uid 1002 --create-home posteingang
USER 1002
ENV POSTEINGANG_PORT=2525

CMD ["python", "posteingang.py"]
