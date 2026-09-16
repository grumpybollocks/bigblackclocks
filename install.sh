#!/bin/bash
# Full setup for the G510s LCD project on a fresh Manjaro/Arch install.
# Run this from inside the project folder: ./install.sh
#
# Installs every dependency this project needs, puts the system files
# (udev rules, hwdb remap, systemd services) in place, and compiles the
# C programs. Safe to re-run any time -- every step just overwrites/
# re-applies, nothing accumulates.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== 1/6: Official repo packages ==="
sudo pacman -S --needed --noconfirm yad python-pyqt5 python-pillow ydotool python-evdev freetype2 zenity

echo "=== 2/6: AUR packages (libg15, libg15render -- needs yay) ==="
if ! command -v yay &>/dev/null; then
    echo "yay not found. Install an AUR helper first, then re-run this script."
    echo "(https://github.com/Jguer/yay -- or use paru/whatever you prefer, just"
    echo " make sure libg15 and libg15render end up installed.)"
    exit 1
fi
yay -S --needed --noconfirm libg15 libg15render

echo "=== 3/6: Compile the C programs ==="
# g510_lcd_stats needs the same FreeType/TTF flags libg15render.so itself
# was built with -- without them, g15canvas's struct layout mismatches
# between this program and the library, corrupting stack memory (this
# bit us once already while building v1.1; caught via AddressSanitizer).
# -DPROJECT_DIR bakes in THIS checkout's absolute path so the binary
# can find its own font/config files without any file in the repo
# itself hardcoding a username or machine-specific location.
gcc $(pkg-config --cflags freetype2) -DPROJECT_DIR="\"$DIR\"" src/g510_lcd_stats.c -o src/g510_lcd_stats -lg15render $(pkg-config --libs freetype2) -lm
gcc src/g510_lcd_buttons.c -o src/g510_lcd_buttons

echo "=== 4/6: udev rules + hwdb (needs sudo) ==="
# The backlight-restore-on-hotplug script needs a fixed system location
# udev can always find regardless of where this checkout lives (root,
# no per-user $HOME to resolve at hotplug time) -- installed here
# rather than referenced via a __PROJECT_DIR__ placeholder, and at the
# exact same path the PKGBUILD installs it to, so the udev rule itself
# never needs to know which install method put it there.
sudo mkdir -p /usr/lib/g510-lcd
sudo cp scripts/restore-backlight.sh /usr/lib/g510-lcd/restore-backlight.sh
sudo chmod 755 /usr/lib/g510-lcd/restore-backlight.sh
# The checked-in rule no longer has any __PROJECT_DIR__ placeholder to
# substitute (the one that used to need it, the backlight-restore
# line, now points at the fixed path above) -- this sed is harmless
# insurance, not load-bearing, in case that ever changes again.
sed "s|__PROJECT_DIR__|$DIR|g" udev/99-g510-lcd.rules | sudo tee /etc/udev/rules.d/99-g510-lcd.rules > /dev/null
sudo cp udev/91-g510-stop-to-playpause.hwdb /etc/udev/hwdb.d/91-g510-stop-to-playpause.hwdb
sudo udevadm control --reload-rules
sudo systemd-hwdb update
echo "NOTE: unplug and replug the keyboard now so these fully apply."
read -p "Press Enter once you've replugged the keyboard..."

echo "=== 5/6: systemd --user services ==="
mkdir -p ~/.config/systemd/user
for svc in g510-lcd-stats g510-lcd-buttons g510-macro-daemon; do
    sed "s|__PROJECT_DIR__|$DIR|g" "services/$svc.service" > ~/.config/systemd/user/"$svc.service"
done
systemctl --user daemon-reload
systemctl --user enable --now ydotool.service
systemctl --user enable --now g510-lcd-stats.service g510-lcd-buttons.service g510-macro-daemon.service

echo "=== 6/6: Desktop shortcuts ==="
# Generated fresh from the resolved $DIR every run -- a clean clone used to
# get zero shortcuts here (this step only chmod'd ones that had to already
# exist by hand). Written to BOTH ~/Desktop and ~/.local/share/applications:
# several desktop environments (GNOME notably) don't show desktop icons by
# default at all, so ~/Desktop alone leaves the app menu with nothing.
# Pattern matches the G910 sibling app's install-g910.sh, already verified
# working there.
mkdir -p "$HOME/Desktop" "$HOME/.local/share/applications"

write_shortcut() {
    # $1=display name  $2=xdg filename stem  $3=Comment  $4=Exec  $5=Icon
    local entry="[Desktop Entry]
Type=Application
Name=$1
Comment=$3
Exec=$4
Icon=$5
Terminal=false
Categories=Utility;"
    echo "$entry" > "$HOME/Desktop/$1.desktop"
    chmod +x "$HOME/Desktop/$1.desktop"
    command -v gio &>/dev/null && gio set "$HOME/Desktop/$1.desktop" metadata::trusted true 2>/dev/null || true

    echo "$entry" > "$HOME/.local/share/applications/$2.desktop"
    chmod +x "$HOME/.local/share/applications/$2.desktop"
}

write_shortcut "G510 LCD - App" "g510-lcd-app" \
    "G510 keyboard LCD control app (backlight, service control)" \
    "python3 \"$DIR/src/g510_app.py\"" "preferences-desktop-color"

write_shortcut "G510 LCD - Rebuild" "g510-lcd-rebuild" \
    "Recompile the keyboard LCD program after editing and restart it" \
    "konsole --noclose -e \"$DIR/scripts/rebuild.sh\"" "utilities-terminal"

write_shortcut "G510 LCD - Start" "g510-lcd-start" \
    "One-click start for the keyboard LCD screen and button services" \
    "\"$DIR/scripts/start.sh\"" "media-playback-start"

write_shortcut "G510 LCD - View Logs" "g510-lcd-view-logs" \
    "Watch live logs from the keyboard LCD screen and button services" \
    "konsole --noclose -e \"$DIR/scripts/view-logs.sh\"" "utilities-terminal"

write_shortcut "G510 LCD - Project Folder" "g510-lcd-project-folder" \
    "Open the keyboard LCD project source and files" \
    "dolphin \"$DIR\"" "folder"

echo ""
echo "=== Done -- one manual step left ==="
echo "This project doesn't include the Eurostile Bold font (commercial"
echo "license, can't redistribute it). Without it, the LCD label font"
echo "won't load. Get your own copy, then run:"
echo "  g15fontconvert -s 8 -i /path/to/Euro_Bold.otf -o fonts/lcd-label-8.fnt"
echo ""
echo "Also can't be scripted: Brave's 'Plasma Integration' extension"
echo "media-control feature needs to be manually disabled if you use"
echo "Brave + media keys together (see G510_README.md, MEDIA KEYS FIX #2)."
echo ""
systemctl --user status g510-lcd-stats.service g510-lcd-buttons.service g510-macro-daemon.service --no-pager -l | head -30
