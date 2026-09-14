# G510s Canvas Rearchitecture — Backlight + G-Keys merged into one view

Built 2026-09-14 on AC130Tria (where the real G510s hardware lives),
mirroring the sibling G910 project's canvas rearchitecture
(`G910_CANVAS_PLAN.md`, branch `g910-canvas`) at the user's explicit
request: "adapt this one to the variables at hand." Not a shared
codebase with the G910 app — a parallel, independent implementation,
because the two keyboards' real capabilities are too different to
force through one abstraction (see "What's different from G910"
below). This is built and self-verified; **not yet visually confirmed
by the user** (they were asleep when this was finished) — same rule as
everywhere else in this project: don't call it fully done until they
say so.

## What changed

- `Backlight` and `G-Keys` tabs merged into one: `Backlight + G-Keys`.
- The G-Keys grid of plain `QPushButton`s is replaced by
  `src/g510_canvas.py`'s `G510Canvas` — a real keyboard-shaped
  `QWidget` with `QPainter`-based rendering and rect-based hit-testing
  (`Cell(key_name, label, row, col, width, height, kind)`), same
  overall pattern as the G910 app's `g910_canvas.py`.
- `Custom Screens` tab renamed to `Custom Screens (WIP)` and otherwise
  **completely untouched** — the user explicitly said to wait on that
  tab since they weren't there to confirm LCD changes.
- Applied the G910 app's exact dark `STYLESHEET` (copied verbatim,
  credited in a comment) for visual consistency across the two sibling
  apps.
- Fixed the same "hardcoded `resize()` goes stale" class of bug the
  G910 project hit: `MainWindow` now calls `self.adjustSize()` instead
  of a fixed pixel size, so it always fits whatever the current tab
  actually needs.
- Added an MR indicator to the canvas (M1/M2/M3/MR row, top-left,
  above the G-key columns) — the physical key/LED existed
  (`g15::macro_record`, already used by `g510_macro_daemon.py`) but
  the GUI never showed it before now.

## What's reused from the G910 project vs. built fresh

**Reused verbatim** (with credit, not re-derived): the main
board/nav-cluster/numpad `Cell` position data — real column positions,
inter-group gaps, and standard ANSI keycap width overrides
(Backspace≈2u, Tab≈1.5u, Caps≈1.75u, Enter≈2.25u, Shift≈2.25u/2.75u,
Ctrl/Alt/Win≈1.25u). That data is itself ported by the G910 project
from Solaar's `ui/perkey/layouts/_keyboard_base.py` (from OpenRGB's
`KeyboardLayoutManager.cpp`, GPL-2.0-or-later) — it's real reference
data for a standard ANSI layout, which the G510s also uses (confirmed
full-size ANSI + numpad from the user's own product photos, not
guessed). Reusing it here is correct reuse of a verified fact, not
copying an assumption.

**Built fresh, not reused from G910 at all**: G-key/M-key/LCD
placement (G510s's physical layout is completely different — 18
G-keys in 3 columns × 6 rows grouped in 3 blocks of 2, vs G910's 9 in
a 5+4 split; no Logo key on G510s at all), and every bit of the
color-control backend.

## What's different from G510s vs. G910 (why no shared code)

| | G910 | G510s |
|---|---|---|
| Backlight | Per-key HID++ RGB (`keyledsctl`, one color per key) | ONE sysfs LED for the entire board (`/sys/class/leds/g15::kbd_backlight`) — confirmed, no per-key addressing exists on this hardware at all |
| G-keys | 9 (G1-G9), 5 left column + 4 top row | 18 (G1-G18), 3 columns × 6 rows, grouped in 3 blocks of 2 rows |
| Logo key | Yes, individually lit | No equivalent |
| Canvas interaction | Click/drag-select any key, opens a color picker | Only G-keys (open macro dialog) and M1/M2/M3 (switch profile) are interactive — everything else is decorative, because there's nothing else *to* interact with on this hardware |

Given that, the G510s canvas shows the WHOLE board (main
board/nav/numpad/M-keys-row) tinted in whatever the **actual current
live backlight color** is (`read_current_rgb()`, already-existing,
already-proven code) — refreshed the moment Apply changes it — rather
than any per-key preview, since a per-key preview would misrepresent
hardware that can't actually do that. G-keys get their own fixed
accent color (not the board color) specifically to visually mark "this
part is clickable," and the LCD placeholder gets a third, muted tone
to mark "this is a screen, not a light or a key" — matching the same
three-way visual distinction the user's product photos actually show.

## MR button: exposed, not yet interactive

The canvas draws MR and reflects its real LED state
(`/sys/class/leds/g15::macro_record/brightness`, polled every 500ms
alongside the M1/M2/M3 profile sync) — confirmed this sysfs path
exists and is readable on the real hardware. Clicking it currently
does nothing. There's no established "toggle a recording mode"
concept anywhere in `g510_macro_daemon.py` or the rest of this app to
attach a click to — recording happens per-G-key via the existing
`MacroRecordDialog`, not through a global MR toggle. Exposing the
indicator without inventing new behavior for it seemed like the
correct scope; say the word if you want MR to actually do something
and it can be designed properly (with the same "plan first" rule as
everything else here).

## A real hardware quirk found while testing this, unrelated to the canvas itself

While verifying `on_apply()` still actually reaches the real LED
(it does — RGB confirmed correct on real hardware both before and
after this change), the **brightness slider's practical effect turned
out to be questionable**: writing intermediate values (e.g. 153 for
60%, or 30, or even 0) to `/sys/class/leds/g15::kbd_backlight/brightness`
did not reliably read back the value just written — readbacks showed
100%/255 in one test and a stale 30 in another, despite
`max_brightness` reporting 255 (implying a real 0-255 range). This
looks like either driver-side quantization to a small number of real
supported steps, or write/read latency in the USB round-trip, or
something else not yet isolated. **Not investigated further tonight**
— it predates this canvas change (the exact same `apply_backlight()`
function, unchanged), is orthogonal to what was actually asked for,
and doesn't block anything here (the canvas correctly shows whatever
color IS live regardless of what brightness value produced it). Worth
a dedicated, focused investigation later if the brightness slider
matters to you in practice — flagging it now so it isn't quietly lost.

## Verification performed (all before calling this ready to look at)

- `python3 -m py_compile` on both new/changed files: clean.
- Headless smoke test (`QT_QPA_PLATFORM=offscreen`): full `MainWindow`
  instantiates with both tabs, no exceptions.
- Signal wiring, tested directly against the real running code (not
  just read): a simulated G-key click opens `MacroRecordDialog`
  (dialog's `exec_()` mocked so it doesn't block headlessly, call
  confirmed via mock assertion); a simulated M-key click updates both
  `current_profile` and the canvas's highlighted M-key; MR's LED-state
  poll reads the real sysfs file and reflects it.
- **Real hardware test, not simulated**: called `on_apply()` through
  the actual GUI code path with a test color (Cyan, arbitrary
  brightness), confirmed the PHYSICAL LED's `multi_intensity` sysfs
  value actually changed to match, confirmed the canvas's board color
  updated to match, then restored the keyboard to its actual persisted
  default (Green, full brightness) and re-verified that stuck.
- Rendered a full screenshot of the actual live `MainWindow` (not a
  standalone test harness) to visually check the merged layout,
  colors, and proportions before considering this done — looked
  correct: G-keys in a distinct blue, LCD in a distinct muted tone,
  main board correctly showing the real live green, M1 correctly
  highlighted as the active profile.
- Grepped the whole project for leftover references to the removed
  `BacklightTab`/`GKeysTab` classes — none outside of explanatory
  comments.
- Relaunched the actual live GUI app process with the new code;
  confirmed it started with an empty log (no exceptions) and stayed
  running.

**What's NOT yet verified**: an actual mouse click through the real
GUI window (as opposed to a simulated signal emission) — the click
handling code path (`mousePressEvent` → `_cell_at` → signal emit) is
straightforward Qt and the signal-side wiring is confirmed, but a
literal physical click hasn't been done by a human yet. Recording a
real macro through the new canvas end-to-end, and seeing the whole
thing with your own eyes, are both still pending — same "not done
until you say so" rule as always.
