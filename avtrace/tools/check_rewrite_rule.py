#!/usr/bin/env python3
"""Replay the send hook's DVD-start rewrite rule against a real capture.

Mirrors the word checks in source/avtrace_hooks.S.  Every send batch in the
capture is tested; the rule must match only DVD-start batches, and mode 1
must turn them into the byte-identical XMB RGB batch.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode_avtrace import read_records  # noqa: E402

CHECKS = (
    (0, 0x02050054), (4, 0x04000001), (8, 0x00010000), (12, 0x00010000),
    (16, 0x0205002C), (20, 0x01000002), (24, 0x00000001), (48, 0x00000009),
    (64, 0x02050014), (68, 0x00010001), (76, 0x00010001),
)


def matches(data: bytes) -> bool:
    if len(data) < 0x50:
        return False
    if any(struct.unpack_from(">I", data, off)[0] != value for off, value in CHECKS):
        return False
    return struct.unpack_from(">H", data, 72)[0] == 0x0010


def rewrite(data: bytes, mode: int) -> bytes:
    out = bytearray(data)
    if mode == 1:
        struct.pack_into(">I", out, 48, 0)
        struct.pack_into(">I", out, 76, 0)
    else:
        struct.pack_into(">I", out, 76, 1)
    return bytes(out)


def main() -> int:
    sends = [(seq, data) for _, seq, kind, _, _, _, data, _ in read_records(Path(sys.argv[1])) if kind == 1]
    hits = [(seq, data) for seq, data in sends if matches(data)]
    print(f"{len(sends)} send batches, {len(hits)} match the rule: {[s for s, _ in hits]}")
    xmb_rgb = {data for _, data in sends
               if len(data) == 116 and data[0:8] == bytes.fromhex("0205005404000001")
               and struct.unpack_from(">I", data, 48)[0] == 0
               and struct.unpack_from(">I", data, 76)[0] == 0}
    for seq, data in hits:
        full = rewrite(data, 1)
        print(f"#{seq}: mode 1 result identical to an XMB RGB batch from this capture: {full in xmb_rgb}")
        diff = [i for i in range(len(data)) if data[i] != full[i]]
        print(f"#{seq}: mode 1 changes byte offsets {diff}")
        out = rewrite(data, 2)
        print(f"#{seq}: mode 2 AV_VIDEO_CS word becomes {out[76:80].hex()}")
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main())
