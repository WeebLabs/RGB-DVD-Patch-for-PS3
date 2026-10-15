# 0005: Blu-ray playback

disc_rgb_fix 2.0.1 as a boot plugin (same boot as the last 2.0.1 test in
0004). AV MULTI to SCART RGB at 576i.

Result (user test): native Blu-ray playback stayed RGB.

`disc_rgb_fix.log` shows the hook installed once and three corrections in
that boot, each accepted by the AV controller (send result `0x74`). The
first was the DVD test from 0004; the log does not record which disc
caused the others.

The plugin only corrects a batch that exactly matches the DVD-start batch
from capture 0002, so Blu-ray playback start sends that same batch. No
avtrace capture of Blu-ray was taken.
