# bigblackclocks

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3-blue.svg)
![Platform: Arch Linux](https://img.shields.io/badge/platform-Arch%20Linux-1793d1.svg)
![G510s: work in progress](https://img.shields.io/badge/G510s-work%20in%20progress-orange.svg)

**A from-scratch Linux driver + GUI for the Logitech G510s** — the LCD
screen, backlight, and G-key macros, properly working. Logitech's own
software is Windows-only and everything else out there is old,
abandoned, or half-broken, so this talks to the keyboard's real
USB/HID traffic directly instead.

## Quickstart

```
./install.sh
```

Sorts out every dependency, builds the LCD driver, wires up the
systemd services, and adds desktop shortcuts. The one thing it can't
do for you: your own copy of the Eurostile Bold font (a licensing
thing — see [`G510_README.md`](G510_README.md)'s FONTS section).

**What you get:**
- Live CPU / RAM / VRAM / TEMP stats on the built-in LCD
- Full RGB backlight colour control
- G-key macros across M1 / M2 / M3 profiles
- Custom Screens dashboard builder — drag sensors, images, and text
  onto L2-L5 (on `g510s-dev`, not merged to `main` yet)
- Runs as your normal user, starts at login, shrugs off reboots —
  no root faffing about

![G510s Control app — v1](docs/screenshots/g510s-control-v1.png)

## How it works

A PyQt5 app (`g510_app.py`) talks straight to `/dev/g510-lcd` and
`/dev/g510-keys` — proper stable symlinks, not flaky device numbers —
instead of relying on `g15daemon`, which gets this keyboard's key
mappings wrong. Runs quietly as three systemd `--user` services.

## Status

- **Meant to be private, isn't right now.** A 2026-09-17 audit found
  this repo set to public on GitHub despite every doc/commit here
  saying otherwise. Fixing that needs a manual, explicit action —
  don't assume either way until someone's actually checked
  `gh api repos/grumpybollocks/bigblackclocks -q '{private,visibility}'`.
- **`main`**: tagged `v1.0` (LCD stats, backlight, G-key macros) —
  stable, confirmed.
- **`g510s-dev`**: active work, not merged yet — Custom Screens, a
  live analog clock, the Backlight+G-Keys canvas rearchitecture, and
  an Arch package. Nothing merges to `main` until it's physically
  confirmed on the real keyboard — standing rule, not a delay.
- Not on the AUR yet — the package points at this (meant-to-be-private)
  repo, which the AUR can't fetch from either way.

## Not the repo you're after?

This used to also hold a separate app for the Logitech **G910** —
different keyboard, different codebase. That's fully moved out to
[grumpybollocks/g910-control](https://github.com/grumpybollocks/g910-control),
already ahead of anything that was ever here. A few frozen, superseded
G910 branches/tags are still queued for a final tidy-up pass in this
repo (see [`BRANCHES.md`](BRANCHES.md)) but no G910 *file* has lived on
`main` since 2026-09-17.

## Docs

- [`G510_README.md`](G510_README.md) — the full story: protocol
  details, every bug hit and fixed, font conversion, udev rules.
- [`G510_CUSTOM_SCREENS_HOWTO.md`](G510_CUSTOM_SCREENS_HOWTO.md) — how
  to actually use the Custom Screens editor.
- [`READY_FOR_ANYONE.md`](READY_FOR_ANYONE.md) — does this work for
  anyone besides us, not just on our own machines?
- [`BRANCHES.md`](BRANCHES.md) — every branch and tag in this repo,
  explained.

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
