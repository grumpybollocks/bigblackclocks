# Branch map

This repo holds two independent apps for two different Logitech keyboards.
Keeping this file up to date is the whole point of it -- if a branch's
purpose changes, update its entry here in the same commit.

See [`READY_FOR_ANYONE.md`](READY_FOR_ANYONE.md) for what makes both
apps actually installable by someone other than us -- what's already
solid, what's still a known gap.

## Two machines, two keyboards

This repo is worked on from two machines, each with only one of the two
keyboards physically attached: one machine has the G910, the other has the
G510s. Each machine's session should only be doing active development on
the branch for the keyboard it actually has -- don't start G510s work
from the G910 machine or vice versa, since neither side can test on the
real hardware for the other keyboard.

## Active branches

- **`main`** -- the merged trunk. Contains both apps: the G510s app
  (LCD/backlight/G-keys) and, as of the merge on 2026-09-14, the G910
  app (per-key RGB/G-keys) too. Nothing landed here directly touches
  the other app's files -- verified at merge time that every G510s
  file the G910 side differed on was untouched by G910 development
  (pure drift from G510s's own later history), so the merge was
  clean with no real conflict resolution needed. Also carries the
  Custom Screens image-import feature merged in from the G510s machine the
  same day.
- **`g510s-dev`** -- active G510s development, driven from the G510s
  machine (the one with that keyboard). This is the canonical branch for
  ongoing G510s work; merges back into `main` when a feature is done.
- **`g910`** -- active G910 development, driven from the G910 machine.
  Used to point at an older, pre-canvas-rewrite snapshot;
  fast-forwarded on 2026-09-14 to match `g910-canvas`'s tip (a real
  fast-forward, nothing rewritten or deleted -- the old commit it used
  to point at is still reachable as an ancestor of `g910-canvas`, and
  separately tagged `g910-skeleton-v1-buttongrid`). Merges back into
  `main` when a feature is done.

## Historical / frozen branches (kept for reference, not deleted)

- **`g510s`** -- a local-only branch created on the G910 machine on
  2026-09-14 before realizing that machine doesn't have a G510s to
  develop against -- `g510s-dev` (above) is the real one. Left in
  place, unpushed, per the no-delete rule; not used going forward.
- **`g910-canvas`** -- the full blow-by-blow G910 development history:
  HID++ protocol reverse-engineering, every real bug found and fixed,
  the canvas UI rearchitecture. `g910` now points at the same commit;
  this branch stays as the detailed record of how it got there.
- **`legacy-yad-backlight-script`** -- the original yad/bash backlight
  script for the G510s, frozen as a standalone reference. Superseded
  by the G510s app's own Backlight tab.

## Tags

- `v1.0` / `g510-v1.0`-equivalent -- G510s v1.0.
- `g910-v1.0` -- G910 app v1.0, tagged after a full bug-check pass.
- `g910-v1.1` -- G910 phase 1 wrap-up: Profiles panel overflow fix,
  GUI-daemon profile desync fix, gold-border assigned-key indicator,
  manual hex colour entry. Merged into `main`.
- `g910-v1.2` -- colour-picker rebuild (real named presets + hex,
  native QColorDialog fully removed from both the sidebar and the
  canvas's own drag-select path), device paths now discovered
  dynamically instead of hardcoded to one physical keyboard's USB
  serial, profiles/macros moved to `$XDG_DATA_HOME/g910-control`, and
  a real Arch package (`packaging/g910-control/`) built and verified
  locally alongside the existing git-clone installer. Merged into
  `main`.
- `g910-gui-v1` -- G910 reaching a single unified canvas-based GUI.
- `g910-skeleton-v1-buttongrid` -- G910's pre-canvas button-grid UI,
  permanent record before the canvas rearchitecture.
