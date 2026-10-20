# 0007: PAL DVD on a 480i (tvSystem = 0) system

Date: 2026-10-19. `tvSystem` = 0 (an xRegistry setting; with 0 the XMB
offers 480i instead of 576i), XMB on AV MULTI 480i.
disc_rgb_fix disabled by marker for this boot; avtrace 0.2 loaded through
webMAN (slot 3) with `rgb_full`, so the picture stayed RGB.

## Result

The native player switched the output to the disc's standard by itself:

| Time | Event | Mode |
| --- | --- | --- |
| 1.2-1.6 s | mute, route, `VIDEO_MODE` + `AV_VIDEO_CS` (#21, corrected to RGB) | 480i, 720x480 |
| 8.6-9.1 s | mute again, full new setup (#67, corrected to RGB) | **576i, 720x576** |
| 11 s on | copy control (0x00030003 = 0x0408), 0x00030004 every 5 s | playback |
| 58.8 s | exit to XMB (#213) | 480i |

All replies status 0. 576i was used although the XMB did not offer it with
`tvSystem` = 0.

## Conclusion

The player reconfigures the output to match the disc once it has read it.
This corrects the earlier assumption (from 0002, where disc and system
already matched) that the player keeps the system mode. The reverse case
(NTSC disc on a 576i system) is not yet tested.

`sends.bin` holds the send records of the capture, for
`disc_rgb_fix/tools/verify_disc_rgb_fix.py`.
