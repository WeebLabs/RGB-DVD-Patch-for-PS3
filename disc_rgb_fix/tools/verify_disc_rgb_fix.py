#!/usr/bin/env python3
"""Check a disc_rgb_fix 2.x build before it goes near a PS3.

Checks:
  1. The send-wrapper signature in the C source matches the 4.92 VSH ELF
     (skipped with a note when the decrypted ELF is not available).
  2. The built PRX imports only sys_fs, sysPrxForUser and vshtask, and
     from vshtask only vshtask_notify (NID 0xA02D46E7).
  3. The PRX contains the expected log strings.
  4. The hook disassembly has exactly one syscall (369) and no calls.
  5. The batch checks in rgbfix_hook.S are exactly the rule replayed
     against the real captures, and that rule matches only the DVD-start
     batch in capture 0002 and turns it into the XMB RGB bytes.
  6. The rewrite part of the hook is the 2.0.1 code (tag v2.0.1 in the public
     repository, commit fce7a56 in the working one) with
     only its "skip" branch target renamed, and the send part is unchanged.
  7. The 2.1 mode observer only reads the batch, writes only the observer,
     and uses only r6-r8 and cr6.  Replayed against captures 0002 (which
     contains 0001), 0003 and 0007, it reports every batch that carries VIDEO_MODE, and
     reports 480i -> 576i -> 480i, all RGB, for 0007.
  8. The pop-up mode names in the C source equal the decoder's AV_VID table.
  9. The 2.1.3 skip rule, replayed on 0007, hides the DVD-start 480i pop-up
     and shows 576i RGB and the exit 480i RGB.
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
# Send records only (no replies or HDMI event payloads).  0002 contains the
# whole 0001 session, so 0001 needs no file of its own.
CAPTURES = {
    "0002": CAPTURE_DVD,
    "0003": ROOT / "logs/0003-dvd-rgb-full/sends.bin",
    "0007": ROOT / "logs/0007-pal-dvd-on-480i/sends.bin",
}
# The same 2.0.1 file under the public tag and the working-repository commit.
HOOK_2_0_1 = ("v2.0.1:disc_rgb_fix/source/rgbfix_hook.S",
              "fce7a56:disc_rgb_fix/source/rgbfix_hook.S")
TIMEBASE_HZ = 79_800_000

sys.path.insert(0, str(ROOT / "avtrace/tools"))
from check_rewrite_rule import CHECKS, matches, rewrite  # noqa: E402
from decode_avtrace import AV_CS, AV_VID, read_records, split_packets  # noqa: E402

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
        if modules == ["sysPrxForUser", "sys_fs", "vshtask"]:
            ok("imports only sys_fs, sysPrxForUser, vshtask")
        else:
            fail(f"unexpected imports: {modules}")
        block = re.search(r"^\[vshtask\][^\n]*\n((?:\s+\d+ nid=.*\n)*)", output, re.M)
        nids = re.findall(r"nid=0x([0-9a-f]{8})", block.group(1)) if block else []
        if nids == ["a02d46e7"]:
            ok("vshtask import is only vshtask_notify (0xA02D46E7)")
        else:
            fail(f"unexpected vshtask imports: {nids}")
    blob = PRX.read_bytes()
    for needed in (b"disc_rgb_fix 2.1.3 starting",
                   b"/dev_hdd0/tmp/disc_rgb_fix.disable",
                   b"/dev_hdd0/tmp/disc_rgb_fix.nopopup",
                   b"WAIT: letting the XMB finish starting",
                   b"READY: DVD-start AV MULTI batch will be kept RGB",
                   b"READY: output-mode changes are reported",
                   b"MODE: ",
                   b"POPUP: ",
                   b"; skipped, same mode as before",
                   b"; skipped, DVD start in the current mode",
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


def instructions(text: str) -> list[str]:
    """Code lines of an assembly file, comments and directives removed."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line and not line.startswith("."):
            lines.append(line)
        elif line.startswith(".L") and line.endswith(":"):
            lines.append(line)
    return lines


def region(lines: list[str], start: str, end: str | None) -> list[str]:
    first = lines.index(start) + 1
    return lines[first:lines.index(end)] if end else lines[first:]


def hook_rule() -> list[tuple[int, int, int]]:
    """Return (offset, width, value) pairs checked by the rewrite part."""
    r0 = None
    pending = None
    pairs = []
    for line in region(instructions(HOOK.read_text()), "rgbfix_send_hook:", ".Lobserve:"):
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


def check_unchanged_parts() -> None:
    old_text = None
    for ref in HOOK_2_0_1:
        try:
            old_text = subprocess.run(["git", "-C", str(ROOT), "show", ref],
                                      capture_output=True, text=True, check=True).stdout
            break
        except (OSError, subprocess.CalledProcessError):
            continue
    if old_text is None:
        print("note: 2.0.1 hook not available from git; 2.0.1 comparison skipped")
        return
    old = instructions(old_text)
    new = instructions(HOOK.read_text())
    old_rewrite = [line.replace(",.Lsend", ",.Lobserve")
                   for line in region(old, "rgbfix_send_hook:", ".Lsend:")]
    if region(new, "rgbfix_send_hook:", ".Lobserve:") == old_rewrite:
        ok("rewrite part is the 2.0.1 code; only its skip target moved to .Lobserve")
    else:
        fail("rewrite part differs from 2.0.1 beyond the skip target")
    if region(new, ".Lsend:", None) == region(old, ".Lsend:", None):
        ok("send, result mapping and return are the 2.0.1 code")
    else:
        fail("send part differs from 2.0.1")


def observer_model():
    """Parse the observer block into (min_length, checks, copies, ok)."""
    lines = region(instructions(HOOK.read_text()), ".Lobserve:", ".Lsend:")
    allowed = {"clrldi", "cmplwi", "blt", "bne", "bne-", "lwz", "lhz", "lis", "ori",
               "cmpw", "cmpwi", "stw", "lwsync", "addi", "lwarx", "stwcx."}
    min_length = None
    checks, copies = [], []
    r6 = None
    pending = None
    good = True
    for line in lines:
        if line.endswith(":"):
            continue
        op, _, args = line.partition(" ")
        if op not in allowed:
            fail(f"observer uses unexpected instruction: {line}")
            good = False
            continue
        if op in ("lwz", "lhz", "lis", "ori", "addi", "clrldi", "lwarx"):
            if args.split(",")[0] not in ("6", "7", "8"):
                fail(f"observer writes a register other than r6-r8: {line}")
                good = False
        if op in ("cmplwi", "cmpw", "cmpwi", "blt", "bne") and not args.startswith("6,"):
            fail(f"observer uses a condition field other than cr6: {line}")
            good = False
        if op in ("blt", "bne", "bne-"):
            if args.split(",")[-1] not in (".Lsend", ".Lmode"):
                fail(f"observer branches somewhere unexpected: {line}")
                good = False
        m = re.match(r"cmplwi 6,8,(0x[0-9a-fA-F]+|\d+)$", line)
        if m:
            min_length = int(m.group(1), 0)
        m = re.match(r"(lwz|lhz) 7,(\d+)\(8\)$", line)
        if m:
            pending = (int(m.group(2)), 4 if m.group(1) == "lwz" else 2)
        m = re.match(r"lis 6,(0x[0-9a-fA-F]+|\d+)$", line)
        if m:
            r6 = int(m.group(1), 0) << 16
        m = re.match(r"ori 6,6,(0x[0-9a-fA-F]+|\d+)$", line)
        if m:
            r6 |= int(m.group(1), 0)
        if line == "cmpw 6,7,6":
            checks.append((*pending, r6))
        m = re.match(r"cmpwi 6,7,(0x[0-9a-fA-F]+|\d+)$", line)
        if m:
            checks.append((*pending, int(m.group(1), 0)))
        if op == "stw":
            m = re.match(r"stw 7,(\d+)\(30\)$", line)
            if not m:
                fail(f"observer stores somewhere other than the observer: {line}")
                good = False
            else:
                copies.append((*pending, int(m.group(1))))
        if op == "stwcx." and args != "7,0,8":
            fail(f"observer counter store unexpected: {line}")
            good = False
    if "addi 8,30,12" not in lines or "lwsync" not in lines:
        fail("observer counter is not observer+12 after an lwsync")
        good = False
    if lines.index("lwsync") < max(i for i, l in enumerate(lines) if l.startswith("stw ")):
        fail("observer bumps the counter before all fields are stored")
        good = False
    return min_length, checks, copies, good


def observe(model, data: bytes):
    """What the observer block stores for one (already rewritten) batch."""
    min_length, checks, copies, _ = model
    if len(data) < min_length:
        return None
    for offset, width, value in checks:
        if int.from_bytes(data[offset:offset + width], "big") != value:
            return None
    return {field: int.from_bytes(data[offset:offset + width], "big")
            for offset, width, field in copies}


def mode_text(report) -> str:
    """Python copy of describe_mode() in disc_rgb_fix.c."""
    vid, cs_out, port = report[24], report[28], report[20]
    names = {0: "RGB", 1: "YCbCr 4:4:4", 2: "YCbCr 4:2:2"}
    text = f"{AV_VID.get(vid, f'mode {vid:#x}')} {names.get(cs_out, f'colour space {cs_out:#x}')}"
    if port in (0, 1):
        text += " (HDMI)"
    elif port != 0x10:
        text += f" (port {port:#x})"
    return text


def has_video_mode(data: bytes) -> bool:
    for _, header, packet in split_packets(data):
        if header and header[2] == 0x04000001:
            if has_video_mode(packet[16:]):
                return True
        elif header and header[2] == 0x01000002:
            return True
    return False


def popups(reports) -> list[tuple[float, str, str]]:
    """Python copy of the worker: (time, text, decision) per settled mode.

    reports are (time, text, (port, vid, cs_out), corrected).  The worker
    decides once the settle time passes without a further mode change.  It
    skips a mode equal to the last decided one, and, before any mode is
    known, a window that contained a DVD-start correction.
    """
    source = SOURCE.read_text()
    poll = int(re.search(r"POLL_USECONDS\s+(\d+)u", source).group(1)) / 1e6
    settle = int(re.search(r"POPUP_SETTLE_POLLS\s+(\d+)u", source).group(1)) * poll
    decided = []
    known = None
    corrected = False
    for i, (t, text, key, rewritten) in enumerate(reports):
        corrected = corrected or rewritten
        if i + 1 < len(reports) and reports[i + 1][0] - t <= settle + poll:
            continue
        if known == key:
            decision = "skipped, same mode"
        elif known is None and corrected:
            decision = "skipped, DVD start"
        else:
            decision = "shown"
        decided.append((t + settle, text, decision))
        known = key
        corrected = False
    return decided


def check_observer() -> None:
    model = observer_model()
    min_length, checks, copies, good = model
    if good:
        ok("observer reads only, writes only the observer, uses r6-r8 and cr6")
    expected_copies = [(32, 4, 16), (72, 2, 20), (74, 2, 24), (76, 2, 28)]
    if copies == expected_copies:
        ok("observer copies VIDEO_MODE.video_vid +0x20 and AV_VIDEO_CS port/vid/cs_out +0x48/+0x4A/+0x4C")
    else:
        fail(f"observer copies {copies}, expected {expected_copies}")
    if min_length is None or min_length < max(o + w for o, w, _ in checks + copies):
        fail("observer length check does not cover every field it reads")
    else:
        ok(f"observer length check ({min_length:#x}) covers every field it reads")
    for name, path in CAPTURES.items():
        if not path.exists():
            print(f"note: capture {name} not available; observer not replayed on it")
            continue
        reports = []
        missed = []
        first_tb = None
        for _, seq, kind, tb, _, _, data, recorded_rewrite in read_records(path):
            first_tb = tb if first_tb is None else first_tb
            if kind != 1:
                continue
            # avtrace stores rgb_full batches already corrected, with a mark.
            corrected = matches(data) or recorded_rewrite != 0
            sent = rewrite(data, 1) if matches(data) else data
            report = observe(model, sent)
            if report is not None:
                reports.append(((tb - first_tb) / TIMEBASE_HZ, seq, report, corrected))
            elif has_video_mode(sent):
                missed.append(seq)
        if missed:
            fail(f"capture {name}: VIDEO_MODE batches not reported: {missed}")
        else:
            ok(f"capture {name}: all {len(reports)} VIDEO_MODE batches reported")
        texts = [(t, mode_text(r), (r[20], r[24], r[28]), c) for t, _, r, c in reports]
        decided = popups(texts)
        print(f"      reports: " + ", ".join(f"#{seq} {mode_text(r)}" for _, seq, r, _ in reports))
        print(f"      pop-ups: " + ", ".join(f"{t:.1f} s {text} ({d})" for t, text, d in decided))
        if name == "0002":
            dvd = [r for _, seq, r, _ in reports if seq == 365]
            if dvd and mode_text(dvd[0]) == "576i RGB":
                ok("capture 0002: DVD start (#365) is reported as sent after the fix, 576i RGB")
            else:
                fail("capture 0002: DVD start not reported as 576i RGB")
        if name == "0007":
            seqs = [(seq, mode_text(r)) for _, seq, r, _ in reports]
            want = [(21, "480i RGB"), (67, "576i RGB"), (213, "480i RGB")]
            if seqs == want:
                ok("capture 0007: observer reports 480i RGB -> 576i RGB -> 480i RGB")
            else:
                fail(f"capture 0007: reports {seqs}, expected {want}")
            shown = [(text, d) for _, text, d in decided]
            want = [("480i RGB", "skipped, DVD start"), ("576i RGB", "shown"), ("480i RGB", "shown")]
            if shown == want:
                ok("capture 0007: DVD-start 480i skipped; 576i RGB and exit 480i RGB shown")
            else:
                fail(f"capture 0007: pop-up decisions {shown}, expected {want}")


def check_names() -> None:
    text = SOURCE.read_text()
    body = re.search(r"g_av_vid_names\[\]\s*=\s*\{(.*?)\};", text, re.S).group(1)
    names = re.findall(r'"([^"]*)"', body)
    if names == [AV_VID[i] for i in range(len(AV_VID))]:
        ok(f"pop-up mode names equal the decoder AV_VID table ({len(names)} entries)")
    else:
        fail(f"pop-up mode names differ from decoder AV_VID: {names}")
    body = re.search(r"g_cs_names\[\]\s*=\s*\{(.*?)\};", text, re.S).group(1)
    if len(re.findall(r'"([^"]*)"', body)) == 3 and AV_CS[0] == "RGB8" and AV_CS[1] == "YUV444_8":
        ok("pop-up colour names cover RGB8, YUV444_8, YUV422_8")
    else:
        fail("pop-up colour names unexpected")


def main() -> int:
    check_signature()
    check_prx()
    check_disassembly()
    check_rule()
    check_unchanged_parts()
    check_observer()
    check_names()
    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
