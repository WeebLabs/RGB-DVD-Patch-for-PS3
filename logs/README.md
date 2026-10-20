# Captures and test results

Recorded on a CECH-L04, 4.92 CEX, Cobra 8.5, webMAN MOD 1.47.48n, AV
MULTI to SCART RGB at 576i, with the same home-made DVD in 0001-0004. 0007
and 0008 use a 480i system and a PAL DVD.

`summary.txt` files are decoded with `avtrace/tools/decode_avtrace.py
--summary`: one line per video-related command, timestamps in seconds from
the start of the capture. HDCP event payloads (which identify the HDMI
display) are omitted. Captures 0001 and 0002 come from one continuous
session, so the 0002 summary also contains 0001. `sends.bin` files hold
only the send records of a capture (no replies or HDMI event payloads), for
`disc_rgb_fix/tools/verify_disc_rgb_fix.py`.

| Capture | Plugin | What happened |
| --- | --- | --- |
| [0001](0001-xmb-rgb-ycbcr/RESULT.md) | avtrace 0.1 (trace only) | XMB output changes: AV MULTI RGB, HDMI, AV MULTI YCbCr. |
| [0002](0002-dvd-playback/RESULT.md) | avtrace 0.1 (trace only) | XMB RGB, then native DVD playback and exit. Picture went component. |
| [0003](0003-dvd-rgb-full/RESULT.md) | avtrace 0.2, rewrite on | Same DVD with the DVD-start batch corrected. Picture stayed RGB. |
| [0004](0004-boot-2.0/RESULT.md) | disc_rgb_fix 2.0 and 2.0.1 at boot | Boot tests with and without the disable marker; DVD stayed RGB. |
| [0005](0005-bluray/RESULT.md) | disc_rgb_fix 2.0.1 at boot | Blu-ray playback stayed RGB. |
| [0007](0007-pal-dvd-on-480i/RESULT.md) | avtrace 0.2, rewrite on | PAL DVD on a 480i system: the player switched to 576i once it read the disc, and back to 480i at exit. |
| [0008](0008-mode-popup/RESULT.md) | disc_rgb_fix 2.1.0 to 2.1.3 at boot | Output-mode pop-up. The exit pop-up needs a 5 s delay; 2.1.3 skips unchanged modes. |
