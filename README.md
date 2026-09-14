# bigblackclocks

Two Logitech gaming keyboards, the **G510s** and the **G910 Orion
Spectrum** — same family, same era, same problem: nothing on Linux
actually drives their hardware properly. Logitech's own software
(G HUB / Logitech Gaming Software) is Windows-only, and the community
tools that exist for keyboards like these are old and unmaintained.

Here's the annoying bit: even back on Windows, proper software for the
G510s's little LCD screen was never easy to find — half of what's out
there is abandoned or just doesn't work right anymore. So when it came
to Linux, there was nothing at all. Bugger all. Same story with the
G910's per-key RGB lighting — no real Linux option, full stop.

So we sorted it ourselves. This repo talks to each keyboard's actual
hardware directly (real USB/HID traffic, not a guess at what "should"
work) and builds the control software from scratch — one app per
keyboard. The G510s app drives its LCD, buttons, backlight, and macro
keys. The G910 app drives its per-key RGB lighting and macro keys.
Different keyboards, different jobs, but the same rule for both:
nothing went in until it was actually tested and working on the real
keyboard, not just assumed to.

Both apps run as your normal user — no faffing about with root — start
themselves up at login, and just keep working through reboots,
replugs, and kernel updates. Does what it says on the tin.

## The two apps

| Keyboard | Branch | What it does |
| --- | --- | --- |
| **G510s** | `main` (this branch) | Lights up the LCD with live CPU/RAM/VRAM/temps, lets you build your own custom dashboards for the L2-L5 buttons (AIDA64 style), does the RGB backlight through a proper on-screen render of the keyboard (click a G-key to record a macro, M1/M2/M3/MR are real clickable bits of the picture), and handles G-key macros across M1-M3 profiles. Tagged `v1.0`; the canvas rework is built and self-tested but not yet confirmed by the user on the real keyboard. |
| **G910 Orion Spectrum** | [`g910-canvas`](../../tree/g910-canvas) | One tidy window built around a proper on-screen render of the keyboard — click any key to colour it, click a cluster to jump to that zone, and M1/M2/M3/MR are real clickable bits of the picture, not just labels. Handles G-key macros, saving/loading whole lighting setups, and won't get confused after a reboot (device paths are pinned down properly, not left to chance). Comes with its own installer and a desktop shortcut. Tagged `g910-v1.0` after a full bug-check pass — hasn't made its way to `main` yet, still on its own branch. |

### Screenshots

**G910 Control** — the app described above: the keyboard render sits in
the middle (click a key to colour it, click a cluster to pick its zone
in the sidebar, M1/M2/M3/MR are properly clickable), Colour Mode
sidebar on the left, G-Keys macro strip tucked under the keyboard, and
your saved lighting Profiles on the right.

![G910 Control app — v1](docs/screenshots/g910-control-v1.png)

**G510s Control** — the same idea, adapted to what this keyboard can
actually do: one sysfs LED for the whole board instead of per-key RGB,
so the keyboard render shows the real live backlight colour across the
main board, G-keys in their own accent colour (click one to record a
macro), and M1/M2/M3/MR shown above the G-key columns. Built and
self-tested 2026-09-14; not yet confirmed on the real hardware by the
user.

![G510s Control app — v1](docs/screenshots/g510s-control-v1.png)

A couple of other branches knocking about: `legacy-yad-backlight-script`
keeps the original yad/bash backlight script around for old times'
sake (the G510s app's Backlight tab does the job properly now), and
`g910` is what the G910 app looked like before the canvas rewrite —
left as-is for the history.

Want to actually run the G510s app? `./install.sh` sorts out every
dependency, drops the system files where they need to go, builds
everything, and switches the services on — the one thing it can't do
for you is track down your own copy of the Eurostile Bold font (that's
a licensing thing, not a laziness thing). The G910 app's got its own
installer, `install-g910.sh`, over on the `g910-canvas` branch.

---

## G510s: the short version

A PyQt5 app (`g510_app.py`) that turns the keyboard's built-in screen
into a live CPU/RAM/VRAM/TEMP display, with a dashboard builder for
the L2-L5 buttons if you fancy making your own layouts. Also does the
RGB backlight and G-key macros across M1-M3 profiles. Talks straight to
`/dev/g510-lcd` and `/dev/g510-keys` (proper stable symlinks, not
flaky device numbers) instead of relying on `g15daemon`, which gets
the key mappings wrong on this keyboard. Runs quietly as three systemd
`--user` services, starts itself at login, shrugs off reboots. Tagged
`v1.0`.

Want the full story — protocol details, every bug we hit and how it
got fixed, the font conversion faff, the udev rules? That's all in
[`G510_README.md`](G510_README.md). Just want to know how to actually
use the Custom Screens editor (add sensors, drag them around, resize
bars)? [`G510_CUSTOM_SCREENS_HOWTO.md`](G510_CUSTOM_SCREENS_HOWTO.md)
is the short version.
