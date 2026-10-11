#!/usr/bin/env python3
"""
Kapitel 3 – Eine NDEF-Nachricht Byte für Byte.

Baut eine Nachricht aus URI-, Text- und External-Record, zeigt die Bytes mit
Erklärung und liest sie wieder zurück. Ohne Leser, ohne Karte.

Aufruf:  python3 03-tags-ndef/ndef_zerlegen.py [--url https://...] [--hex 0301...]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import hexs, unhex                       # noqa: E402
from nfcsmarthome.ndef import (Record, decode_message, encode_message,   # noqa: E402
                               find_ndef_tlv, wrap_tlv)


def explain(msg: bytes) -> None:
    pos, n = 0, 1
    while pos < len(msg):
        flags, tlen = msg[pos], msg[pos + 1]
        sr = flags & 0x10
        plen = msg[pos + 2] if sr else int.from_bytes(msg[pos + 2:pos + 6], "big")
        hdr = 3 if sr else 6
        names = [f for f, bit in (("MB", 0x80), ("ME", 0x40), ("SR", 0x10), ("IL", 0x08)) if flags & bit]
        print(f"Record {n}: Kopf {flags:02X} = {'+'.join(names)}, TNF {flags & 7}")
        print(f"          Typlänge {tlen}, Nutzdatenlänge {plen}")
        t = msg[pos + hdr:pos + hdr + tlen]
        p = msg[pos + hdr + tlen:pos + hdr + tlen + plen]
        print(f"          Typ      {hexs(t, ' ')}  ({t.decode('ascii', 'replace')})")
        print(f"          Nutzdaten {hexs(p[:12], ' ')}{' …' if len(p) > 12 else ''}")
        pos += hdr + tlen + plen
        n += 1
        if flags & 0x40:
            break


def main() -> int:
    ap = argparse.ArgumentParser(description="NDEF zerlegen")
    ap.add_argument("--url", default="https://home.local/t/kueche/licht")
    ap.add_argument("--hex", help="Speicherinhalt ab Seite 4 (hex) statt eigener Nachricht")
    args = ap.parse_args()

    if args.hex:
        msg = find_ndef_tlv(unhex(args.hex))
        if msg is None:
            print("Kein NDEF-Block (03) gefunden")
            return 1
    else:
        records = [Record.uri(args.url), Record.text("Licht Küche"),
                   Record.external("home.arpa:nfh", bytes(32))]
        msg = encode_message(records)
        tlv = wrap_tlv(msg)
        print(f"TLV auf dem Tag ({len(tlv)} Byte):")
        for i in range(0, len(tlv), 16):
            print(f"  Seite {4 + i // 4:3d}: {hexs(tlv[i:i + 16], ' ')}")
        print()
    explain(msg)
    print()
    for r in decode_message(msg):
        print("  " + r.describe())
    return 0


if __name__ == "__main__":
    sys.exit(main())
