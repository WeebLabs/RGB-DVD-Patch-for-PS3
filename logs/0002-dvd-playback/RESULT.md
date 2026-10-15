# 0002: native DVD playback, trace only

Same session as 0001 (records from #130). The HDMI cable was unplugged at
about 507 s (two `EVENT_UNPLUGGED` replies).

| Time | Event | `video_out_format` | `AV_VIDEO_CS` output / input |
| --- | --- | --- | --- |
| 411.5 s | XMB, AV MULTI RGB 576i | 0 | `RGB_8` / `RGB_8` |
| 419.9 s | XMB, 576p selected by mistake | 0 | `RGB_8` / `RGB_8` |
| 451.0 s, 457.3 s | XMB, back to RGB 576i | 0 | `RGB_8` / `RGB_8` |
| **529.1 s** | **DVD playback starts** | **9** | **`YUV444_8` / `YUV444_8`** |
| 552.7 s | Exit to the XMB | 0 | `RGB_8` / `RGB_8` |

The picture on the RGB display went green at playback start and returned
at exit. All replies had status 0. No other `VIDEO_MODE` or `AV_VIDEO_CS`
command was sent during playback.

The DVD-start batch (#365) and the exit batch (#489) are both 116 bytes and
differ in exactly two 32-bit words:

| Offset | Field | Exit (#489) | DVD start (#365) |
| --- | --- | --- | --- |
| `+0x30` | `VIDEO_MODE.video_out_format` | `0x00000000` | `0x00000009` |
| `+0x4C` | `AV_VIDEO_CS` output / input colour space | `0x00000000` | `0x00010001` |

`sends.bin` holds every batch sent in this session (replies removed). The
build verifier uses it to confirm that the plugin's match rule selects
only batch #365, and that correcting it produces exactly batch #489.
