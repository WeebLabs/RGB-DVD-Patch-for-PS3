# 0003: DVD playback with the correction (avtrace 0.2)

avtrace 0.2 loaded at runtime through webMAN, with the rewrite switched on.
HDMI unplugged, XMB on AV MULTI RGB 576i, same DVD as 0002.

Result: the picture stayed RGB through playback start, and both the movie
and the XMB overlay had correct colours.

Trace:

- Batch #21 was the DVD-start batch. It was corrected once and sent with
  `video_out_format` 0 and `AV_VIDEO_CS` `RGB_8` / `RGB_8`, byte-identical
  to the XMB RGB batch.
- The send was accepted in full, and the reply (#22) had status 0.
- No other batch was changed. No further `VIDEO_MODE` or `AV_VIDEO_CS` was
  sent in about 28 minutes of playback, including opening the overlay.
- Exit at about 1762 s (#855) sent the normal XMB RGB batch, uncorrected,
  with every reply status 0.

`sends.bin` holds the send records of the capture, for
`disc_rgb_fix/tools/verify_disc_rgb_fix.py`.
