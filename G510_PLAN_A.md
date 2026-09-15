# G510s Plan A — from `g510s-dev` to a confirmed, mergeable, installable app

Written 2026-09-15 on the machine where the real G510s hardware lives
(`g510s-dev`, the canonical branch for this work per `BRANCHES.md`).
This is a roadmap, not a one-shot task list — later sessions should
keep updating this file in place as phases complete or new gaps turn
up, the same way `G510_CANVAS_PLAN.md` and
`G510_DRAW_ON_DISPLAY_PLAN.md` have been treated. Everything below is
sourced from real git history, real file reads, real `journalctl`
output, and a real `lsusb -v` against the actual connected hardware —
not assumed from filenames or commit subjects alone.

## Where this branch actually stands right now

`g510s-dev` is 3 commits ahead of `main`, not yet merged:

```
caf5be0 Document phase-1 polish status in G510_README.md
7807781 Phase 1 polish: Custom Screens discoverability fixes
0d7de14 Harden image-import path found during post-launch audit
```

Verified via `git fetch` + `git log main..g510s-dev` — no other
divergence, no uncommitted code changes (`custom_screens.txt`'s only
local diff is the user's own live LCD layout editing, which is
expected). Nothing here is stale or at risk.

Four pieces of work are sitting **built and self-tested, but not yet
physically confirmed on the real G510s LCD** — per this project's own
repeated rule (see `G510_CANVAS_PLAN.md`, `G510_README.md`): nothing
is "done" until the user says so on the real hardware.

1. **Custom Screens v1.1** — the sensor dashboard for L2-L5 (20+
   sensors, drag-to-position, resize bars, PNG image import). Read the
   full implementation end to end this session: the on-screen preview
   shells out to the real compiled `g510_lcd_stats --preview` binary,
   which writes a `.meta` sidecar with exact per-element pixel bounds
   from real font-glyph metrics — so the GUI preview and drag/resize
   hit-testing are provably pixel-identical to the LCD, not a Python
   reimplementation or a guessed layout. The remaining risk is
   real-hardware quirks (contrast, refresh timing, button feel), not
   preview accuracy.
2. **Canvas rearchitecture** — Backlight + G-Keys merged into one tab,
   `g510_canvas.py`'s `QPainter` keyboard replacing the old button
   grid, MR indicator added to the canvas (LED state shown, not yet
   clickable — no "toggle recording" exists in the daemon yet).
3. **PNG/image import** for Custom Screens (`png-to-lcd.py`,
   Floyd-Steinberg dithered, fit-not-upscale).
4. **Phase 1 polish** (`7807781`) — tooltips explaining disabled L1
   controls, staggered placement so two imported images in a row don't
   land exactly on top of each other, a duplicate-constant cleanup.

`0d7de14` (image-import hardening — explicit null-termination after
every `strncpy()` in `g510_lcd_stats.c`'s config parser, since an
unterminated buffer there feeds a `fopen()` call; a width-*and*-height
bounds check before accepting an `IMAGE` line, matching a same-commit
fix in `png-to-lcd.py` that previously only constrained width) is a
real correctness fix already applied, not pending — it doesn't need
re-confirmation the way the visual features above do, but is listed
here because it landed in the same unmerged range.

## Phase 0 — Real-hardware confirmation pass (blocking everything else)

This is the actual bottleneck, not missing code. Go through each of
the four items above live on the physical G510s:

- Custom Screens v1.1: cycle L2-L5 with the real button presses (not
  just the GUI preview — `g510_lcd_buttons.c`'s 400ms debounce was
  itself added after real single-presses were observed logging 2-4
  times, so the physical button behavior is worth trusting less than
  the GUI by default), confirm each configured sensor reads correctly,
  confirm drag/resize in the GUI matches what the LCD actually shows,
  confirm PNG import looks right at real LCD contrast (1bpp XBM
  conversion can look different on-screen vs. a real monochrome LCD).
- Canvas rearchitecture: confirm the merged tab renders correctly,
  G-key clicks still open the macro dialog, M-key clicks still switch
  profiles, board-color tinting still matches the live backlight.
- Phase 1 polish: confirm the new tooltips actually show, confirm two
  imported images in a row no longer land exactly on top of each
  other.

Fix whatever's found for real, using the existing self-audit pattern
already established in this repo (`G510_DRAW_ON_DISPLAY_PLAN.md`
documents exactly this: build, self-test, catch and fix a real bug
before calling it done — including once catching that a demo
screenshot was taken against a stale `/tmp` binary, not the real
production one). Do not merge to `main` or move to Phase 2 until this
pass is complete.

## Phase 1 — Fix the known backlight-slider quirk

Documented, unresolved, not yet investigated: the backlight brightness
slider's intermediate values don't reliably read back from sysfs
(`/sys/class/leds/g15::kbd_backlight/`). Needs focused investigation —
whether it's a read-timing issue, a sysfs caching quirk, or the kernel
LED class genuinely coalescing/rounding intermediate writes. Not
guessed at further here since it hasn't been investigated yet; that
investigation is the actual Phase 1 task.

## Phase 2 — Close the G510s-specific packaging gaps — DONE 2026-09-15

Pulled directly from `READY_FOR_ANYONE.md` (brought into this branch
this pass; didn't exist here before). All three real, already-scoped
gaps closed and verified, not just coded:

1. ~~`install.sh`'s desktop-shortcut step only `chmod +x`'s files that
   must already exist by hand.~~ Fixed: now generates all 5 launchers
   fresh from the resolved `$DIR`, ported from `install-g910.sh`'s
   already-working pattern.
2. ~~`scripts/start.sh` calls `zenity`, which `install.sh` never
   checks for or installs.~~ Fixed: added to the dependency list.
3. ~~Desktop launchers were only written to `~/Desktop`, not also
   `~/.local/share/applications`.~~ Fixed: now written to both.

Verified by running just the shortcut-generation logic in isolation
(not the full installer — that would trigger unrelated sudo/pacman/
udev/systemd changes this fix doesn't touch), diffing the regenerated
files against the real working originals on this machine (only diff:
added `Exec=` path quoting, a real robustness improvement not a
regression), confirmed the app still launches cleanly via the quoted
command. `READY_FOR_ANYONE.md`'s G510s section updated to match G910's
"done and verified this pass" wording, same file, same branch.

## Phase 3 — Merge to `main`

Once Phases 0-2 are complete and confirmed: merge `g510s-dev` into
`main`. `BRANCHES.md`'s own account of the G910 merge describes it as
clean with no real conflicts, because neither side's development ever
touched the other's files — worth a real check at merge time
regardless, not assumed from that precedent alone. `main` is currently
52 commits ahead of what this branch has seen (`git fetch` shows this
is essentially all G910-side merge work, not overlapping G510s files —
verified this session, not assumed), so a real `git merge`/rebase
review at that point is warranted before treating it as a formality.

## Phase 4 / "Option B" — AUR packaging (stretch goal, not yet started)

Referred to elsewhere as "Plan B"/"Option B" — same thing as this
phase, confirmed directly by the user 2026-09-15.

`READY_FOR_ANYONE.md` already researched the packaging mechanics
against a real installed reference (`solaar` — same problem domain,
Logitech HID++ device control, PyQt-based, needs a udev rule): a
proper PKGBUILD, service units under `/usr/lib/systemd/user/`, udev
rule under `/usr/lib/udev/rules.d/`, and `depends=` doing what
`install.sh`'s hand-rolled dependency script does today. This takes
the app from "clone and run install.sh" to "`yay -S`".

**Identity-in-history blocker — resolved by user decision, not a
technical fix:** real AUR packaging needs a public source repo, but
this repo's commit history has the user's real email address in
essentially every commit (`Co-Authored-By:` trailers) and can't be
easily scrubbed without rewriting history shared across multiple
active branches/machines. The user's explicit decision (2026-09-15,
asked directly, not assumed): don't solve this in the current repo.
Keep building normally here through Phases 0-3. Once the app is
genuinely complete, the user will personally create a fresh repo for
the real public/AUR release at that point — this phase's actual
packaging work (PKGBUILD, etc.) can still be prototyped/tested here,
but the *publish* step targets that future clean repo, not this one.
This same blocker and resolution applies to the G910 side's equivalent
phase (their own "Phase B") — same shared repo, same history.

Still a stretch goal, still not blocking anything in Phases 0-3.

## Why this order

Phase 0 gates everything because merging or building further on top of
unconfirmed features risks compounding an undiscovered real-hardware
bug — the project's own established discipline, not a new rule
invented for this plan. Phase 1 and 2 are independent of each other
and could run in parallel if picked up by different sessions, but both
should land before Phase 3's merge so `main` doesn't inherit either the
open quirk or the packaging gap. Phase 4 is explicitly a stretch goal
and shouldn't block anything real above it.
