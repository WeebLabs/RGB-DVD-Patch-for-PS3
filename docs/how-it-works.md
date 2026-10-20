# How it works

Everything here was observed on a CECH-L04 running 4.92 CEX with Cobra 8.5,
using the [avtrace](../avtrace/) plugin. The captures are in
[../logs](../logs/).

## What the PS3 sends to its video hardware

The system menu (VSH) configures the video output by sending command
batches to the AV controller through one function, the send wrapper at
`0x005DED54` (syscall 369). avtrace records every batch at that point.

Command and field names below come from the Linux kernel's PS3 AV driver
header (`arch/powerpc/include/asm/ps3av.h`). VSH also sends some command IDs
that Linux does not define; those are shown as raw numbers.

### XMB: RGB versus YCbCr (captures 0001 and 0002)

Selecting AV MULTI Y Pb/Cb Pr/Cr in the XMB's Video Output Settings (batch
#108) and selecting AV MULTI RGB at the same resolution (batch #193) send
116-byte batches that differ in exactly one 32-bit word:

| Setting | `AV_VIDEO_CS` output colour space | `AV_VIDEO_CS` input colour space |
| --- | --- | --- |
| RGB | `RGB_8` (0) | `RGB_8` (0) |
| Y Pb/Cb Pr/Cr | `YUV444_8` (1) | `RGB_8` (0) |

### Starting a DVD (capture 0002)

When native DVD playback starts, VSH sends the same 116-byte batch that it
sends for XMB RGB, except for two 32-bit words:

| Batch offset | Field | XMB RGB | DVD playback |
| --- | --- | --- | --- |
| `+0x30` | `VIDEO_MODE.video_out_format` | `0` | `9` |
| `+0x4C` | `AV_VIDEO_CS` output / input colour space | `RGB_8` / `RGB_8` | `YUV444_8` / `YUV444_8` |

The output colour space is the same value the XMB uses for Y Pb/Cb Pr/Cr,
so the AV MULTI port carries component video. No further `VIDEO_MODE` or
`AV_VIDEO_CS` command is sent during playback. Leaving playback sends the
XMB RGB batch again.

### PAL disc on a 480i system (capture 0007)

With the system set to 480i, VSH starts playback of a PAL DVD with the
DVD-start batch at 480i (720x480, batch #21). About 7.5 seconds later, once
the player has read the disc, it mutes the output and sends a complete new
setup at 576i (720x576, #67), in the same DVD-start form. Leaving playback
sends the XMB batch at 480i again (#213). So the player switches the output
to the disc's standard, even though the XMB does not offer 576i on that
system. When disc and system already match (capture 0002), there is only
the one batch at the start.

## What the plugin does

`disc_rgb_fix` replaces the send wrapper with an identical copy that checks
each batch before sending it. If a batch is exactly the DVD-start batch
above (an `AVB_PARAM` batch with `VIDEO_MODE` for head 1 with
`video_out_format` 9, and `AV_VIDEO_CS` for the AV MULTI port with
`YUV444_8` in and out), the plugin sets both words back to the XMB RGB
values. The batch it sends is then byte-identical to the XMB RGB batch.
Every other batch is sent unchanged.

Results (captures 0003 and 0004):

- The AV controller accepts the corrected batch (send result `0x74`, the
  full 116 bytes; reply status 0).
- The display stays RGB, and the movie and the XMB overlay both have
  correct colours.
- In about 28 minutes of playback, including opening the overlay, no
  further `VIDEO_MODE` or `AV_VIDEO_CS` command was sent.
- Leaving playback returns to the XMB normally.
- Blu-ray (test 0005): native Blu-ray playback also stays RGB. The plugin
  corrected the batch at playback start and the AV controller accepted it
  (`0x74`). The plugin only corrects a batch that exactly matches the one
  described above, so Blu-ray playback sends the same batch. It was not
  captured separately with avtrace.

## Output-mode pop-up (2.1)

Every output-mode change in the captures is one batch with the same
layout: `AVB_PARAM` with one `VIDEO_MODE` at `+0x10` and one `AV_VIDEO_CS`
at `+0x40`, and no audio packets. After the RGB correction, the hook checks
each batch for that layout and copies four fields into the plugin's
memory: `VIDEO_MODE.video_vid` (`+0x20`), and the `AV_VIDEO_CS` port,
`av_vid` and `av_cs_out` (`+0x48`, `+0x4A`, `+0x4C`). It then increments a
counter. It never changes the batch. The correction and send code are the
2.0.1 code.

The plugin's own thread checks the counter every 100 ms and logs each
change. Once the output has gone 5 seconds without a further change, it
shows the mode with `vshtask_notify` (module `vshtask`, NID `0xA02D46E7`),
the XMB notification webMAN MOD also uses. It skips the pop-up when the
mode equals the last one, and when no mode is known yet and the change was
a DVD-start correction. The plugin starts watching after the XMB has set
its mode, so the first DVD start has nothing to compare with.

On the console (test 0008), pop-ups sent 1 or 3 seconds after leaving
disc playback were not drawn, although `vshtask_notify` returned 0. Pop-ups
sent after 5 seconds were.

## Safety measures

- The plugin compares the 21 instructions of the 4.92 send wrapper with the
  running system before writing anything, and installs nothing if they
  differ.
- It changes one instruction in VSH (a branch at `0x005DED54`) and
  restores it if the plugin is stopped.
- The hook calls no functions. Its only system call is the original
  syscall 369. The pop-up is shown from the plugin's own thread, never
  from inside the hook.
- At boot it waits 5 seconds before installing, and afterwards only checks
  its own counters every 100 ms, to log corrections and mode changes.
- `/dev_hdd0/tmp/disc_rgb_fix.disable` turns it off at the next boot.
- `/dev_hdd0/tmp/disc_rgb_fix.nopopup` turns the pop-ups off at the next
  boot and keeps the RGB correction.
