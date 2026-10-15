#!/usr/bin/env python3
"""Decode avtrace.bin into a readable list of PS3AV batches and replies.

Usage: decode_avtrace.py avtrace.bin [--summary]

--summary prints one line per video-related command with named fields.

Each record is a send (VSH -> AV controller, syscall 369) or a receive
(AV controller -> VSH, syscall 368).  Batches are split into packets using
the PS3AV header: u16 version, u16 size (bytes after this word), u32 cid.
Replies carry a u32 status after the cid.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

TIMEBASE_HZ = 79_800_000
MAGIC = b"AVTRACE1"

# Names from Linux arch/powerpc/include/asm/ps3av.h only.  VSH also sends
# CIDs that Linux does not define (0x00030001, 0x00030003, 0x00030004,
# 0x01000003); those are printed as raw numbers.
CID_NAMES = {
    0x00000001: "AV_INIT",
    0x00000002: "AV_FIN",
    0x00000003: "AV_GET_HW_CONF",
    0x00000004: "AV_GET_MONITOR_INFO",
    0x00000006: "AV_ENABLE_EVENT",
    0x00000007: "AV_DISABLE_EVENT",
    0x0000000A: "AV_TV_MUTE",
    0x00010001: "AV_VIDEO_CS",
    0x00010002: "AV_VIDEO_MUTE",
    0x00010003: "AV_VIDEO_DISABLE_SIG",
    0x00020001: "AV_AUDIO_PARAM",
    0x00020002: "AV_AUDIO_MUTE",
    0x00040001: "AV_HDMI_MODE",
    0x01000001: "VIDEO_INIT",
    0x01000002: "VIDEO_MODE",
    0x01000004: "VIDEO_FORMAT",
    0x01000005: "VIDEO_PITCH",
    0x02000001: "AUDIO_INIT",
    0x02000002: "AUDIO_MODE",
    0x02000003: "AUDIO_MUTE",
    0x02000004: "AUDIO_ACTIVE",
    0x02000005: "AUDIO_INACTIVE",
    0x02000006: "AUDIO_SPDIF_BIT",
    0x02000007: "AUDIO_CTRL",
    0x04000001: "AVB_PARAM",
    0x10000001: "EVENT_UNPLUGGED",
    0x10000002: "EVENT_PLUGGED",
    0x10000003: "EVENT_HDCP_DONE",
    0x10000004: "EVENT_HDCP_FAIL",
    0x10000005: "EVENT_HDCP_AUTH",
    0x10000006: "EVENT_HDCP_ERROR",
}


def cid_name(cid: int) -> str:
    name = CID_NAMES.get(cid & 0x7FFFFFFF)
    return name if name else f"cid {cid:#010x}"


def hexwords(data: bytes) -> str:
    words = [data[i:i + 4].hex() for i in range(0, len(data), 4)]
    return " ".join(words)


def split_packets(data: bytes):
    offset = 0
    while offset + 8 <= len(data):
        version, size = struct.unpack_from(">HH", data, offset)
        cid = struct.unpack_from(">I", data, offset + 4)[0]
        end = offset + 4 + size
        if size < 4 or end > len(data):
            yield offset, None, data[offset:]
            return
        yield offset, (version, size, cid), data[offset:end]
        offset = end
    if offset < len(data):
        yield offset, None, data[offset:]


def print_packets(data: bytes, kind: int, indent: str) -> None:
    for packet_offset, header, packet in split_packets(data):
        if header is None:
            print(f"{indent}+{packet_offset:04x} unparsed: {hexwords(packet)}")
            continue
        version, size, cid = header
        line = f"{indent}+{packet_offset:04x} {cid_name(cid):22s} v{version:04x} size {size:3d}"
        if kind == 2 and size >= 8:
            line += f" status {struct.unpack_from('>I', packet, 8)[0]:#010x}"
        print(line)
        if kind == 1 and cid == 0x04000001 and size >= 12:
            # Linux ps3av_pkt_avb_param: four u16 counts, then nested packets.
            counts = struct.unpack_from(">HHHH", packet, 8)
            print(f"{indent}       counts video={counts[0]} audio={counts[1]} "
                  f"av_video={counts[2]} av_audio={counts[3]}")
            print_packets(packet[16:], kind, indent + "    ")
        else:
            print(f"{indent}       {hexwords(packet[8:])}")


AV_PORTS = {0x0000: "HDMI0", 0x0001: "HDMI1", 0x0010: "AVMULTI", 0x0020: "SPDIF0", 0x0021: "SPDIF1"}
AV_VID = {0: "480i", 1: "480p", 2: "720p60", 3: "1080i60", 4: "1080p60", 5: "576i",
          6: "576p", 7: "720p50", 8: "1080i50", 9: "1080p50", 10: "WXGA", 11: "SXGA", 12: "WUXGA"}
AV_CS = {0: "RGB8", 1: "YUV444_8", 2: "YUV422_8", 3: "XVYCC8", 4: "RGB10", 5: "YUV444_10",
         6: "YUV422_10", 7: "XVYCC10", 8: "RGB12", 9: "YUV444_12", 10: "YUV422_12", 11: "XVYCC12"}
VIDEO_CIDS = {0x0000000A, 0x00010001, 0x00010002, 0x00010003, 0x00030001, 0x00030003,
              0x00030004, 0x00040001, 0x01000001, 0x01000002, 0x01000003, 0x01000004}


def port_name(value: int) -> str:
    return AV_PORTS.get(value, f"port{value:#06x}")


def describe(cid: int, body: bytes) -> str:
    words = [struct.unpack_from(">I", body, i)[0] for i in range(0, len(body) - 3, 4)]
    halves = [struct.unpack_from(">H", body, i)[0] for i in range(0, len(body) - 1, 2)]
    if cid == 0x00010001 and len(halves) >= 4:
        port, vid, cs_out, cs_in = halves[:4]
        return (f"{port_name(port)} vid={AV_VID.get(vid, vid)} "
                f"cs_out={AV_CS.get(cs_out, cs_out)} cs_in={AV_CS.get(cs_in, cs_in)} "
                f"tail={hexwords(body[8:])}")
    if cid == 0x01000002 and len(words) >= 5:
        return (f"head={words[0]} words={hexwords(body[4:12])} "
                f"{words[3]}x{words[4]} rest={hexwords(body[20:])}")
    if cid in (0x0000000A, 0x00010002, 0x00010003) and halves:
        return f"{port_name(halves[0])} value={hexwords(body[2:])}"
    return hexwords(body)


def summary_lines(data: bytes, kind: int):
    for _, header, packet in split_packets(data):
        if header is None:
            continue
        _, size, cid = header
        if kind == 1 and cid == 0x04000001 and size >= 12:
            yield from summary_lines(packet[16:], kind)
            continue
        if kind == 1 and cid in VIDEO_CIDS:
            yield f"{cid_name(cid):20s} {describe(cid, packet[8:])}"
        elif kind == 2 and (cid & 0xF0000000) == 0x10000000:
            yield f"{cid_name(cid):20s} (event) {hexwords(packet[8:])}"
        elif kind == 2 and size >= 8:
            status = struct.unpack_from(">I", packet, 8)[0]
            if status != 0 and cid != 0x01000003:
                yield f"{cid_name(cid):20s} REPLY STATUS {status:#010x}"


def read_records(path: Path):
    blob = path.read_bytes()
    offset = 0
    session = 0
    while offset < len(blob):
        if blob[offset:offset + 8] == MAGIC:
            session += 1
            offset += 16
            continue
        if offset + 32 > len(blob):
            break
        seq, kind, timebase, requested, result, copied, rewrite = struct.unpack_from(
            ">IIQIIII", blob, offset)
        data = blob[offset + 32:offset + 32 + copied]
        offset += 32 + ((copied + 3) & ~3)
        yield session, seq, kind, timebase, requested, result, data, rewrite


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    summary = "--summary" in sys.argv[2:]
    first_tb = None
    last_session = None

    for session, seq, kind, tb, requested, result, data, rewrite in read_records(Path(sys.argv[1])):
        if session != last_session:
            print(f"==== session {session} ====")
            last_session = session
            first_tb = tb
        t = (tb - first_tb) / TIMEBASE_HZ
        signed = struct.unpack(">i", struct.pack(">I", result))[0]
        mark = f" REWRITTEN(mode {rewrite})" if rewrite else ""
        if summary:
            for line in summary_lines(data, kind):
                print(f"[{t:9.4f}] #{seq:<5} {'SEND' if kind == 1 else 'RECV'}{mark} {line}")
            continue
        if kind == 1:
            status = "ok" if signed == requested else f"MISMATCH result={signed}"
            print(f"[{t:9.4f}] #{seq:<5} SEND {requested:4d} bytes  ({status}){mark}")
        else:
            print(f"[{t:9.4f}] #{seq:<5} RECV {signed:4d} bytes")
        print_packets(data, kind, "           ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
