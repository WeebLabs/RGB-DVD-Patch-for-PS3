#!/usr/bin/env python3
"""Check an avtrace build against the supplied 4.92 VSH before it goes near a PS3.

Checks:
  1. Every signature word in avtrace.c matches the decrypted 4.92 VSH ELF.
  2. The built PRX imports only sys_fs and sysPrxForUser.
  3. The PRX contains the expected log strings and the SPRX exists.
  4. The hook disassembly contains exactly the expected syscalls.
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
SOURCE = PROJECT / "source/avtrace.c"
PRX = PROJECT / "avtrace.prx"
SPRX = PROJECT / "avtrace.sprx"
DISASM = PROJECT / "build/avtrace_hooks.disasm.txt"

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
        p_type = struct.unpack_from(">I", data, base)[0]
        offset, vaddr, _, filesz = struct.unpack_from(">QQQQ", data, base + 8)
        if p_type == 1 and filesz:
            segments.append((vaddr, offset, filesz))
    return segments


def read_word(data: bytes, segments, address: int) -> int:
    for vaddr, offset, filesz in segments:
        if vaddr <= address < vaddr + filesz:
            return struct.unpack_from(">I", data, offset + address - vaddr)[0]
    raise ValueError(f"address {address:#x} not in a PT_LOAD segment")


def source_array(text: str, name: str) -> list[int]:
    match = re.search(name + r"\[\]\s*=\s*\{(.*?)\};", text, re.S)
    if not match:
        raise ValueError(f"{name} not found in source")
    return [int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]{8})u", match.group(1))]


def source_define(text: str, name: str) -> int:
    match = re.search(r"#define\s+" + name + r"\s+0x([0-9A-Fa-f]+)u", text)
    if not match:
        raise ValueError(f"{name} not found in source")
    return int(match.group(1), 16)


def check_signatures() -> None:
    if not VSH_ELF.exists():
        print("note: decrypted VSH not available; signatures not re-checked against firmware")
        return
    text = SOURCE.read_text()
    data = VSH_ELF.read_bytes()
    segments = load_segments(data)
    checks = (
        ("g_send_signature", "VSH_SEND_ADDRESS"),
        ("g_recv_signature", "VSH_RECV_SIGNATURE_ADDRESS"),
        ("g_recv_wrapper_signature", "VSH_RECV_WRAPPER_ADDRESS"),
    )
    for array_name, address_name in checks:
        words = source_array(text, array_name)
        address = source_define(text, address_name)
        actual = [read_word(data, segments, address + 4 * i) for i in range(len(words))]
        if actual == words:
            ok(f"{array_name} matches VSH at {address:#010x} ({len(words)} words)")
        else:
            fail(f"{array_name} does not match VSH at {address:#010x}")

    send_original = source_define(text, "VSH_SEND_ORIGINAL")
    recv_original = source_define(text, "VSH_RECV_ORIGINAL")
    if read_word(data, segments, source_define(text, "VSH_SEND_ADDRESS")) == send_original:
        ok("VSH_SEND_ORIGINAL is the real first instruction")
    else:
        fail("VSH_SEND_ORIGINAL is wrong")
    if read_word(data, segments, source_define(text, "VSH_RECV_PATCH_ADDRESS")) == recv_original:
        ok("VSH_RECV_ORIGINAL is the real nop")
    else:
        fail("VSH_RECV_ORIGINAL is wrong")


def check_prx() -> None:
    if not PRX.exists() or not SPRX.exists():
        fail("avtrace.prx or avtrace.sprx missing; build first")
        return
    ok(f"avtrace.sprx present, {SPRX.stat().st_size} bytes")

    output = subprocess.run(
        [sys.executable, str(PARSE_PRX), str(PRX)],
        capture_output=True, text=True, check=False,
    ).stdout
    modules = re.findall(r"^\[([^\]]+)\]", output, re.M)
    if sorted(modules) == ["sysPrxForUser", "sys_fs"]:
        ok(f"imports only {', '.join(modules)}")
    else:
        fail(f"unexpected imports: {modules}")

    blob = PRX.read_bytes()
    for needed in (
        b"avtrace 0.2 starting",
        b"/dev_hdd0/tmp/avtrace.disable",
        b"CHECK: all VSH signatures match",
        b"READY: tracing PS3AV send and receive",
        b"RESTORED: send wrapper",
        b"RESTORED: receive call site",
        b"/dev_hdd0/tmp/avtrace.rgb_full",
        b"/dev_hdd0/tmp/avtrace.rgb_out",
        b"MODE: trace only; nothing is rewritten",
    ):
        if needed in blob:
            ok(f"string present: {needed.decode()}")
        else:
            fail(f"string missing: {needed.decode()}")


def check_disassembly() -> None:
    if not DISASM.exists():
        fail("hook disassembly missing")
        return
    text = DISASM.read_text(errors="replace")
    sc_count = len(re.findall(r"\bsc\b", text))
    li369 = len(re.findall(r"li\s+r11,369\b", text))
    li368 = len(re.findall(r"li\s+r11,368\b", text))
    if sc_count == 1 and li369 == 1 and li368 == 0:
        ok("hooks contain exactly one syscall (369, send) and no receive syscall")
    else:
        fail(f"syscall count unexpected: sc={sc_count} li369={li369} li368={li368}")
    if re.search(r"\bbl\s", text):
        fail("hook code contains a function call")
    else:
        ok("hook code calls no function")


def main() -> int:
    check_signatures()
    check_prx()
    check_disassembly()
    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
