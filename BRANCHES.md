# Branch map

This repo holds two independent apps for two different Logitech keyboards.
Keeping this file up to date is the whole point of it -- if a branch's
purpose changes, update its entry here in the same commit.

## Active branches

- **`main`** -- the merged trunk. Contains both apps: the G510s app
  (LCD/backlight/G-keys) and, as of the merge on 2026-09-14, the G910
  app (per-key RGB/G-keys) too. Nothing landed here directly touches
  the other app's files -- verified at merge time that every G510s
  file the G910 side differed on was untouched by G910 development
  (pure drift from G510s's own later history), so the merge was
  clean with no real conflict resolution needed.
- **`g510s`** -- active G510s development. Forked from `main` at
  `5cf7a89` (2026-09-14), the last commit before G910 was merged in,
  so it's the G510s app exactly as it stood on `main`, with no G910
  files at all. Further G510s work happens here and gets merged back
  into `main` when a feature is done.
- **`g910`** -- active G910 development. Used to point at an older,
  pre-canvas-rewrite snapshot; fast-forwarded on 2026-09-14 to match
  `g910-canvas`'s tip (a real fast-forward, nothing rewritten or
  deleted -- the old commit it used to point at is still reachable as
  an ancestor of `g910-canvas`, and separately tagged
  `g910-skeleton-v1-buttongrid`). Further G910 work happens here and
  gets merged back into `main` when a feature is done.

## Historical / frozen branches (kept for reference, not deleted)

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
- `g910-gui-v1` -- G910 reaching a single unified canvas-based GUI.
- `g910-skeleton-v1-buttongrid` -- G910's pre-canvas button-grid UI,
  permanent record before the canvas rearchitecture.
