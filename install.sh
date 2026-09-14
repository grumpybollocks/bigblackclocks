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
sudo pacman -S --needed --noconfirm yad python-pyqt5 python-pillow ydotool python-evdev freetype2

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
gcc $(pkg-config --cflags freetype2) -DPROJECT_DIR="\"$DIR\"" src/g510_lcd_stats.c -o src/g510_lcd_stats -lg15render $(pkg-config --libs freetype2)
gcc src/g510_lcd_buttons.c -o src/g510_lcd_buttons

echo "=== 4/6: udev rules + hwdb (needs sudo) ==="
# The checked-in rule has a __PROJECT_DIR__ placeholder instead of a
# real path (same reasoning as -DPROJECT_DIR above) -- substitute it
# here rather than committing any one checkout's location.
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
for f in "G510 LCD - App" "G510 LCD - Rebuild" "G510 LCD - Start" "G510 LCD - View Logs" "G510 LCD - Project Folder"; do
    if [ -f "$HOME/Desktop/$f.desktop" ]; then
        chmod +x "$HOME/Desktop/$f.desktop"
    fi
done

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
