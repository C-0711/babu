# AppleRootCA-G3.cer

Apples Wurzelzertifikat, gegen das die signierten Belege aus dem App Store
geprüft werden (`apple_abo.py`). Geholt am 10.10.2026 von

    https://www.apple.com/certificateauthority/AppleRootCA-G3.cer

    subject/issuer  CN=Apple Root CA - G3, OU=Apple Certification Authority,
                    O=Apple Inc., C=US   (selbstsigniert)
    gültig          30.04.2014 – 30.04.2039
    SHA-256         63:34:3A:BF:B8:9A:6A:03:EB:B5:7E:9B:3F:5F:A7:BE:7C:4F:5C:75:
                    6F:30:17:B3:A8:C4:88:C3:65:3E:91:79

Der Fingerabdruck steht zusätzlich in `apple_abo.WURZEL_SHA256`. Wird die
Datei getauscht, ohne dass dort derselbe Abdruck steht, verweigert das Modul
den Dienst statt blind zu vertrauen — ein vertauschtes Wurzelzertifikat wäre
sonst genau der Fehler, der jede Signaturprüfung wertlos macht.

Nachprüfen:

    openssl x509 -inform DER -in zertifikate/AppleRootCA-G3.cer \
        -noout -subject -fingerprint -sha256 -dates
