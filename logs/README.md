# Captures and test results

Recorded on a CECH-L04, 4.92 CEX, Cobra 8.5, webMAN MOD 1.47.48n, AV
MULTI to SCART RGB at 576i, with the same home-made DVD in 0001-0004.

`summary.txt` files are decoded with `avtrace/tools/decode_avtrace.py
--summary`: one line per video-related command, timestamps in seconds from
the start of the capture. HDCP event payloads (which identify the HDMI
display) are omitted. Captures 0001 and 0002 come from one continuous
session, so the 0002 summary also contains 0001.

| Capture | Plugin | What happened |
| --- | --- | --- |
| [0001](0001-xmb-rgb-ycbcr/RESULT.md) | avtrace 0.1 (trace only) | XMB output changes: AV MULTI RGB, HDMI, AV MULTI YCbCr. |
| [0002](0002-dvd-playback/RESULT.md) | avtrace 0.1 (trace only) | XMB RGB, then native DVD playback and exit. Picture went component. |
| [0003](0003-dvd-rgb-full/RESULT.md) | avtrace 0.2, rewrite on | Same DVD with the DVD-start batch corrected. Picture stayed RGB. |
| [0004](0004-boot-2.0/RESULT.md) | disc_rgb_fix 2.0 and 2.0.1 at boot | Boot tests with and without the disable marker; DVD stayed RGB. |
| [0005](0005-bluray/RESULT.md) | disc_rgb_fix 2.0.1 at boot | Blu-ray playback stayed RGB. |
