# avtrace 0.2

A diagnostic plugin that records everything VSH sends to and receives from
the PS3 AV controller, on 4.92 CEX. It was used to find the cause of the
DVD component switch and to test the correction before it became
`disc_rgb_fix`.

By default it changes nothing that VSH sends or receives. An optional
marker file switches on a rewrite of the DVD-start batch:

| Marker in `/dev_hdd0/tmp/` | Effect | Tested |
| --- | --- | --- |
| none | Trace only | Yes (captures 0001, 0002) |
| `avtrace.rgb_full` | DVD-start batch set to the XMB RGB bytes (what `disc_rgb_fix` does) | Yes (capture 0003) |
| `avtrace.rgb_out` | Only the output colour space set to `RGB_8`, input left `YUV444_8` | No |

## What it hooks

| VSH address | Original | Change |
| --- | --- | --- |
| `0x005DED54` | first instruction of the send wrapper (syscall 369) | branch to a copy of the wrapper that records the batch before the syscall and the raw result after it |
| `0x005DBFA8` | `nop` after the only call to the receive wrapper (syscall 368) | `bl` to an observer that records non-empty replies; empty and failed results are only counted |

These are the only two syscall 368/369 sites in VSH, each with a single
caller. Both hooks are checked against the exact 4.92 bytes before
anything is written, and neither hook calls a function.

## Output

- `/dev_hdd0/tmp/avtrace.log`: status lines and a one-line summary per record.
- `/dev_hdd0/tmp/avtrace.bin`: complete records for `tools/decode_avtrace.py`.

## Loading

Never put this in `boot_plugins.txt`. Load it from the XMB through webMAN:

```text
http://<ps3-ip>/loadprx.ps3?prx=/dev_hdd0/tmp/avtrace.sprx
```

It waits 10 seconds, installs the hooks, and drains its ring buffer to
the files once a second. Remove it by rebooting.

If `/dev_hdd0/tmp/avtrace.disable` exists, it logs `DISABLED` and does
nothing. Test each new build that way first.

## Build

```sh
./build-docker.sh
```

The build runs `tools/verify_avtrace.py`, which checks the signatures
against the decrypted 4.92 VSH, the imports, the log strings, and the hook
disassembly.
