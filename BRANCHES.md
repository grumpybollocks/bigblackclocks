# Branch map

This repo holds one app, for one keyboard: the Logitech G510s (LCD/
backlight/G-keys). Keeping this file up to date is the whole point of
it -- if a branch's purpose changes, update its entry here in the same
commit.

See [`READY_FOR_ANYONE.md`](READY_FOR_ANYONE.md) for what makes the
app actually installable by someone other than us -- what's already
solid, what's still a known gap.

## Formerly a two-keyboard repo

Until 2026-09-17 this repo also held a separate app for the Logitech
G910 Orion Spectrum (per-key RGB/macros), developed alongside the
G510s app for a while. That app's source, docs, install script,
packaging, and full dev history (the `g910` and `g910-canvas`
branches, and every `g910-*` tag) have been removed from here --
confirmed byte-identical-or-newer in the app's own standalone public
repo, [grumpybollocks/g910-control](https://github.com/grumpybollocks/g910-control),
before anything was deleted, and a full mirror of this repo's
pre-cleanup state was taken first so nothing is actually unrecoverable.
This repo is now exclusively about the G510s.

## Active branches

- **`main`** -- the G510s app: LCD stats display, backlight, G-key
  macros. Tagged `v1.0`.
- **`g510s-dev`** -- active development, driven from the machine with
  the actual G510s hardware attached (this app can only be tested for
  real from there). This is the canonical branch for ongoing work;
  merges back into `main` when a feature is done and physically
  confirmed on the real keyboard -- nothing gets tagged or merged
  before that, standing rule, not a delay.

## Historical / frozen branches (kept for reference, not deleted)

- **`legacy-yad-backlight-script`** -- the original yad/bash backlight
  script for the G510s, frozen as a standalone reference. Superseded
  by the app's own Backlight tab.

## Tags

- `v1.0` -- G510s v1.0 (LCD stats, backlight, G-key macros), the
  tagged/confirmed baseline on `main`.
- `pre-canvas-checkpoint` -- snapshot right before the Backlight +
  G-Keys canvas rearchitecture began, includes the v1.1 Custom Screens
  (AIDA64-style sensor dashboard for L2-L5) work.
- `g510-canvas-v1` / `g510-canvas-v2` / `g510-canvas-v3` -- checkpoints
  through the canvas rearchitecture: the macro-assigned key indicator
  and a full solo self-audit (v1), hover cursor feedback and
  contextual hint text (v2), and a real fix for M1/M2/M3 clicks
  reverting after ~500ms (v3).
