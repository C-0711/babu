#!/bin/sh
# UIKit-freie Logik-Harnesse (macOS, swiftc) — Muster wie in HANDOVER §4.
set -e
cd "$(dirname "$0")"
ZIEL="${TMPDIR:-/tmp}/beleg-harness"
mkdir -p "$ZIEL"

echo "— EXTF-Harness —"
swiftc -o "$ZIEL/extf" ../Beleg/Beleg/Models.swift ../Beleg/Beleg/ExtfWriter.swift extf/main.swift
"$ZIEL/extf"
