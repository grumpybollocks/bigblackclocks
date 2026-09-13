# G510s LCD Stats Screen + Buttons + Backlight

Repo: `github.com/grumpybollocks/bigblackclocks` (pushed via SSH — key already set up on this machine and on GitHub).

Branches: `main` (this branch) = the Python app, actively developed.
`legacy-yad-backlight-script` = the original yad/bash backlight tool, frozen there as a standalone reference — not present on main anymore.

Fresh-install setup: run `./install.sh` (installs every dependency, places system files, compiles, enables services — see that file for the one thing it CAN'T automate: sourcing your own Eurostile Bold font).

## STATUS FOR AI AGENTS

Read this block only, skip the rest unless you need deep detail for actual debugging.

**v1.0 TAGGED** (git tag `v1.0`, pushed). Everything in the v1.0 section below is DONE and confirmed working by the user — don't re-diagnose any of it, only read further sections if something specific is actually broken.

**v1.1 BUILT, NOT YET TAGGED** — code is committed on main, rebuilt binaries are live and running on the real hardware, and everything has been verified by the assistant (compiled clean, ran repeatedly with no crash, output visually inspected pixel-by-pixel). It has NOT yet been physically confirmed by the user on the actual keyboard LCD — don't tag v1.1 or claim it's "done" until that happens.

### What v1.1 adds

A "Custom Screens" tab in `g510_app.py` — an AIDA64-style dashboard builder for the L2-L5 buttons. Pick a screen (L2-L5), add sensors with a display style (Number or Bar) and an X/Y position, see the result in a live preview pane, Remove any element — every change auto-saves immediately (no separate Save button). New sensors beyond the original CPU/RAM/VRAM/CPU-Temp: GPU %, GPU Edge/Hotspot/VRAM temps, Swap %, Disk % (root + the "frigider" drive), Uptime, Network up/down speed, and 6 genuinely-unlabeled motherboard temps (shown honestly as "MB Temp 1..6", not invented names). Layouts are stored in `custom_screens.txt` (plain SCREEN/ELEMENT text lines, no JSON lib needed in C) and rendered by `g510_lcd_stats.c`'s `draw_custom_screen()`.

**Preview mechanism**: `g510_lcd_stats` gained a `--preview <screen> <outfile>` one-shot mode that renders a single frame through the EXACT same drawing code as the live LCD, but writes a PPM image file instead of touching `/dev/g510-lcd`. `g510_app.py` runs this in the background and displays the result — what you see in the editor is guaranteed pixel-identical to the real screen, not a lookalike.

Two real bugs found and fixed while building this (both matter beyond v1.1, keep in mind for any future C changes to this file):

1. `g510_lcd_stats.c`'s compile command was missing FreeType/TTF flags that `libg15render.so` was actually built with. Without them, this program's view of the `g15canvas` struct is SMALLER than what the library writes into (it has extra `FT_Library`/`FT_Face` fields gated by `#ifdef TTF_SUPPORT`) — `g15r_initCanvas()` then writes past the end of the stack-allocated struct. This was a LATENT bug in v1.0 too (silently landed on stack padding, never tripped anything visible) until v1.1's extra locals shifted it onto the stack canary, causing "stack smashing detected" aborts. Confirmed via AddressSanitizer (no heap/logic bug, only leaked FreeType init allocations — harmless) plus a direct A/B compile with and without stack-protector. Fix: `#define TTF_SUPPORT` + FreeType headers before `#include <libg15render.h>`, and compile with `$(pkg-config --cflags freetype2) ... $(pkg-config --libs freetype2)`. This is now in `install.sh`, `scripts/rebuild.sh`, and the source file itself — if you ever hand-compile this file, use the same flags or it WILL crash intermittently.
2. `fonts/lcd-label-8.fnt` (the converted Eurostile Bold label font) had a corrupted 'S' glyph (rendered as something closer to a '6'). Never caught before because no existing label (CPU/RAM/VRAM/TEMP/MAX) contained the letter S — v1.1's "SWAP" and "DISK" labels hit it immediately. Fixed by reconverting from the original source font (`/usr/local/share/fonts/e/Eurostile_Bold.otf`) via `g15fontconvert -s 8 -i <otf> -o fonts/lcd-label-8.fnt`. Verified by rendering the full A-Z alphabet plus every actual label string used in the sensor table — all clean now, and the pre-existing CPU/RAM/VRAM/TEMP screen was re-verified pixel-for-pixel unchanged.

PNG/image placement on custom screens (the OLDER Phase 2 idea, before the user reprioritized) is DEPRIORITIZED, not built into the Custom Screens tab. `src/png-to-lcd.py` and `g15r_drawXBM()` still exist and still work if this ever comes back, but they are NOT wired into anything current — don't assume they're part of the live feature set.

### v1.0 section

Everything below in this section is DONE and confirmed working by the user:

- **PRIMARY UI is `g510_app.py`** (PyQt5, one window, QTabWidget).
  - **Backlight tab**: color preset dropdown, brightness slider, Apply (live + persists as boot default), Set as Default (persists WITHOUT touching the live color — lets you preview other colors via Apply without losing a chosen default), Start/Stop/Restart Service (covers all 3 background services). "Apply Defaults" was removed by request (redundant with Set as Default, and had a real bug: it read from a hardcoded constant instead of the actual persisted default — if you ever see a similar "the button that's supposed to remember what I set doesn't" complaint, check for this exact class of bug first: hardcoded fallback vs. actually reading the persisted file).
  - **G-Keys tab**: 3-group physical-layout grid (2x3 per group), M1/M2/M3 profile buttons — GUI now polls the daemon's live-profile file every 500ms so it follows physical M-key presses too, not just its own clicks (fixed a real bug: a custom QSS stylesheet was swallowing Qt's default `:checked` visual, needed an explicit `QPushButton:checked` rule). Each G-key: Record a keystroke combo (QThread + python-evdev, grabs the device while recording) OR type a shell command instead — both confirmed working by the user, replayed via `g510_macro_daemon.py` (separate systemd --user service, watches `/dev/g510-keys`). M1/M2/M3 physically switching the live profile: CONFIRMED working (the keycodes were never actually wrong — see BUTTONS section, the daemon logic was already correct once tested). M1/M2/M3/MR hardware indicator LEDs: CONFIRMED working — the fix was switching from a declarative `MODE=`/`GROUP=` udev rule (never matched, root cause not fully understood beyond "these LEDs are seat-tagged and behave differently") to the same `ACTION=="add"` + `RUN+="chgrp/chmod"` pattern already proven for `kbd_backlight`.
- The old yad/bash backlight UI (`g510-backlight-control.sh` + `g510-backlight-apply.sh`) is NOT on this branch anymore — it lives on the `legacy-yad-backlight-script` branch as a standalone reference. `g510_app.py` is the only interface on main.

*(rest of this file: explains the WHY behind the non-obvious parts, for whoever/whatever needs to actually debug something)*

## What This Is

Turns the Logitech G510s keyboard's built-in LCD into a live CPU/RAM/VRAM/TEMP display, wires up the 5 buttons under the screen (L1-L5), and adds RGB backlight control. Everything runs as your normal user (no root needed at runtime), starts automatically at login, and survives reboots/replugs/kernel updates.

## Files

| File | Description |
| --- | --- |
| `g510_app.py` | PRIMARY UI (PyQt5). Phase 1 = Backlight tab. Phase 2 (Custom Screen) goes here too, add as a new tab, see STATUS block above. |
| `g510_lcd_stats.c` | draws the screen(s), the main program |
| `g510_lcd_buttons.c` | listens for L1-L5 presses |
| `png-to-lcd.py` | PNG -> raw XBM bitmap converter, verified working, ready for Phase 2 to call |
| `g510-lcd-stats.service` | systemd --user unit for the above |
| `g510-lcd-buttons.service` | systemd --user unit for the above |
| `99-g510-lcd.rules` | udev rules (see PERSISTENCE below) |
| `fonts/lcd-label-8.fnt` | the label font, converted, actually used (see FONTS below) |
| `fonts/source-ttf/Euro_Bold.otf` | the original font `lcd-label-8.fnt` was converted FROM (keep this — you need it to reconvert at a different size/gap; the `.fnt` alone can't be edited, only regenerated from this source) |
| `set-backlight-color.sh` | applies the saved backlight color on boot (auto-rewritten every time you click Apply in the GUI — don't hand-edit and expect it to stick, the GUI owns this file now) |
| `rebuild.sh` | recompiles both programs, restarts services |
| `view-logs.sh` | tails both services' logs live |
| `start.sh` | one-click start (used by the Desktop icon) |

Desktop icons (in `~/Desktop`, named "G510 LCD - ..."):

| Icon | Description |
| --- | --- |
| App | PRIMARY: launches `g510_app.py` |
| Rebuild | run after editing the `.c` files |
| Start | restarts both services (works whether stopped, crashed, or just stuck/unresponsive) |
| View Logs | live log viewer |
| Project Folder | opens this folder in the file manager |

## How To Make A Code Change

1. Edit `g510_lcd_stats.c` or `g510_lcd_buttons.c`
2. Double-click "G510 LCD - Rebuild" on the Desktop (or run `./rebuild.sh`) — this recompiles both and restarts the services for you.
3. If you touched pixel-drawing code, check the screen for garbage — see "The Pixel Format" below before assuming it's a typo.

## The Pixel Format (the single most important thing to know)

The LCD is 160x43, 1 bit per pixel. libg15render's canvas buffer stores pixels ROW-MAJOR, MSB-first (`pixel_offset = y*160+x`). The physical LCD hardware wants pixels in a different, VERTICAL "page" format (8 pixels per byte, one byte per column, LSB = top pixel) — this is the classic SSD1306-style layout. `dump_to_lcd_format()` in `g510_lcd_stats.c` is a byte-for-byte port of libg15's own `dumpPixmapIntoLCDFormat()` that does this conversion. If you ever see garbled diagonal/streaky output instead of clean text, you skipped this conversion somewhere — do NOT just `memcpy` canvas->buffer to the device, it will look like static.

The final wire format is a 992-byte HID report: byte 0 = `0x03` (the report ID, discovered by reading libg15's source — it's not documented anywhere else), bytes 1-31 = padding/zero, bytes 32-991 = the converted 960 bytes of page-format pixel data.

## Why This Doesn't Use g15daemon / libg15's Own Device Code

g15daemon (the "standard" tool for this) grabs the keyboard's whole extra-keys USB interface via libusb, detaching it from the kernel's `hid_lg_g15` driver, then re-emits key events through its OWN decoder — which has the WRONG key table for a G510s specifically (a long-standing, never-fixed bug in that 15+ year old project). This broke media/volume keys HARD when tested live (confirmed: random garbage keystrokes).

Instead, this program writes directly to `/dev/g510-lcd`, a hidraw device node — hidraw lets you send/receive HID reports through a device the kernel driver already owns, without detaching anything. The kernel's normal key handling (`hid_lg_g15`) keeps working completely undisturbed. This was verified repeatedly with the LCD screen running continuously while actively using media keys — zero interference either way.

## Media Keys Fix (predates this project, but this is why it's safe to touch this keyboard at all — read before changing anything input-related)

Three separate, unrelated problems were found and fixed on this exact keyboard. None of them involve this LCD project's code, but breaking any of them again is an easy mistake to make while experimenting:

1. Play/Pause is PHYSICALLY DEAD (corrosion/worn contact, confirmed via raw HID capture — zero signal from that key even wet with contact cleaner, while every neighboring key on the same interface worked). Fixed with a udev hwdb remap: the Stop button's key sends the correct signal, so `/etc/udev/hwdb.d/91-g510-stop-to-playpause.hwdb` remaps its exact scan code (`0x000c00b7`, HID consumer-page "Stop") to `KEY_PLAYPAUSE` instead of `KEY_STOPCD`. You lose a hardware Stop button; you gain a working Play/Pause. If you ever want the real Stop function back, delete that hwdb file and re-run `sudo systemd-hwdb update`.
2. Brave's native media-key support and the "Plasma Integration" browser extension (id `cimiefiiaegbelhefglklhhakcgmhkai`) were BOTH registering as MPRIS players for the same tab, so KDE's media-key router got confused about which one to actually control. Fixed by disabling that extension's media-control feature (its `active_bit` should read `false` in Brave's Preferences JSON if you ever need to check).
3. The kernel driver, `hid_lg_g15`, is what actually reports all of this keyboard's keys correctly — do NOT blacklist it (an earlier attempt to "fix" flaky media keys by forcing hid-generic instead turned out to be unnecessary once #1 and #2 above were found; `hid_lg_g15` is also required for the Gaming Keys interface this LCD project's buttons depend on). Check `lsmod | grep hid_lg_g15` and `grep -rl lg_g15 /etc/modprobe.d/` (should be empty) if media keys or L1-L5 ever stop responding after a system change.

## Multi-Screen System

A single file, `$XDG_RUNTIME_DIR/g510lcd_screen`, holds one number:

- `0` = the stats screen (CPU/TEMP/VRAM/RAM, in that vertical order)
- `1` = a clock
- `2-5` = "L2".."L5" test screens (see BUTTONS below)

`g510_lcd_stats.c` re-reads this file every loop iteration (~1-2s) and draws whichever screen it says. `g510_lcd_buttons.c` is the only thing that ever WRITES to this file. To add a new screen: write a new `draw_XXX_screen()` function, add a branch for its number in `main()`'s loop, and make some button set that number in `g510_lcd_buttons.c`.

## Buttons (L1-L5)

Real, standard Linux keycodes — no HID remapping was needed, unlike the media keys (see MEDIA KEYS FIX above for that story). Confirmed by testing each button individually:

- L1 = 696 (`KEY_KBD_LCD_MENU1`) — cycles: stats -> clock -> stats... (if currently on an L2-L5 test screen, L1 returns to stats)
- L2 = 697 (`KEY_KBD_LCD_MENU2`) — shows "L2" on screen (test/placeholder)
- L3 = 698, L4 = 699, L5 = 700 — same pattern

These switches BOUNCE (one physical press can fire 2-4 raw events) — `g510_lcd_buttons.c` has a 400ms debounce per key, don't remove it. L2-L5 currently do nothing but confirm the press — to actually program them, edit the `else` branch in `g510_lcd_buttons.c`'s main loop (the one that currently just calls `write_screen()`+`log_button()`).

## Fonts

The library ships `default-00` through `default-39.fnt`, but they're all the SAME typeface at different sizes — not actually different fonts. For anything else, use `g15fontconvert -i font.ttf -o out.fnt -s N -g 1` (the AUR `libg15render` package; `-s` is NOT literal pixel height, it's closer to a point size — check the ACTUAL resulting height with:

```bash
python3 -c "import struct; print(struct.unpack('<H', open('FILE.fnt','rb').read()[4:6])[0])"
```

and adjust `-s` up/down until it matches what you want (our 10px row spacing needs a font around 8-9px tall).

IMPORTANT: thin/regular-weight fonts render GARBLED at this tiny size (confirmed multiple times) — there simply aren't enough pixels for fine strokes. Use Bold or Black weights only. Current setup: labels use Eurostile Bold (`fonts/source-ttf` has the `.otf`, matches the G510's original stock LCD font style), numbers use the library's own built-in `G15_TEXT_SMALL` font (also tried several converted fonts for numbers — all looked worse than the built-in one, which was purpose-built for this exact resolution).

`.otb`/`.pcf` bitmap fonts (like Terminus) do NOT work with `g15fontconvert` — it silently produces an empty/broken `.fnt` (`font_height` stuck at one value regardless of `-s`, near-zero file size). Only scalable TTF/OTF outline fonts convert correctly.

## Backlight (RGB Keyboard Glow)

This is a REAL Linux kernel LED device, nothing hidraw/USB-custom about it: `/sys/class/leds/g15::kbd_backlight/` — `brightness` (0-255) and `multi_intensity` ("R G B" space-separated, 0-255 each). KDE's own "Keyboard Colour: Follow accent colour" toggle fights over this same file — turn that OFF in System Settings > Brightness & Color if you want manual control to actually stick.

Applied automatically on boot/replug by `set-backlight-color.sh` via the udev rule. Use the "Backlight" tab in `g510_app.py` to change it — a color preset dropdown + brightness slider, Apply / Apply Defaults, no sudo prompt. Whenever you click Apply, `apply_backlight()` in `g510_app.py` REWRITES `set-backlight-color.sh` with your new choice — so whatever you pick becomes the new permanent boot default automatically, not just a one-time live change. "Apply Defaults" resets to Blue-Violet/full brightness (110 0 255) without touching the dropdown/slider state, and also persists that choice.

Uses a preset-color dropdown (`COLOR_RGB` dict) rather than a live color picker — a Qt color picker would work fine here (this isn't the yad CLR+SCL crash from the old script, see the `legacy-yad-backlight-script` branch for that story), just wasn't built yet. Add more presets by editing the `COLOR_RGB` dict near the top of `g510_app.py`.

## Persistence (why this survives reboots/updates)

`99-g510-lcd.rules` (installed at `/etc/udev/rules.d/`) does three things:

1. Creates `/dev/g510-lcd`, a stable symlink to whatever hidraw number the LCD's USB interface gets THIS boot (it changes across reboots/replugs, don't hardcode a hidrawN number anywhere).
2. Creates `/dev/g510-keys` the same way, for the Gaming Keys input device.
3. On the backlight LED appearing, chmod/chgrp's it to group "input" (so no sudo is needed at runtime) and runs `set-backlight-color.sh`.

The two systemd --user services are `enable`d, so they autostart at every login. `hid_lg_g15` (the kernel driver all of this depends on) is a mainline upstream driver, ships in every Manjaro kernel package — nothing here is tied to today's specific kernel version.

## Gotcha We Actually Hit (keep this in mind if things break weirdly)

A test script once ran `fopen("/dev/hidrawN", "wb")` at the exact moment the real device briefly didn't exist during re-enumeration — this silently created a REGULAR FILE named `hidrawN` in `/dev` instead of erroring, which then permanently blocked the kernel from recreating the real character device at that path. Symptom: permissions look right but writes still fail, or udev rules seem to apply then "un-apply". Fix: `stat /dev/hidrawN` — if it says "regular file" instead of "character special file", `sudo rm` it and replug the keyboard.

## Udev Rule Gotcha (if you ever add another rule)

Don't mix `ATTRS{}` from two different ancestor devices in one rule line (e.g. `ATTRS{idVendor}` lives on the USB device, `ATTRS{bInterfaceNumber}` lives on the USB interface, a different level) — once udev matches one `ATTRS{}` against a device, it locks onto that SAME device for the rest of the rule's `ATTRS{}` checks, silently failing to match. Use `ENV{}` for properties instead where possible (`ENV{ID_VENDOR_ID}`, `ENV{ID_MODEL_ID}`, `ENV{ID_USB_INTERFACE_NUM}` are all already resolved onto the device you actually want to match, no ancestor-walking involved) — this is what the hidraw rule does and it's reliable.
