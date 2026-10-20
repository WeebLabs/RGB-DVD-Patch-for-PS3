# RGB DVD Patch for PS3

A PS3 VSH plugin that retains RGB output on the AV MULTI port during DVD and
Blu-ray playback using the PS3's native player.

Without it, the PS3 switches AV MULTI from RGB to component video (YPbPr)
whenever playback of a DVD or Blu-ray begins. On a SCART RGB display, the picture becomes 
green and purple. With this plugin, the output remains RGB, with correct 
colours for both the content itself and the on-screen menus.

The plugin also shows the video output mode, for example `576i RGB`, as a
pop-up whenever it changes. The PS3's player switches the output to the
disc's own standard, so a PAL DVD on a 480i system plays at 576i, and the
pop-up shows when that happens.

Feel free to join the [official Discord server](https://discord.gg/RCyqxAQ5xS)
for development updates, discussion or to request assistance!

## Requirements

- A PS3 running **Evilnat 4.92 CEX and Cobra 8.5**.
- Video output set to **AV MULTI / SCART, RGB**.
- A means of transferring files to the PS3's hard drive, such as webMAN MOD's FTP
  server or a file manager like multiMAN.

The plugin checks the exact 4.92 system code before changing anything. On
any other firmware it does nothing and writes an error to its log.

Tested on a CECH-L04 with webMAN MOD 1.47.48n, at 576i and at 480i
(including a PAL DVD on a 480i system). HDMI output is never affected.

## Installing

1. Download `disc_rgb_fix.sprx` from the
   [Releases](../../releases) page.
2. Copy it to `/dev_hdd0/plugins/` on the PS3.
3. Add this line to `/dev_hdd0/boot_plugins.txt` (create the file if it
   doesn't exist), on its own line below any other plugins:

   ```text
   /dev_hdd0/plugins/disc_rgb_fix.sprx
   ```

4. Reboot the PS3.

The plugin installs its hook 5 seconds after being loaded at boot. Nothing
changes in the XMB itself; only disc playback behaves differently.

## Checking that it works

Play a DVD or Blu-ray. The picture should remain RGB.

The plugin writes a log to `/dev_hdd0/tmp/disc_rgb_fix.log`. After a DVD
or Blu-ray begins, it should contain the lines below. The log reports
"DVD-start" for both Blu-ray and DVD; the correction is the same.

```text
READY: DVD-start AV MULTI batch will be kept RGB
REWRITE: DVD-start batch kept RGB; total 0x00000001
REWRITE: send result (0x74 = accepted) 0x00000074
```

## Output-mode pop-up

About 5 seconds after the output mode changes, a pop-up shows the new
mode, for example `576i RGB`. The plugin waits that long because the
picture is blanked while the mode switches, and because the XMB did not
show pop-ups sent sooner after leaving disc playback.

In every test so far, the player started in the mode the system was
already in, so there is no pop-up when playback starts. With a PAL DVD on a 480i system, a
`576i RGB` pop-up appears once the player has read the disc (about 14
seconds in), and a `480i RGB` pop-up appears after leaving playback.

Every change is also logged, whether or not a pop-up is shown:

```text
MODE: 576i RGB; video_vid 0x3 port 0x10 av_vid 0x5 cs_out 0x0 total 0x2
POPUP: 576i RGB; vshtask_notify returned 0x0
```

The system sometimes also sets up the HDMI port by itself. A pop-up such
as `480p RGB (HDMI)` then appears. It doesn't change the AV MULTI output.

## Turning it off

- **Temporarily:** create an empty file at
  `/dev_hdd0/tmp/disc_rgb_fix.disable` and reboot. The plugin loads but
  does nothing. Delete the file and reboot to turn it back on.
- **Pop-ups only:** create an empty file at
  `/dev_hdd0/tmp/disc_rgb_fix.nopopup` and reboot. The output stays RGB
  and mode changes are still logged, but no pop-ups appear.
- **Removing it:** delete the line from `/dev_hdd0/boot_plugins.txt`,
  reboot, and delete `/dev_hdd0/plugins/disc_rgb_fix.sprx`.

## If the PS3 won't boot

If the PS3 freezes during boot after you add any plugin:

1. Turn it fully off by holding the power button for 10 seconds.
2. Start Recovery Mode: hold the power button until you hear a second beep
   and the console turns off, then hold it again until you hear a quick
   double beep.
3. Connect a controller with a USB cable, press the PS button, and choose
   **Restart System**.

On Evilnat, this boots without plugins, but it also deletes
`boot_plugins.txt` and turns Cobra off. Turn Cobra back on (for example by
renaming `/dev_blind/sys/stage2.bin.bak` back to `stage2.bin`), then
recreate `boot_plugins.txt`.

## Building from source

Building needs the Sony Cell SDK, which is not included and not
distributed here. See [disc_rgb_fix/README.md](disc_rgb_fix/README.md).

## More detail

- [docs/how-it-works.md](docs/how-it-works.md) explains what the PS3
  changes when a disc starts, and what the plugin does about it.
- [avtrace](avtrace/) is the diagnostic plugin used to find the cause. It
  records the commands the system sends to the PS3's video hardware.
- [logs](logs/) holds the captures and test results the fix is based on.

## Licence

MIT. See [LICENSE](LICENSE).
