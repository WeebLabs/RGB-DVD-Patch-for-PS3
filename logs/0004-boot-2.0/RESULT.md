# 0004: disc_rgb_fix as a boot plugin

Boot list: webMAN MOD, then `/dev_hdd0/plugins/disc_rgb_fix.sprx`.
`disc_rgb_fix.log` is the plugin's log across these four boots.

| Build | Disable marker | Boot | DVD |
| --- | --- | --- | --- |
| 2.0 (20 s start delay) | present | Clean; log `DISABLED` | not tested |
| 2.0 | absent | Clean; hook installed, `READY` | Stayed RGB; one correction, send result `0x74` |
| 2.0.1 (5 s start delay) | present | Clean; log `DISABLED` | not tested |
| 2.0.1 | absent | Clean; hook installed, `READY` | Stayed RGB; one correction, send result `0x74` |
