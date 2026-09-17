# bigblackclocks

A Logitech G510s keyboard Windows abandoned and Linux never supported,
driven properly from scratch: LCD screen, backlight, and G-key macros.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3-blue.svg)
![Platform: Arch Linux](https://img.shields.io/badge/platform-Arch%20Linux-1793d1.svg)
![G510s: work in progress](https://img.shields.io/badge/G510s-work%20in%20progress-orange.svg)

## Status, plainly

- **This repo is private.** Not indexed, not fetchable by anyone
  without an invite.
- **Work in progress** (see the table below) — not tagged beyond
  `v1.0`, not packaged for real installs beyond local testing, no
  live-hardware confirmation yet on everything past `v1.0`.
- Not pushed to the real AUR yet — its package still points at this
  private repo, which the AUR can never fetch from.

## Not the repo you're after?

This repo used to also contain a separate app for the Logitech G910
Orion Spectrum (per-key RGB/macros) — a different keyboard, different
codebase, developed alongside this one for a while. That app has been
fully moved out: its source, docs, install script, packaging, and
entire dev history now live in their own standalone public repo,
[grumpybollocks/g910-control](https://github.com/grumpybollocks/g910-control).
Nothing G910-related remains here, in any branch or tag, as of
2026-09-17 — if you're looking for that, it's over there.

The Logitech G510s — same family, same era as the G910, same problem:
nothing on Linux actually drives its hardware properly. Logitech's own
software (G HUB / Logitech Gaming Software) is Windows-only, and the
community tools that exist for a keyboard like this are old and
unmaintained.

Here's the annoying bit: even back on Windows, proper software for the
G510s's little LCD screen was never easy to find — half of what's out
there is abandoned or just doesn't work right anymore. So when it came
to Linux, there was nothing at all. Bugger all.

So we sorted it ourselves. This repo talks to the keyboard's actual
hardware directly (real USB/HID traffic, not a guess at what "should"
work) and builds the control software from scratch. It drives the LCD,
buttons, backlight, and macro keys. Nothing went in until it was
actually tested and working on the real keyboard, not just assumed to.

The app runs as your normal user — no faffing about with root — starts
itself up at login, and just keeps working through reboots, replugs,
and kernel updates. Does what it says on the tin.

## The app

| Keyboard | Branch | What it does |
| --- | --- | --- |
| **G510s** | `main` (`v1.0`) / **`g510s-dev`** (active work) | **Work in progress** — `main` has the tagged, confirmed `v1.0` (LCD stats, backlight, G-key macros). Everything since has been built and self-tested (including several rounds of self-audit bug-fixing) on `g510s-dev`, not merged here yet: the Custom Screens dashboard builder for L2-L5 (drag sensors, PNG images, and freeform text onto a live preview, resizable images, per-element text sizing), a live analog clock on L1, the Backlight + G-Keys canvas rearchitecture, a real Arch package (`packaging/g510-lcd/`), and a full split of your own data (screens/macros/images) into `~/.local/share/g510-lcd`, independent of wherever the app itself is installed from. Nothing on `g510s-dev` gets tagged or merged until it's physically confirmed on the real keyboard — that's this project's standing rule, not a delay. |

### Screenshot

**G510s Control** — the keyboard render shows the real live backlight
colour across the main board, G-keys in their own accent colour (click
one to record a macro), and M1/M2/M3/MR shown above the G-key columns.
Built and self-tested 2026-09-14; not yet confirmed on the real
hardware by the user.

![G510s Control app — v1](docs/screenshots/g510s-control-v1.png)

Active development happens on `g510s-dev` and gets merged back into
`main` once a feature is actually done — see
[`BRANCHES.md`](BRANCHES.md) for the full map of every branch and tag
in this repo, including the frozen historical `legacy-yad-backlight-script`
(the original yad/bash backlight script, kept for old times' sake — the
app's Backlight tab does the job properly now).

Want to actually run it? `./install.sh` sorts out every dependency,
drops the system files where they need to go, builds everything, and
switches the services on — the one thing it can't do for you is track
down your own copy of the Eurostile Bold font (that's a licensing
thing, not a laziness thing). A real Arch package also exists
(`packaging/g510-lcd/` on `g510s-dev`) — built and its contents
verified via `makepkg`, not yet actually installed on real hardware
(that's a manual `sudo pacman -U` step away, deliberately not run
automatically).

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

Wondering whether this actually works for anyone other than us, not
just on our own machines? [`READY_FOR_ANYONE.md`](READY_FOR_ANYONE.md)
covers that directly.

---

## The cheeky bits

A few things that happened along the way worth a mention, because
they're the kind of detail that makes a "personal project" actually
personal:

- The app can show free space on a second drive over its LCD like any
  other sensor, on request — fully optional, shows "N/A" gracefully on
  any setup that doesn't have one.
- This app was originally built and developed alongside a sibling app
  for the Logitech G910 (see "Not the repo you're after?" above) —
  two separate Claude Code sessions, one per keyboard, each on its own
  machine, coordinating over actual messages to each other, catching
  each other's mistakes and occasionally getting confused by each
  other's shorthand ("Plan A/B" turned out to be a mishearing of
  "Phase A/B"). That history predates the split and lives on in this
  repo's own commit log even though the G910 app's files themselves
  have moved on.
- "wtf are the blue squares for?" is a genuine, verbatim piece of user
  feedback that shipped an actual UI fix (resize handles now only show
  up when you're hovering near them, not all at once) — which is as
  good a reminder as any that real usage beats guessing every time.

---

## License

[MIT](LICENSE).
