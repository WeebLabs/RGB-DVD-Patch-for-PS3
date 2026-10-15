# 0001: XMB output changes

In the XMB's Video Output Settings, in this order: AV MULTI RGB, then HDMI,
then AV MULTI Y Pb/Cb Pr/Cr. The HDMI cable was connected.

129 records (64 batches sent, 65 replies), none dropped. Every batch was
accepted in full.

| Time | Port | `VIDEO_MODE` | `AV_VIDEO_CS` output / input |
| --- | --- | --- | --- |
| 6.4 s | AV MULTI | head 1, 720x576, `video_out_format` 0 | 576i, `RGB_8` / `RGB_8` |
| 29.6 s | HDMI | head 0, 1920x1080 | 1080p60, `RGB_8` / `RGB_8` |
| 50.9 s | AV MULTI | head 1, 720x576, `video_out_format` 0 | 576i, `YUV444_8` / `RGB_8` |

The YCbCr batch (#108) and a later XMB RGB batch at the same resolution
(#193, in the 0002 summary) differ in exactly one 32-bit word: `+0x4C`,
the `AV_VIDEO_CS` output colour space.
