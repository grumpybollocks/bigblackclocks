# Portability

How this repo answers "if someone else uses this app, how does it figure
out its own paths?" — what's already solid, what's a known gap, and why.

## The short version

Neither app hardcodes a username, hostname, or checkout location
anywhere in the actual source/config that ships. Every install script
resolves its own real location at run time (`DIR="$(cd "$(dirname
"$0")" && pwd)"`) and either substitutes that into a checked-in
`__PROJECT_DIR__` placeholder (systemd service files, the G510s udev
rule) or passes it to the C compiler as `-DPROJECT_DIR` (G510s's LCD
program, with a compile-time `#error` if that flag is ever missing —
no silent wrong-path fallback). Both install scripts also generate
their own desktop launchers fresh from the real resolved path, rather
than assuming one already exists.

## What each install script actually does

Both `install.sh` (G510s) and `install-g910.sh` (G910):
1. Resolve their own real location (`$DIR`), independent of where the
   repo was cloned.
2. Check each dependency's install status first and report it
   (`[ok]`/`[missing]`) before touching the system — never a silent
   `pacman -S` black box.
3. Install only what's actually missing.
4. Prompt/exit with a clear message instead of guessing when something
   genuinely can't be auto-determined (no AUR helper found, for
   example) — see each script's own comments for the specific cases.
5. Substitute `__PROJECT_DIR__`/pass `-DPROJECT_DIR` into every
   checked-in service file, udev rule, and C source that needs to know
   where it's actually installed.
6. Generate a desktop launcher fresh, written to BOTH `~/Desktop` (a
   literal desktop icon) and `~/.local/share/applications` (the
   standard XDG location every desktop environment's actual app menu
   reads — several DEs, GNOME notably, don't show desktop icons at
   all by default, so relying on `~/Desktop` alone would make the app
   undiscoverable there regardless of path-correctness).

## Status

**G910**: done and verified this pass — every hardcoded path found
(`services/g910-macro-daemon.service` still had one from before this
repo's `main`-branch cleanup) fixed and re-verified live: ran
`install-g910.sh` for real on this machine, confirmed the generated
systemd service correctly contains this machine's real path (not a
placeholder, not a stale one), the daemon is active, and both desktop
files were generated identically and correctly.

**G510s**: audited, real gaps found, not yet fixed (tracked as the
next piece of this work, done on the machine with that hardware):
- `install.sh`'s desktop-shortcut step only `chmod +x`'s files that
  must already exist by hand — unlike G910's installer, it never
  generates them. A genuinely fresh clone gets zero desktop icons.
- `scripts/start.sh` calls `zenity`, which `install.sh` never installs.
- Same "also write to `~/.local/share/applications`" gap as G910 had.

## Researched against a real reference, not guessed

Checked `pacman -Ql solaar` — a real, actively-maintained, officially
Arch-packaged Logitech device manager already installed on this
machine, same problem domain (Logitech HID++ device control, PyQt-
based GUI, needs a udev rule). Its actual installed layout — `/usr/bin/
solaar`, `/usr/lib/udev/rules.d/`, `/usr/share/applications/
solaar.desktop`, Python source under `/usr/lib/python3.*/
site-packages/` — confirmed the standard, professional pattern: a real
system package installs everything to fixed locations at build time,
so there's no per-user path to discover at runtime at all. The
`__PROJECT_DIR__`-templating this repo does today is the right answer
for a "git clone + run install.sh" install; a real AUR package
(PKGBUILD per app, `/usr/lib/systemd/user/` for the service units,
`/usr/lib/udev/rules.d/` for the udev rule, pacman's own `depends=`
handling dependency resolution instead of a hand-rolled script) is the
next step under consideration, not yet started.
