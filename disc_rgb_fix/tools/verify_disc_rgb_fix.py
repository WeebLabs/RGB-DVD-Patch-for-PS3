#!/usr/bin/env python3
"""Check a disc_rgb_fix 2.0 build before it goes near a PS3.

Checks:
  1. The send-wrapper signature in the C source matches the 4.92 VSH ELF
     (skipped with a note when the decrypted ELF is not available).
  2. The built PRX imports only sys_fs and sysPrxForUser.
  3. The PRX contains the expected log strings.
  4. The hook disassembly has exactly one syscall (369) and no calls.
  5. The batch checks in rgbfix_hook.S are exactly the rule replayed
     against the real captures, and that rule matches only the DVD-start
     batch in capture 0002 and turns it into the XMB RGB bytes.
"""

from __future__ import annotations

import re
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
ROOT = PROJECT.parent
VSH_ELF = ROOT / "fresh_492_analysis/decrypted/vsh_module_vsh.self.elf"
PARSE_PRX = ROOT / "tools/parse_prx.py"
SOURCE = PROJECT / "source/disc_rgb_fix.c"
HOOK = PROJECT / "source/rgbfix_hook.S"
PRX = PROJECT / "disc_rgb_fix.prx"
SPRX = PROJECT / "disc_rgb_fix.sprx"
DISASM = PROJECT / "build/rgbfix_hook.disasm.txt"
CAPTURE_DVD = ROOT / "logs/0002-dvd-playback/sends.bin"

sys.path.insert(0, str(ROOT / "avtrace/tools"))
from check_rewrite_rule import CHECKS, matches, rewrite  # noqa: E402
from decode_avtrace import read_records  # noqa: E402

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)
    print("FAIL:", message)


def ok(message: str) -> None:
    print("ok:  ", message)


def load_segments(data: bytes):
    phoff = struct.unpack_from(">Q", data, 0x20)[0]
    phentsize, phnum = struct.unpack_from(">HH", data, 0x36)
    segments = []
    for i in range(phnum):
        base = phoff + i * phentsize
        if struct.unpack_from(">I", data, base)[0] != 1:
            continue
        offset, vaddr, _, filesz = struct.unpack_from(">QQQQ", data, base + 8)
        if filesz:
            segments.append((vaddr, offset, filesz))
    return segments


def read_word(data: bytes, segments, address: int) -> int:
    for vaddr, offset, filesz in segments:
        if vaddr <= address < vaddr + filesz:
            return struct.unpack_from(">I", data, offset + address - vaddr)[0]
    raise ValueError(f"{address:#x} not in a PT_LOAD segment")


def check_signature() -> None:
    text = SOURCE.read_text()
    body = re.search(r"g_send_signature\[\]\s*=\s*\{(.*?)\};", text, re.S).group(1)
    words = [int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]{8})u", body)]
    address = int(re.search(r"VSH_SEND_ADDRESS\s+0x([0-9A-Fa-f]+)u", text).group(1), 16)
    original = int(re.search(r"VSH_SEND_ORIGINAL\s+0x([0-9A-Fa-f]+)u", text).group(1), 16)
    if words[0] != original:
        fail("VSH_SEND_ORIGINAL is not the first signature word")
    if not VSH_ELF.exists():
        print("note: decrypted VSH not available; signature not re-checked against firmware")
        return
    data = VSH_ELF.read_bytes()
    segments = load_segments(data)
    actual = [read_word(data, segments, address + 4 * i) for i in range(len(words))]
    if actual == words:
        ok(f"send signature matches VSH at {address:#010x} ({len(words)} words)")
    else:
        fail("send signature does not match VSH")


def check_prx() -> None:
    if not PRX.exists() or not SPRX.exists():
        fail("disc_rgb_fix.prx or .sprx missing; build first")
        return
    ok(f"disc_rgb_fix.sprx present, {SPRX.stat().st_size} bytes")
    if PARSE_PRX.exists():
        output = subprocess.run([sys.executable, str(PARSE_PRX), str(PRX)],
                                capture_output=True, text=True, check=False).stdout
        modules = sorted(re.findall(r"^\[([^\]]+)\]", output, re.M))
        if modules == ["sysPrxForUser", "sys_fs"]:
            ok("imports only sys_fs, sysPrxForUser")
        else:
            fail(f"unexpected imports: {modules}")
    blob = PRX.read_bytes()
    for needed in (b"disc_rgb_fix 2.0.1 starting",
                   b"/dev_hdd0/tmp/disc_rgb_fix.disable",
                   b"WAIT: letting the XMB finish starting",
                   b"READY: DVD-start AV MULTI batch will be kept RGB",
                   b"RESTORED: send wrapper"):
        if needed in blob:
            ok(f"string present: {needed.decode()}")
        else:
            fail(f"string missing: {needed.decode()}")
    for forbidden in (b"PS3MAPI_OPCODE_GET_ALL_PROC_PID", b"bdp_BDVD.self"):
        if forbidden in blob:
            fail(f"retired 1.12 content present: {forbidden.decode()}")


def check_disassembly() -> None:
    if not DISASM.exists():
        fail("hook disassembly missing")
        return
    text = DISASM.read_text(errors="replace")
    if (len(re.findall(r"\bsc\b", text)) == 1 and
            len(re.findall(r"li\s+r11,369\b", text)) == 1):
        ok("hook contains exactly one syscall (369)")
    else:
        fail("hook syscall count unexpected")
    if re.search(r"\bbl\s", text):
        fail("hook code contains a function call")
    else:
        ok("hook code calls no function")


def hook_rule() -> list[tuple[int, int, int]]:
    """Return (offset, width, value) pairs checked by the assembly."""
    r0 = None
    pending = None
    pairs = []
    for raw in HOOK.read_text().splitlines():
        line = raw.split("/*")[0].strip()
        m = re.match(r"(lwz|lhz)\s+9,(\d+)\(10\)$", line)
        if m:
            pending = (int(m.group(2)), 4 if m.group(1) == "lwz" else 2)
            continue
        m = re.match(r"lis\s+0,(0x[0-9a-fA-F]+|\d+)$", line)
        if m:
            r0 = int(m.group(1), 0) << 16
            continue
        m = re.match(r"ori\s+0,0,(0x[0-9a-fA-F]+|\d+)$", line)
        if m and r0 is not None:
            r0 |= int(m.group(1), 0)
            continue
        m = re.match(r"cmpw\s+7,9,0$", line)
        if m and pending:
            pairs.append((pending[0], pending[1], r0))
            pending = None
            continue
        m = re.match(r"cmpwi\s+7,9,(0x[0-9a-fA-F]+|\d+)$", line)
        if m and pending:
            pairs.append((pending[0], pending[1], int(m.group(1), 0)))
            pending = None
    return pairs


def check_rule() -> None:
    expected = sorted([(off, 4, value) for off, value in CHECKS] + [(72, 2, 0x10)])
    actual = sorted(hook_rule())
    if actual == expected:
        ok(f"hook checks the same {len(actual)} fields as the replayed rule")
    else:
        fail(f"hook rule differs from replayed rule:\n  hook {actual}\n  rule {expected}")
    if not CAPTURE_DVD.exists():
        print("note: capture 0002 not available; rule not replayed")
        return
    sends = [(seq, data) for _, seq, kind, _, _, _, data, _ in read_records(CAPTURE_DVD) if kind == 1]
    hits = [seq for seq, data in sends if matches(data)]
    if hits == [365]:
        ok("rule matches only the DVD-start batch (#365) in capture 0002")
    else:
        fail(f"rule matches {hits} in capture 0002")
    exit_batch = next(data for seq, data in sends if seq == 489)
    start_batch = next(data for seq, data in sends if seq == 365)
    if rewrite(start_batch, 1) == exit_batch:
        ok("rewritten DVD-start batch is byte-identical to the XMB RGB batch (#489)")
    else:
        fail("rewritten DVD-start batch differs from the XMB RGB batch")


def main() -> int:
    check_signature()
    check_prx()
    check_disassembly()
    check_rule()
    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
