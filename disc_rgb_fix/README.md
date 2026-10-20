# disc_rgb_fix 2.1.3

A VSH plugin that keeps a PS3's AV MULTI output electrically RGB during
native XMB DVD and Blu-ray playback, so a SCART RGB display (such as a PVM) keeps a
correct picture instead of receiving component video. Since 2.1.0 it also
shows the new output mode, for example `576i RGB`, as an XMB notification
whenever VSH changes it.

Tested on: CECH-L04, 4.92 CEX, Evilnat CFW with Cobra 8.5, webMAN MOD
1.47.48n, AV MULTI to SCART RGB at 576i (2.0.1) and 480i (2.1.2, 2.1.3).

**Hardware status.** 2.1.3 passed the console test below on 2026-10-20
with a PAL DVD on the 480i setup. The log shows the DVD-start `480i RGB`
pop-up skipped (`skipped, DVD start in the current mode`), and `576i RGB`
and the exit `480i RGB` shown, and both corrections accepted (`0x74`).
After that run, the log also has an HDMI mode change,
`480p RGB (HDMI)`, with its pop-up shown. Before 2.1.3, 2.1.2 passed the
same test: playback stayed RGB, and the `480i RGB`, `576i RGB` and exit
`480i RGB` pop-ups all appeared. Only this one setup has been tested.

2.1.0 and 2.1.1 ran on the same setup first. DVD playback stayed RGB, and
every mode change was logged. The `480i RGB` and `576i RGB` pop-ups at the
start were visible, but the `480i RGB` pop-up on leaving playback was not,
although the log shows `vshtask_notify` returned 0 for it. 2.1.0 sent the
pop-up 1 s after the switch and 2.1.1 sent it after 3 s. 2.1.2 waits 5 s
and changes nothing else, and the exit pop-up then appeared. Why a
notification sent 3 s after that switch is dropped is not known; the 5 s
delay was found by trying it.

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

## Output-mode pop-up (2.1.0 to 2.1.3)

The native DVD player switches the output to the disc's own standard. On a
480i system, a PAL disc goes to 576i about 7.5 s after it starts and back
to 480i when playback ends (`../logs/0007-pal-dvd-on-480i`). The pop-up
makes each switch visible.

Every output-mode change VSH makes is one batch with a fixed layout, seen
in all captures (0001, 0002, 0003 and 0007): `AVB_PARAM` with one
`VIDEO_MODE` at `+0x10` and one `AV_VIDEO_CS` at `+0x40`. After the RGB
correction, the hook checks for that layout in every batch and copies four
fields into the plugin's memory, without changing the batch:

| Batch offset | Field | Example (PAL DVD) |
| --- | --- | --- |
| `+0x20` | `VIDEO_MODE.video_vid` | `0x3` |
| `+0x48` | `AV_VIDEO_CS` port | `0x10` (AV MULTI) |
| `+0x4A` | `AV_VIDEO_CS` av_vid | `5` (576i) |
| `+0x4C` | `AV_VIDEO_CS` av_cs_out | `0` (RGB8) |

It then increments a counter. The copy code calls nothing and adds no
syscall, and the RGB correction code is the 2.0.1 code unchanged.

The worker thread now checks the counters every 100 ms instead of every
second. When the mode counter changes, it logs a `MODE` line at once. It
shows the pop-up after 5 s without a further change (1 s in 2.1.0, 3 s in
2.1.1). The output is muted while it switches, and on leaving DVD playback
the XMB did not show a notification sent 1 s or 3 s after the switch, but
did show one sent after 5 s. The text is the `av_vid` name and the colour
space, for example `576i RGB`, with ` (HDMI)` added for HDMI. The pop-up is
`vshtask_notify` (module `vshtask`, NID `0xA02D46E7`), the function webMAN
MOD uses for its own notifications. The import stub
`lib/libvshtask_export_stub.a` is webMAN MOD's `lib/` file. If it is
missing, `build-docker.sh` downloads it from a pinned webMAN MOD commit
and checks its SHA-256 before building.

Since 2.1.3, the pop-up only appears when the mode actually changes. The
player always starts in the system's current mode (captures 0002 and
0007), and VSH re-sends that mode in full, so 2.1.2 showed a `480i RGB`
pop-up at every DVD start on a 480i system. When the wait ends, the worker
now skips the pop-up in two cases:

- the port, resolution and colour space equal the last mode it decided
  on, whether shown or skipped;
- no mode has been seen since boot, and a DVD-start correction (`REWRITE`)
  happened during the wait. The plugin starts watching only after the
  XMB has set its mode, so the first DVD start has nothing to compare
  with.

A skipped pop-up is still logged, as a `POPUP` line ending in `skipped`.
The second rule cannot be based on the correction alone. The player's
576i setup is corrected too, and its pop-up must still appear.

The pop-up also appears for mode changes outside DVD playback, such as
changing the resolution or RGB/Y Pb/Cb Pr/Cr in Video Output Settings, or
Blu-ray playback. Replaying the captures through the verifier's model of
the hook and the worker gives these decisions for capture 0007:

| Time | Batch | Pop-up |
| --- | --- | --- |
| 6.6 s | #21, player start | `480i RGB` skipped (DVD start, no earlier mode) |
| 14.1 s | #67, player switches to the disc's standard | `576i RGB` shown |
| 63.8 s | #213, back to the XMB (XMB display set up at 60.6 s) | `480i RGB` shown |

In captures 0002 and 0003, where the disc matched the system, the DVD
start and exit pop-ups are all skipped, because nothing changed.

### Risks

- The notification does appear over native DVD playback (the `576i RGB`
  pop-up, about 14 s in). Right after leaving playback, the XMB dropped
  notifications sent 1 s and 3 s after the switch, for an unknown reason.
  If a pop-up is ever missing, the `MODE` and `POPUP` lines in the log
  still record each change. A fallback would be to draw the text directly
  by hooking the player's frame flip, as webMAN MOD's
  `_Projects_/VshFpsCounter` does. That is a much larger change.
- The pop-up is shown from the plugin's own thread, not from inside the
  send hook, so a problem in `vshtask_notify` cannot block an AV send. A
  crash in it would still take VSH down. To keep the RGB fix but turn the
  pop-ups off, create `/dev_hdd0/tmp/disc_rgb_fix.nopopup` and reboot.
- 2.1.0 was the first version to import from a VSH module (`vshtask`).
  On the console that import resolved, and the plugin loaded as a boot
  plugin. A log without the `starting` line would mean it did not, which
  would also turn the RGB fix off.
- A batch with a different layout, for example one that also carries audio
  packets, is not reported. No capture contains one. The verifier checks
  that every batch with a `VIDEO_MODE` in the four captures is reported.

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
- Each output-mode change logs a line such as
  `MODE: 576i RGB; video_vid 0x3 port 0x10 av_vid 0x5 cs_out 0x0 total 0x2`.
  Each pop-up logs `POPUP: 576i RGB; vshtask_notify returned 0x0` (the
  return value is logged as it comes back; its meaning is not documented).
  A skipped one logs `POPUP: 480i RGB; skipped, same mode as before` or
  `POPUP: 480i RGB; skipped, DVD start in the current mode`.
- Disable without uninstalling: create `/dev_hdd0/tmp/disc_rgb_fix.disable`
  and reboot. The plugin then logs `DISABLED` and does nothing.
- Pop-ups off, RGB fix on: create `/dev_hdd0/tmp/disc_rgb_fix.nopopup` and
  reboot. Mode changes are still logged.
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
the rule replayed against the real DVD capture. Since 2.1.0 it also checks
that:

- the only new import is `vshtask` NID `0xA02D46E7`;
- the RGB correction and send code equal the 2.0.1 hook (tag `v2.0.1`)
  apart from one renamed branch target;
- the mode observer only reads the batch, writes only the plugin's
  observer, and uses only scratch registers;
- replaying captures 0002 (which contains 0001), 0003 and 0007 reports
  every batch with a `VIDEO_MODE`, the DVD start in 0002 as `576i RGB` after correction, and
  `480i RGB`, `576i RGB`, `480i RGB` for 0007;
- the pop-up mode names equal the `AV_VID` table in
  `../avtrace/tools/decode_avtrace.py`.

## Console test plan for 2.1.3

Setup, as in `../logs/0007-pal-dvd-on-480i`: `tvSystem` = 0, the XMB on AV
MULTI 480i RGB, and a PAL DVD. Keep 2.0.1 on the console so it can be put
back.

1. Copy the 2.1.3 `disc_rgb_fix.sprx` over the installed file in
   `/dev_hdd0/plugins/`. `boot_plugins.txt` stays the same. Delete or
   rename the old `/dev_hdd0/tmp/disc_rgb_fix.log`, and make sure neither
   `disc_rgb_fix.disable` nor `disc_rgb_fix.nopopup` exists.
2. Reboot. Expect a normal XMB. The log should start with
   `disc_rgb_fix 2.1.3 starting` and reach both `READY` lines.
3. Start the PAL DVD. Expect no pop-up at the start, then a `576i RGB`
   pop-up about 5 s after the output switches to 576i (about 14 s after the
   start). The picture must stay RGB throughout,
   as with 2.0.1.
4. Leave playback and return to the XMB. Expect a `480i RGB` pop-up about
   5 s after the switch. This is the pop-up 2.1.0 and 2.1.1 did not show.
5. Start the DVD a second time and leave again. Expect the same: no pop-up
   at the start (now `skipped, same mode as before`), then `576i RGB`, and
   `480i RGB` after leaving.
6. Copy the log to `../logs/NNNN-.../`. Per run, expect two `REWRITE`
   pairs (the start and the 576i setup are both corrected), three `MODE`
   lines, and three `POPUP` lines: one skipped and two shown.

Record which pop-ups were visible on screen. If the log has the `POPUP`
lines but the screen showed nothing during playback, the notification does
not draw over the DVD player, and the frame-flip overlay above is the next
step. If the console freezes or VSH crashes, use Recovery Mode as described
above and put 2.0.1 back.
