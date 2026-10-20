# 0008: output-mode pop-up (disc_rgb_fix 2.1.0 to 2.1.3)

Date: 2026-10-20. `tvSystem` = 0, XMB on AV MULTI 480i RGB, the PAL DVD
from 0007. Boot plugins: webMAN MOD 1.47.48n, then
`/dev_hdd0/plugins/disc_rgb_fix.sprx`. Each version was installed over
FTP, checked by reading it back, and loaded by restarting through webMAN.

| Version | SHA-256 of `disc_rgb_fix.sprx` | Pop-up delay | Log |
| --- | --- | --- | --- |
| 2.1.0 | `1a681a056ee41edec7c62342dd214003a7eb4402e83ecdfb3f71d125891374ad` | 1 s | `disc_rgb_fix-2.1.0.log` |
| 2.1.1 | `7cad1a7a152999186591e01fe78bc47eb81e4b87b3d8692d33a9332d1328348a` | 3 s | `disc_rgb_fix-2.1.1.log` (two DVD runs, then a second boot) |
| 2.1.2 | `2b51f20ed615bdc33c62d2cc01ce55f9f44616aa73fea5e14bc4665f4b2cf097` | 5 s | `disc_rgb_fix-2.1.2.log` |
| 2.1.3 | `aff98e5da5b8d0826ab1e9e645d51e7bfd37ffb1027903056b60d7a6f13b1ca1` | 5 s, unchanged modes skipped | `disc_rgb_fix-2.1.3.log` |

## Result

Every version booted cleanly and installed its hook, and the user reported
no picture problems. Each DVD run logged the same three mode changes as capture 0007 (480i at the
start, 576i once the player has read the disc, 480i at exit). Both start
batches, the 480i and the 576i one, were corrected (`REWRITE`, send result
`0x74`).

| Version | Start 480i | 576i | Exit 480i |
| --- | --- | --- | --- |
| 2.1.0 | seen | seen | **not seen**, `vshtask_notify` returned 0 |
| 2.1.1 | seen | seen | **not seen**, `vshtask_notify` returned 0 |
| 2.1.2 | seen | seen | seen |
| 2.1.3 | skipped (logged) | seen | seen |

A notification sent 1 s or 3 s after the exit switch was not drawn,
although the call succeeded; one sent after 5 s was. Why is not known.

2.1.3 skips the pop-up when the mode equals the last one, and when no mode
is known yet and the batch was a DVD-start correction. The start 480i is
the mode the XMB was already in, so it is no change.

## HDMI setups

After the 2.1.3 DVD run, the log shows two `480p RGB (HDMI)` setups (head
0, `video_vid` 0x5, port 0, `av_vid` 1) that the user did not ask for. The
first seemed to coincide with highlighting the Photo column of the XMB; a
later attempt to repeat that did not produce one, but the second appeared
during that attempt at 19:12:04 local time. No AV MULTI setup came with
either, so the RGB output was not affected. The trigger is not known.
