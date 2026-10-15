# disc_rgb_fix 2.0.1

A VSH plugin that keeps a PS3's AV MULTI output electrically RGB during
native XMB DVD and Blu-ray playback, so a SCART RGB display (such as a PVM) keeps a
correct picture instead of receiving component video.

Tested on: CECH-L04, 4.92 CEX, Evilnat CFW with Cobra 8.5, webMAN MOD
1.47.48n, AV MULTI to SCART RGB at 576i.

## How it works

When native DVD playback starts, VSH sends the AV controller the same
command batch the XMB uses for AV MULTI RGB, except for two words:

| Batch offset | Field | XMB RGB | DVD playback |
| --- | --- | --- | --- |
| `+0x30` | `VIDEO_MODE.video_out_format` | `0` | `9` |
| `+0x4C` | `AV_VIDEO_CS` cs_out / cs_in | RGB8 / RGB8 | YUV444_8 / YUV444_8 |

YUV444 out on AV MULTI is a component signal. The plugin replaces the
VSH send wrapper (`0x005DED54`, syscall 369) with an identical copy that
sets exactly that batch back to the XMB RGB bytes before sending it. Every
other batch is passed through unchanged. The evidence is in
`../logs/0001-xmb-rgb-ycbcr`, `../logs/0002-dvd-playback`, and
`../logs/0003-dvd-rgb-full`.

The hook only fires on an exact match: `AVB_PARAM` containing
`VIDEO_MODE` (head 1, out_format 9) and `AV_VIDEO_CS` for AV MULTI with
YUV444_8 in and out. HDMI output is never touched.

## Installing

1. Copy `disc_rgb_fix.sprx` to `/dev_hdd0/plugins/`.
2. Add `/dev_hdd0/plugins/disc_rgb_fix.sprx` to `/dev_hdd0/boot_plugins.txt`.
3. Reboot.

The plugin waits 5 seconds after it loads before installing its hook.

## Log and disable switch

- Log: `/dev_hdd0/tmp/disc_rgb_fix.log`. Each corrected DVD or Blu-ray
  start logs a
  `REWRITE` line with the send result (`0x74` means the AV controller
  accepted the 116-byte batch).
- Disable without uninstalling: create `/dev_hdd0/tmp/disc_rgb_fix.disable`
  and reboot. The plugin then logs `DISABLED` and does nothing.
- If the console ever fails to boot: enter Recovery Mode and choose
  Restart System. On Evilnat, this skips the boot plugins (and turns Cobra
  off, which must then be turned back on).

## Firmware specificity

The plugin checks the exact 4.92 bytes of the send wrapper before writing
anything, and does nothing on any other firmware. Supporting another
firmware means finding the same wrapper there and repeating the captures
with `../avtrace`.

## Build

```sh
./build-docker.sh
```

This needs a Cell SDK, which is not included. The build runs
`tools/verify_disc_rgb_fix.py`, which checks the firmware signature, the
imports, the hook disassembly, and that the hook's batch checks are exactly
the rule replayed against the real DVD capture.
