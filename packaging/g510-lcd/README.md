# g510-lcd packaging

A real Arch/pacman PKGBUILD for the G510s app, alongside the existing
`install.sh` git-clone install method (both are valid; this one
follows the "package installs everything to fixed `/usr/...`
locations, no per-user path discovery needed" pattern -- see
`PORTABILITY.md`), mirroring `packaging/g910-control/` on the G910
side, built the same night for direct comparison.

## Status

Built and verified locally as far as possible **without root**.
**Not installed on the real system, not submitted to the AUR.** The
one remaining step -- a real `sudo pacman -U` install -- was blocked
by this session's own permission system (an auto-mode classifier
denial, not a workaround-able failure) and needs the user's explicit
go-ahead, either by running it themselves or by granting that
permission directly. Everything short of that step has been verified
for real, not assumed.

## Dependencies

`depends=('python' 'python-pyqt5' 'python-pillow' 'python-evdev'
'ydotool' 'freetype2' 'libg15render')`. Cross-checked against actual
source, not copied from install.sh's list unexamined -- `yad` is in
install.sh's pacman line but a real grep of every `.py`/`.c` file
found zero uses of it anywhere in current code (leftover from the
retired yad-based backlight script, see `BRANCHES.md`'s
`legacy-yad-backlight-script` entry); correctly left out here.
`python-pillow` is real and required (`png-to-lcd.py`'s Floyd-Steinberg
dithering for the Custom Screens image-import feature).

## Layout -- deliberately NOT flat, unlike g910-control

`packaging/g910-control`'s PKGBUILD installs its `.py` files flat
under `/usr/lib/g910-control/` (no `src/` subdirectory). This package
keeps the `src/` subdirectory:

- `/usr/bin/g510-lcd` -- thin wrapper, `exec`s the real script
- `/usr/lib/g510-lcd/src/*.py`, `*.c`-compiled binaries -- same shape
  as the git-clone checkout, not flattened
- `/usr/lib/systemd/user/g510-lcd-stats.service`,
  `g510-lcd-buttons.service`, `g510-macro-daemon.service`
- `/usr/lib/udev/rules.d/99-g510-lcd.rules` (see below -- one line
  dropped, everything else kept)
- `/usr/share/applications/g510-lcd.desktop`
- `/usr/share/licenses/g510-lcd/LICENSE`

This isn't a style choice -- `g510_app.py` computes its own
`PROJECT_DIR` as `Path(__file__).resolve().parent.parent`, and several
of its own path constants (`STATS_BINARY`, `DEFAULTS_SCRIPT`, the
`png-to-lcd.py` subprocess call) are built as `PROJECT_DIR / "src" /
...` or `PROJECT_DIR / "scripts" / ...`. Flattening the layout the way
`g910-control` does would silently break every one of those
(`PROJECT_DIR` would resolve one directory too high, e.g. `/usr/lib`
instead of `/usr/lib/g510-lcd`) without a real source change this pass
didn't make. Keeping the checkout shape under a fixed root means the
existing, already-tested path logic (the same code exercised by
tonight's full regression suite) is correct here with zero changes,
rather than a new, unverified code path.

## Known gap: the udev rule's backlight-restore line

`99-g510-lcd.rules` has four jobs: create `/dev/g510-lcd` and
`/dev/g510-keys` symlinks (both genuinely load-bearing --
`g510_lcd_stats.c`/`g510_lcd_buttons.c` hard-`fopen()` those exact
paths and fail outright without them, confirmed by reading the actual
open() calls, not assumed), fix LED sysfs permissions, and restore the
last-applied backlight color on every hotplug via
`RUN+="__PROJECT_DIR__/scripts/set-backlight-color.sh"`.

The first three have zero `PROJECT_DIR` dependency and are packaged
as-is, unconditionally. The fourth is dropped for this package: that
script's write location depends on which user's desktop session
applied a color (`~/.local/share/g510-lcd/set-backlight-color.sh` as
of tonight's DATA_DIR migration), and udev fires as root with no
resolvable per-user `$HOME` at that point on a general multi-user-safe
system. Real options exist (a wrapper that resolves the logged-in
user via `loginctl`, moving color-restore to the user-session systemd
service instead of a root udev hook) but weren't attempted this pass
-- deliberately scoped out rather than guessed at. Until solved: a
packaged install gets a fully working LCD screen, buttons, and macros,
but backlight color won't auto-restore across a physical replug (it
still applies live and persists correctly within the same session,
same as tonight's live testing on the real machine confirmed).

## Known gap: the label font

Same restriction `install.sh` already documents -- Eurostile Bold is
commercially licensed and can't be redistributed in the package.
`g510_lcd_stats` refuses to start without
`/usr/lib/g510-lcd/fonts/lcd-label-8.fnt` (confirmed: `main()` prints
"failed to load custom font" and returns 1 if it's missing -- verified
directly against the actual built binary this pass, not assumed).
Requires manually converting your own copy post-install, same as the
git-clone flow -- except now targeting a root-owned directory, which
the git-clone flow doesn't require sudo for. A real regression in
convenience versus `install.sh`, worth fixing properly (e.g. checking
`~/.local/share/g510-lcd/fonts/` first) before any real release, not
silently accepted as fine.

## What's actually been verified this pass

1. `makepkg` against a real tarball -- both a manually-assembled one
   from the live working tree (for fast iteration while fixing a real
   bug below) and a genuine `git archive` of the `g510s-dev` branch
   HEAD (matching how `g910-control`'s README describes its own
   process, since neither app has a real public tag yet this can
   build from a real URL). Builds clean, no warnings.
2. Extracted the built `.pkg.tar.zst` and checked every substituted
   file by hand: the `/usr/bin/g510-lcd` wrapper, all three systemd
   service `ExecStart=` lines, and the udev rule (confirmed the
   backlight-restore `RUN+=` line is gone, confirmed the symlink and
   permission lines are byte-identical to the source rule).
3. Confirmed the compiled `g510_lcd_stats` binary really has
   `/usr/lib/g510-lcd` baked in (`strings` on the binary), and ran it
   directly -- it correctly looked for
   `/usr/lib/g510-lcd/fonts/lcd-label-8.fnt` and failed exactly the
   documented way (not some other, unexpected failure) when that path
   doesn't exist yet, which it won't until the package is actually
   installed.
4. Grepped every file in the built package (not just the source tree)
   for personal identifiers -- clean, except `.BUILDINFO`'s
   `builddir`/`startdir` fields, which record wherever a build
   happened to run (this test ran from a scratch directory under the
   user's home). Not a PKGBUILD defect -- a real AUR build (or even
   just building from `/tmp`) wouldn't show this; noted for honesty,
   not left silently unmentioned.

## What's NOT been verified (honest gaps, not glossed over)

- **Real install** (`sudo pacman -U`) -- blocked by this session's own
  permission system, needs the user directly. Once done: confirm
  `g510-lcd` actually launches from `/usr/bin/`, confirm the packaged
  systemd services can be started (`systemctl --user start
  --user-unit=... g510-lcd-stats.service` after temporarily removing
  the `~/.config/systemd/user/` override that currently makes the
  git-clone version win) without disrupting the live dev-checkout
  services in the meantime -- they were NOT started or enabled as
  part of this pass, specifically to avoid exactly that risk while
  testing.
- **`namcap`** -- not installed on this machine, lint step skipped
  entirely rather than assumed clean.
- **`sha256sums=SKIP`** -- same private-repo/no-public-tag situation
  documented in `G510_PLAN_A.md`'s Phase 4 section. Must become a real
  sum before any AUR submission.

## Before real AUR submission (not done, needs the user's go-ahead)

- The real install + service-start verification above.
- Fix the font-path convenience regression (check a user-writable
  location first).
- Solve or explicitly accept the backlight-restore-on-replug gap.
- Make the source repo public, compute a real `sha256sum`.
- Generate `.SRCINFO` (`makepkg --printsrcinfo > .SRCINFO`).
- Push to a dedicated `aur.archlinux.org` git remote.
