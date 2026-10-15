# RGB DVD Patch for PS3

A PS3 plugin that keeps RGB output on the AV MULTI port during DVD playback
in the PS3's own (XMB) disc player.

Without it, the PS3 switches AV MULTI from RGB to component video (YPbPr)
whenever a DVD starts. On a SCART RGB display, such as a Sony PVM or an RGB
SCART TV, the picture then turns green and purple. With the plugin, the
picture stays RGB, with correct colours for both the movie and the
on-screen menus.

## Requirements

- A PS3 on **firmware 4.92 CEX** with custom firmware that includes
  **Cobra** (tested with Evilnat 4.92 and Cobra 8.5).
- Video output set to **AV MULTI / SCART, RGB**. Tested at 576i (PAL);
  480i (NTSC) has not been tested.
- A way to copy files to the PS3's hard drive, such as webMAN MOD's FTP
  server or a file manager like multiMAN.

The plugin checks the exact 4.92 system code before changing anything. On
any other firmware it does nothing and writes an error to its log.

Tested on a CECH-L04 with webMAN MOD 1.47.48n. HDMI output is never
affected.

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

The plugin installs its hook 5 seconds after it loads at boot. Nothing
changes in the XMB itself; only DVD playback behaves differently.

## Checking that it works

Play a DVD. The picture should stay RGB.

The plugin writes a log to `/dev_hdd0/tmp/disc_rgb_fix.log`. After a DVD
starts, it should contain:

```text
READY: DVD-start AV MULTI batch will be kept RGB
REWRITE: DVD-start batch kept RGB; total 0x00000001
REWRITE: send result (0x74 = accepted) 0x00000074
```

## Turning it off

- **Temporarily:** create an empty file at
  `/dev_hdd0/tmp/disc_rgb_fix.disable` and reboot. The plugin loads but
  does nothing. Delete the file and reboot to turn it back on.
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
  changes when a DVD starts, and what the plugin does about it.
- [avtrace](avtrace/) is the diagnostic plugin used to find the cause. It
  records the commands the system sends to the PS3's video hardware.
- [logs](logs/) holds the captures and test results the fix is based on.

## Licence

MIT. See [LICENSE](LICENSE).
