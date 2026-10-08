"""Eigener Kassenklang für babu: „ka“ (Mechanik) + „ching“ (Glocke). Synthetisch, keine Vorlage.

Erzeugt kaching.wav; daraus die Datei in der App (beide Ziele, auch Push-Ton):
    python3 kaching.py && afconvert -f caff -d LEI16 kaching.wav ../../ios/Beleg/Beleg/kaching.caf
"""
import wave
import numpy as np

SR = 44100
dauer = 1.25
t = np.arange(int(SR * dauer)) / SR
x = np.zeros_like(t)
rng = np.random.default_rng(7)

def huelle(start, angriff, abkling, laenge=None):
    h = np.zeros_like(t)
    m = t >= start
    tt = t[m] - start
    a = np.clip(tt / angriff, 0, 1)
    h[m] = a * np.exp(-tt / abkling)
    if laenge:
        h[t > start + laenge] = 0
    return h

# „ka“: kurzer gefilterter Rauschstoß + tiefer Klack (Schublade/Taste)
rausch = rng.standard_normal(len(t))
kern = np.ones(6) / 6
rausch = np.convolve(rausch, kern, mode="same")          # etwas weicher
x += 0.35 * rausch * huelle(0.0, 0.002, 0.012, 0.05)
x += 0.45 * np.sin(2 * np.pi * 180 * t) * huelle(0.0, 0.002, 0.03, 0.12)
x += 0.25 * np.sin(2 * np.pi * 95 * t) * huelle(0.035, 0.002, 0.03, 0.12)

# „ching“: Glocke aus unharmonischen Teiltönen, zwei Anschläge (Münzen)
def glocke(start, grund, staerke):
    teil = [(1.0, 1.0, 0.9), (2.32, 0.55, 0.6), (2.76, 0.45, 0.5),
            (4.07, 0.25, 0.35), (5.4, 0.15, 0.25), (6.8, 0.08, 0.18)]
    s = np.zeros_like(t)
    for ratio, amp, ab in teil:
        f = grund * ratio
        if f > SR / 2 - 500:
            continue
        schwebung = 1 + 0.003 * np.sin(2 * np.pi * 5.5 * t)   # leichtes Schimmern
        s += amp * np.sin(2 * np.pi * f * t * schwebung) * huelle(start, 0.003, ab)
    return staerke * s

x += glocke(0.075, 1568.0, 0.55)    # G6
x += glocke(0.155, 2093.0, 0.42)    # C7
x += glocke(0.205, 2637.0, 0.22)    # E7 — kleines Nachklingeln

# sanft ausblenden, normalisieren auf -3 dBFS
x *= np.clip((dauer - t) / 0.15, 0, 1)
x = x / np.max(np.abs(x)) * (10 ** (-3 / 20))
pcm = (x * 32767).astype("<i2")
with wave.open("kaching.wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print("ok", len(pcm) / SR, "s, Spitze", float(np.max(np.abs(x))))
