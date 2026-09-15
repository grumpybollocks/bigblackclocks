#!/usr/bin/env python3
"""
G510 LCD Control App.

Architecture: one QTabWidget, one tab per feature. Adding a new feature
= adding a new tab class + one line in MainWindow.__init__. Nothing in
an existing tab needs to change when a new one is added.

Phase 1: Backlight tab (color/brightness + service control).
         G-Keys tab (record/assign macros to G1-G18 per M1/M2/M3 profile).
Phase 2: Custom Screens tab (AIDA64-style sensor dashboard builder for
         the L2-L5 buttons, with a live preview of the real LCD output).
"""
import sys
import json
import subprocess
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QComboBox, QSlider, QPushButton, QLabel,
    QMessageBox, QDialog, QLineEdit, QSpinBox, QFrame, QScrollArea,
    QFileDialog,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect, QPoint
from PyQt5.QtGui import QImage, QPixmap, QColor, QPainter, QPen
import evdev
from evdev import ecodes

import g510_canvas

PROJECT_DIR = Path(__file__).resolve().parent.parent  # repo root (this file lives in src/)
LED_DIR = Path("/sys/class/leds/g15::kbd_backlight")
DEFAULTS_SCRIPT = PROJECT_DIR / "scripts" / "set-backlight-color.sh"
MAIN_KEYBOARD_DEVICE = "/dev/input/by-id/usb-Logitech_G510s_Gaming_Keyboard-event-kbd"
STATS_BINARY = PROJECT_DIR / "src" / "g510_lcd_stats"

# Your own macros/custom-screens config and imported images live under
# ~/.local/share/g510-lcd, independent of where the program itself is
# installed from (a dev checkout via install.sh, or a real package
# under a fixed /usr/lib/g510-lcd) -- so a package upgrade never
# touches what you've actually configured. Mirrors the identical
# data_dir()/migrate_*_if_needed() logic in g510_lcd_stats.c -- both
# sides need to agree on this path independently since the C binary
# and this GUI both read/write the same files without talking to each
# other directly.
DATA_DIR = Path.home() / ".local" / "share" / "g510-lcd"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_file_if_needed(old_path: Path, new_path: Path):
    if new_path.exists() or not old_path.exists():
        return
    new_path.write_bytes(old_path.read_bytes())


def _migrate_dir_if_needed(old_dir: Path, new_dir: Path):
    if not old_dir.is_dir():
        return
    new_dir.mkdir(parents=True, exist_ok=True)
    for f in old_dir.iterdir():
        if f.is_file():
            _migrate_file_if_needed(f, new_dir / f.name)


_migrate_file_if_needed(PROJECT_DIR / "custom_screens.txt", DATA_DIR / "custom_screens.txt")
_migrate_file_if_needed(PROJECT_DIR / "macros.json", DATA_DIR / "macros.json")
_migrate_dir_if_needed(PROJECT_DIR / "custom_screen_images", DATA_DIR / "custom_screen_images")

MACROS_FILE = DATA_DIR / "macros.json"
CUSTOM_SCREENS_FILE = DATA_DIR / "custom_screens.txt"
LCD_WIDTH = 160
LCD_HEIGHT = 43

# Shared dark theme, copied verbatim from the sibling G910 app's
# g910_app.py for visual consistency across the two projects.
STYLESHEET = """
QWidget {
    background-color: #17171a;
    color: #e4e4e7;
    font-family: sans-serif;
}
QTabWidget::pane {
    border: 1px solid #2a2a30;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background: #1e1e22;
    border: 1px solid #2a2a30;
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: #26262b;
    border-bottom-color: #26262b;
    color: white;
}
QPushButton {
    background-color: #26262b;
    border: 1px solid #34343a;
    border-radius: 6px;
    padding: 7px 10px;
    text-align: left;
}
QPushButton:hover {
    background-color: #302f36;
    border-color: #46454e;
}
QPushButton:checked {
    background-color: #3a6cc4;
    border-color: #5a8ce0;
    color: white;
}
QPushButton#Primary {
    background-color: #3a6cc4;
    border-color: #5a8ce0;
    color: white;
    text-align: center;
    font-weight: 600;
    padding: 9px 10px;
}
QPushButton#Primary:hover {
    background-color: #4a7cd4;
    border-color: #6a9cf0;
}
QLabel#Title {
    font-size: 15px;
    font-weight: 600;
    padding: 4px 2px 10px 2px;
}
QWidget#Panel {
    background-color: #1c1c20;
    border: 1px solid #2a2a30;
    border-radius: 8px;
}
QFrame#Separator {
    background-color: #2a2a30;
    border: none;
    max-width: 1px;
    min-width: 1px;
}
QLabel#Status {
    color: #9a9aa2;
    font-size: 11px;
    padding-top: 4px;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #34343a;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #5a8ce0;
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
}
QLineEdit {
    background-color: #1e1e22;
    border: 1px solid #34343a;
    border-radius: 4px;
    padding: 5px;
}
"""


def active_profile_file():
    import os
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return Path(runtime, "g510_macro_profile")

COLOR_RGB = {
    "Blue-Violet": (110, 0, 255),
    "Red": (255, 0, 0),
    "Green": (0, 255, 0),
    "Blue": (0, 0, 255),
    "Purple": (128, 0, 128),
    "Cyan": (0, 255, 255),
    "Orange": (255, 100, 0),
    "Pink": (255, 0, 150),
    "White": (255, 255, 255),
}


def read_current_rgb():
    try:
        r, g, b = (int(x) for x in (LED_DIR / "multi_intensity").read_text().split())
        return (r, g, b)
    except Exception:
        return None


def read_current_brightness_pct():
    try:
        val = int((LED_DIR / "brightness").read_text().strip())
        return round(val * 100 / 255)
    except Exception:
        return 100


def write_defaults_script(rgb, brightness_val):
    script = f"""#!/bin/bash
# Applies the chosen keyboard backlight color. Run automatically by
# 99-g510-lcd.rules whenever the LED device appears (boot or replug).
# Auto-updated by g510_app.py every time you click Apply or Set as Default.
echo {brightness_val} > /sys/class/leds/g15::kbd_backlight/brightness
echo "{rgb[0]} {rgb[1]} {rgb[2]}" > /sys/class/leds/g15::kbd_backlight/multi_intensity
"""
    DEFAULTS_SCRIPT.write_text(script)
    DEFAULTS_SCRIPT.chmod(0o755)


def apply_backlight(color_name, brightness_pct):
    """Writes the LED sysfs files AND rewrites set-backlight-color.sh so
    this becomes the new permanent boot default (matches the behavior
    already established by g510-backlight-apply.sh -- same contract)."""
    rgb = COLOR_RGB.get(color_name)
    if rgb is None:
        return False, f"Unknown color: {color_name}"
    brightness_val = round(brightness_pct * 255 / 100)
    try:
        (LED_DIR / "multi_intensity").write_text(f"{rgb[0]} {rgb[1]} {rgb[2]}")
        (LED_DIR / "brightness").write_text(str(brightness_val))
    except PermissionError as e:
        return False, f"Permission denied writing to {LED_DIR} -- check the udev rule (99-g510-lcd.rules) is installed: {e}"

    write_defaults_script(rgb, brightness_val)
    return True, None


def set_as_default(color_name, brightness_pct):
    """Persist-only: updates set-backlight-color.sh (the boot default)
    WITHOUT touching the live backlight right now -- distinct from
    Apply, which does both. Lets you keep previewing other colors live
    without losing a default you've already decided on."""
    rgb = COLOR_RGB.get(color_name)
    if rgb is None:
        return False, f"Unknown color: {color_name}"
    brightness_val = round(brightness_pct * 255 / 100)
    write_defaults_script(rgb, brightness_val)
    return True, None


ALL_SERVICES = [
    "g510-lcd-stats.service",
    "g510-lcd-buttons.service",
    "g510-macro-daemon.service",
]


def run_systemctl(action):
    try:
        subprocess.run(
            ["systemctl", "--user", action] + ALL_SERVICES,
            check=True, capture_output=True, text=True,
        )
        return True, None
    except subprocess.CalledProcessError as e:
        return False, e.stderr or str(e)


MACRO_RECORD_LED = Path("/sys/class/leds/g15::macro_record/brightness")


def read_macro_record_led():
    try:
        return int(MACRO_RECORD_LED.read_text().strip()) > 0
    except Exception:
        return False


def load_macros():
    if MACROS_FILE.exists():
        try:
            return json.loads(MACROS_FILE.read_text())
        except Exception:
            pass
    return {"M1": {}, "M2": {}, "M3": {}}


def save_macro(profile, gkey, value, kind="keys"):
    """kind is 'keys' (a ydotool key-sequence string) or 'command' (a
    shell command string). Stored as {"type": ..., "value": ...} --
    g510_macro_daemon.py checks 'type' to decide how to replay it."""
    macros = load_macros()
    macros.setdefault(profile, {})[gkey] = {"type": kind, "value": value}
    MACROS_FILE.write_text(json.dumps(macros, indent=2))


def clear_macro(profile, gkey):
    macros = load_macros()
    macros.setdefault(profile, {}).pop(gkey, None)
    MACROS_FILE.write_text(json.dumps(macros, indent=2))


class RecorderThread(QThread):
    """Captures real keystrokes from the main keyboard while recording,
    grabbing the device so they don't also leak into whatever window has
    focus. Emits the final ydotool-ready 'code:value code:value ...'
    string when stopped."""
    finished_recording = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._stop = False
        self._events = []

    def stop(self):
        self._stop = True

    def run(self):
        import select
        dev = evdev.InputDevice(MAIN_KEYBOARD_DEVICE)
        dev.grab()
        try:
            while not self._stop:
                # Poll with a short timeout instead of a blocking read --
                # read_loop() only checks _stop between events, so it can
                # hang forever if the user stops without pressing another
                # key. This checks _stop every 0.1s regardless.
                r, _, _ = select.select([dev.fd], [], [], 0.1)
                if not r:
                    continue
                for event in dev.read():
                    if event.type == ecodes.EV_KEY:
                        self._events.append(f"{event.code}:{event.value}")
        finally:
            dev.ungrab()
            dev.close()
        self.finished_recording.emit(" ".join(self._events))


class MacroRecordDialog(QDialog):
    def __init__(self, profile, gkey, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.gkey = gkey
        self.recorder = None
        self.recorded_sequence = None

        self.setWindowTitle(f"{profile} / {gkey}")
        layout = QVBoxLayout()

        macros = load_macros()
        existing = macros.get(profile, {}).get(gkey)
        if isinstance(existing, dict) and existing.get("type") == "command":
            status_text = f"Currently runs: {existing.get('value', '')}"
        elif existing:
            status_text = "Currently assigned (recorded keystrokes)."
        else:
            status_text = "Nothing assigned yet."
        self.status_label = QLabel(status_text)
        layout.addWidget(self.status_label)

        self.record_btn = QPushButton("Record")
        self.record_btn.clicked.connect(self.toggle_recording)
        layout.addWidget(self.record_btn)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.on_save)
        self.save_btn.setEnabled(False)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.on_clear)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("<b>Or run a command instead:</b>"))
        cmd_row = QHBoxLayout()
        self.command_edit = QLineEdit()
        self.command_edit.setPlaceholderText("e.g. notify-send hello")
        if isinstance(existing, dict) and existing.get("type") == "command":
            self.command_edit.setText(existing.get("value", ""))
        save_cmd_btn = QPushButton("Save Command")
        save_cmd_btn.clicked.connect(self.on_save_command)
        cmd_row.addWidget(self.command_edit)
        cmd_row.addWidget(save_cmd_btn)
        layout.addLayout(cmd_row)

        self.setLayout(layout)

    def toggle_recording(self):
        if self.recorder is None:
            self.status_label.setText("Recording... press your key combo, then click Stop.")
            self.record_btn.setText("Stop")
            self.recorder = RecorderThread()
            self.recorder.finished_recording.connect(self.on_recorded)
            self.recorder.start()
        else:
            self.record_btn.setEnabled(False)  # ignore clicks until the thread actually finishes
            self.status_label.setText("Stopping...")
            self.recorder.stop()

    def reject(self):
        if self.recorder is not None:
            self.recorder.stop()
            self.recorder.wait(2000)  # let it clean up (ungrab) before the dialog closes
        super().reject()

    def on_recorded(self, sequence):
        self.recorded_sequence = sequence
        if self.recorder is not None:
            # The signal can arrive just before Qt finishes tearing down
            # the OS thread -- wait() blocks until that's truly done
            # before we drop the last Python reference. Skipping this
            # causes "QThread: Destroyed while thread is still running"
            # and a hard process abort (confirmed -- this crashed twice).
            self.recorder.wait()
        self.recorder = None
        self.record_btn.setText("Record")
        self.record_btn.setEnabled(True)
        self.status_label.setText(f"Captured {len(sequence.split())} events. Click Save to keep it.")
        self.save_btn.setEnabled(bool(sequence))

    def on_save(self):
        if self.recorded_sequence:
            save_macro(self.profile, self.gkey, self.recorded_sequence, kind="keys")
        self.accept()

    def on_save_command(self):
        cmd = self.command_edit.text().strip()
        if cmd:
            save_macro(self.profile, self.gkey, cmd, kind="command")
        self.accept()

    def on_clear(self):
        clear_macro(self.profile, self.gkey)
        self.accept()


class KeyboardTab(QWidget):
    """Unified Backlight + G-Keys view: a real keyboard-shaped canvas
    (see g510_canvas.py) next to a control panel, same overall pattern
    as the sibling G910 app's canvas+sidebar layout -- adapted here for
    a single-zone backlight (one live color for the whole board, not
    per-key) and 18 G-keys instead of 9.

    G-keys on the canvas open the existing macro-record dialog
    unchanged; M1/M2/M3 switch the active profile unchanged; a poll
    timer keeps the canvas's active-M-key highlight and MR indicator in
    sync with the daemon/hardware, exactly like the old GKeysTab did."""
    def __init__(self):
        super().__init__()
        self.current_profile = "M1"

        root = QHBoxLayout()

        canvas_col = QVBoxLayout()
        self.canvas = g510_canvas.G510Canvas()
        current_rgb = read_current_rgb()
        if current_rgb:
            self.canvas.set_board_color(QColor(*current_rgb))
        self.canvas.gkey_clicked.connect(self.open_key_dialog)
        self.canvas.mkey_clicked.connect(self.select_profile)
        self.refresh_assigned_keys()
        canvas_col.addWidget(self.canvas)

        hint = QLabel("Click a G-key to record a macro  •  click M1/M2/M3 to switch profiles  •  gold border = macro assigned")
        hint.setObjectName("Status")
        canvas_col.addWidget(hint)
        canvas_col.addStretch()
        root.addLayout(canvas_col, stretch=1)

        panel = QWidget()
        panel.setObjectName("Panel")
        panel.setFixedWidth(220)
        panel_layout = QVBoxLayout()

        title = QLabel("Backlight")
        title.setObjectName("Title")
        panel_layout.addWidget(title)

        panel_layout.addWidget(QLabel("Color:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(COLOR_RGB.keys())
        for name, rgb in COLOR_RGB.items():
            if rgb == current_rgb:
                self.color_combo.setCurrentText(name)
                break
        panel_layout.addWidget(self.color_combo)

        panel_layout.addWidget(QLabel("Brightness:"))
        bright_row = QHBoxLayout()
        self.bright_slider = QSlider(Qt.Horizontal)
        self.bright_slider.setRange(0, 100)
        self.bright_slider.setValue(read_current_brightness_pct())
        self.bright_label = QLabel(f"{self.bright_slider.value()}%")
        self.bright_slider.valueChanged.connect(
            lambda v: self.bright_label.setText(f"{v}%")
        )
        bright_row.addWidget(self.bright_slider)
        bright_row.addWidget(self.bright_label)
        panel_layout.addLayout(bright_row)

        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("Primary")
        apply_btn.clicked.connect(self.on_apply)
        panel_layout.addWidget(apply_btn)
        set_default_btn = QPushButton("Set as Default")
        set_default_btn.clicked.connect(self.on_set_as_default)
        panel_layout.addWidget(set_default_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("Separator")
        panel_layout.addSpacing(10)
        panel_layout.addWidget(sep)
        panel_layout.addSpacing(10)

        panel_layout.addWidget(QLabel("Service Control"))
        start_btn = QPushButton("Start")
        start_btn.clicked.connect(lambda: self.on_service_action("start"))
        panel_layout.addWidget(start_btn)
        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(lambda: self.on_service_action("stop"))
        panel_layout.addWidget(stop_btn)
        restart_btn = QPushButton("Restart Service")
        restart_btn.clicked.connect(lambda: self.on_service_action("restart"))
        panel_layout.addWidget(restart_btn)

        panel_layout.addStretch()
        panel.setLayout(panel_layout)
        root.addWidget(panel)

        self.setLayout(root)

        # Physical M1/M2/M3 presses and the MR LED are hardware/daemon
        # state this GUI doesn't own -- poll and reflect them, same
        # pattern as the old GKeysTab's profile poll timer.
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_hardware_state)
        self.poll_timer.start(500)

    def select_profile(self, name):
        self.current_profile = name
        self.canvas.set_active_mkey(name)
        self.refresh_assigned_keys()
        # Real bug, found via live use: clicking M1/M2/M3 here used to
        # be GUI-only -- the daemon (which decides what a physical
        # G-key press actually replays) never learned about it, and
        # the poll below would revert the highlight right back within
        # 500ms. Writing the same file the daemon itself writes makes
        # this a real profile switch, not a cosmetic one -- and makes
        # this call idempotent when poll_hardware_state calls it after
        # reading an unchanged file (same value written back, harmless).
        try:
            active_profile_file().write_text(name)
        except Exception:
            pass  # matches the daemon's own best-effort LED write

    def refresh_assigned_keys(self):
        """Which G-keys have a macro in the CURRENT profile -- drawn
        with a gold border on the canvas so it's visible at a glance,
        without opening each key's dialog to check."""
        assigned = load_macros().get(self.current_profile, {}).keys()
        self.canvas.set_assigned_keys(assigned)

    def poll_hardware_state(self):
        try:
            live = active_profile_file().read_text().strip()
        except Exception:
            live = None
        if live in ("M1", "M2", "M3") and live != self.current_profile:
            self.select_profile(live)
        self.canvas.set_mr_active(read_macro_record_led())

    def open_key_dialog(self, gkey):
        dlg = MacroRecordDialog(self.current_profile, gkey, self)
        dlg.exec_()
        self.refresh_assigned_keys()  # a macro may have been saved or cleared

    def on_apply(self):
        ok, err = apply_backlight(self.color_combo.currentText(), self.bright_slider.value())
        if not ok:
            QMessageBox.critical(self, "Error", err)
            return
        rgb = COLOR_RGB[self.color_combo.currentText()]
        self.canvas.set_board_color(QColor(*rgb))

    def on_set_as_default(self):
        ok, err = set_as_default(self.color_combo.currentText(), self.bright_slider.value())
        if not ok:
            QMessageBox.critical(self, "Error", err)

    def on_service_action(self, action):
        ok, err = run_systemctl(action)
        if not ok:
            QMessageBox.critical(self, "Error", err)


# --- Custom Screens (v1.1): dashboards for L2-L5, mirrors the sensor
# table in g510_lcd_stats.c's SENSORS[] array. Keep the two in sync if a
# sensor is ever added or renamed -- there's no shared source of truth
# because one side is C and the other Python, by design (no JSON/IPC
# schema needed for something this small).
SENSOR_CHOICES = [
    ("CPU_PCT", "CPU %"),
    ("CPU_GHZ", "CPU GHz"),
    ("CPU_TEMP", "CPU Temp"),
    ("RAM_PCT", "RAM %"),
    ("RAM_AMOUNT", "RAM Used (amount)"),
    ("VRAM_PCT", "VRAM %"),
    ("VRAM_AMOUNT", "VRAM Used (amount)"),
    ("MAXTEMP", "Max Temp Seen"),
    ("GPU_PCT", "GPU %"),
    ("GPU_EDGE_TEMP", "GPU Edge Temp"),
    ("GPU_HOTSPOT_TEMP", "GPU Hotspot Temp"),
    ("GPU_VRAM_TEMP", "GPU VRAM Temp"),
    ("SWAP_PCT", "Swap %"),
    ("DISK_ROOT_PCT", "Disk % (root)"),
    ("DISK_FRIGIDER_PCT", "Disk % (frigider)"),
    ("UPTIME", "Uptime"),
    ("NET_DOWN", "Network Download Speed"),
    ("NET_UP", "Network Upload Speed"),
    ("TIME", "Time"),
    ("DATE", "Date"),
    ("MB_TEMP1", "Motherboard Temp 1 (unlabeled)"),
    ("MB_TEMP2", "Motherboard Temp 2 (unlabeled)"),
    ("MB_TEMP3", "Motherboard Temp 3 (unlabeled)"),
    ("MB_TEMP4", "Motherboard Temp 4 (unlabeled)"),
    ("MB_TEMP5", "Motherboard Temp 5 (unlabeled)"),
    ("MB_TEMP6", "Motherboard Temp 6 (unlabeled)"),
]
SENSOR_LABELS = dict(SENSOR_CHOICES)

# Only sensors with an honest 0-100 scale (a true percent, or a
# temperature via the 0-90C convention already used on the main stats
# screen) can be shown as a bar -- matches is_percent/is_temp in the C
# SENSORS[] table exactly. Anything else offered as "Bar" would need a
# guessed scale, which we don't do.
BAR_CAPABLE_SENSORS = {
    "CPU_PCT", "CPU_TEMP", "RAM_PCT", "VRAM_PCT", "MAXTEMP",
    "GPU_PCT", "GPU_EDGE_TEMP", "GPU_HOTSPOT_TEMP", "GPU_VRAM_TEMP",
    "SWAP_PCT", "DISK_ROOT_PCT", "DISK_FRIGIDER_PCT",
    "MB_TEMP1", "MB_TEMP2", "MB_TEMP3", "MB_TEMP4", "MB_TEMP5", "MB_TEMP6",
}

CUSTOM_SCREEN_KEYS = ["L2", "L3", "L4", "L5"]
# L1 is the built-in clock screen (drawn by draw_clock_screen() in C,
# not draw_custom_screen()) -- it has no ELEMENT lines of its own and
# was never meant to be edited here. Included in the tab's screen
# selector as a read-only preview only, per user request ("make a
# preview panel for L1 too") -- kept separate from CUSTOM_SCREEN_KEYS
# so load/save_custom_screens (which only know about real SCREEN
# blocks) are untouched.
SCREEN_PREVIEW_KEYS = ["L1"] + CUSTOM_SCREEN_KEYS


MAX_IMAGES_PER_SCREEN = 2  # matches MAX_IMAGES in g510_lcd_stats.c
CUSTOM_SCREEN_IMAGES_DIR = DATA_DIR / "custom_screen_images"


def load_custom_screens():
    """Returns {"L2": [ {kind:"sensor",sensor,style,x,y,width} or
    {kind:"image",path,x,y,width,height}, ... ], "L3": [...], ...}"""
    config = {k: [] for k in CUSTOM_SCREEN_KEYS}
    if not CUSTOM_SCREENS_FILE.exists():
        return config
    current = None
    for line in CUSTOM_SCREENS_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("SCREEN "):
            key = line.split(" ", 1)[1]
            current = key if key in config else None
        elif line.startswith("ELEMENT ") and current:
            el = {"kind": "sensor", "sensor": "", "style": "number", "x": 0, "y": 0, "width": 40}
            for tok in line[len("ELEMENT "):].split():
                if "=" not in tok:
                    continue
                k, v = tok.split("=", 1)
                if k in ("x", "y", "width"):
                    try:
                        el[k] = int(v)
                    except ValueError:
                        pass
                elif k in ("sensor", "style"):
                    el[k] = v
            if el["sensor"]:
                config[current].append(el)
        elif line.startswith("IMAGE ") and current:
            im = {"kind": "image", "path": "", "x": 0, "y": 0, "width": 0, "height": 0}
            for tok in line[len("IMAGE "):].split():
                if "=" not in tok:
                    continue
                k, v = tok.split("=", 1)
                if k in ("x", "y", "width", "height"):
                    try:
                        im[k] = int(v)
                    except ValueError:
                        pass
                elif k == "path":
                    im[k] = v
            if im["path"] and im["width"] > 0 and im["height"] > 0:
                config[current].append(im)
    return config


def save_custom_screens(config):
    lines = []
    for key in CUSTOM_SCREEN_KEYS:
        lines.append(f"SCREEN {key}")
        for el in config[key]:
            if el.get("kind") == "image":
                lines.append(
                    f"IMAGE path={el['path']} width={el['width']} height={el['height']} "
                    f"x={el['x']} y={el['y']}"
                )
            else:
                width = el.get("width", 40)
                lines.append(
                    f"ELEMENT sensor={el['sensor']} style={el['style']} "
                    f"x={el['x']} y={el['y']} width={width}"
                )
    CUSTOM_SCREENS_FILE.write_text("\n".join(lines) + "\n")


def _parse_bounds_meta(meta_path):
    """Parses the .meta sidecar --preview writes alongside the image for
    custom screens: real per-element pixel bounds computed with the
    label font's actual glyph metrics, which Python has no way to
    compute itself. Returns {index: {"label_x1":.., ..., "bar_x1":.. (bar
    elements only)}}. Missing/unreadable file -> empty dict, callers
    fall back to an approximation rather than crashing."""
    bounds = {}
    try:
        text = meta_path.read_text()
    except Exception:
        return bounds
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            idx = int(parts[0])
        except ValueError:
            continue
        entry = {}
        for tok in parts[1:]:
            if "=" not in tok:
                continue
            k, v = tok.split("=", 1)
            try:
                entry[k] = int(v)
            except ValueError:
                pass
        bounds[idx] = entry
    return bounds


def render_preview(screen_num):
    """Runs the same C binary that draws the real LCD, in one-shot
    --preview mode, and returns (QPixmap, bounds, err) -- the pixmap is
    guaranteed pixel-identical to what the real screen shows, since
    it's the same drawing code. bounds is real per-element pixel
    geometry (see _parse_bounds_meta), empty dict for non-custom
    screens or if the sidecar wasn't written."""
    if not STATS_BINARY.exists():
        return None, {}, "Not built yet -- run install.sh or rebuild the C programs."
    out_path = Path("/tmp/g510_app_preview.ppm")
    meta_path = Path(str(out_path) + ".meta")
    try:
        result = subprocess.run(
            [str(STATS_BINARY), "--preview", str(screen_num), str(out_path)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None, {}, f"Preview render failed: {result.stderr.strip()}"
    except Exception as e:
        return None, {}, f"Couldn't run preview: {e}"

    try:
        data = out_path.read_bytes()
    except Exception as e:
        return None, {}, f"Couldn't read preview output: {e}"

    # Minimal hand-rolled P6 PPM parser -- avoids depending on Qt's
    # optional ppm plugin being present on whatever system this runs on.
    if not data.startswith(b"P6"):
        return None, {}, "Preview output wasn't a valid PPM image."
    parts = data.split(b"\n", 3)
    if len(parts) < 4:
        return None, {}, "Malformed PPM header."
    try:
        w, h = (int(x) for x in parts[1].split())
    except ValueError:
        return None, {}, "Malformed PPM header."
    pixels = parts[3]
    img = QImage(w, h, QImage.Format_RGB888)
    if len(pixels) < w * h * 3:
        return None, {}, "Truncated PPM data."
    for y in range(h):
        row_start = y * w * 3
        img.scanLine(y)  # ensure detach
        for x in range(w):
            i = row_start + x * 3
            img.setPixel(x, y, (pixels[i] << 16) | (pixels[i + 1] << 8) | pixels[i + 2])
    bounds = _parse_bounds_meta(meta_path)
    return QPixmap.fromImage(img), bounds, None


PREVIEW_SCALE = 4
# Approximate click/drag hit box per element, in real LCD pixels (not
# scaled) -- there's no exact per-element width/height available from
# Python (the C renderer computes real text width using font metrics
# Python doesn't have access to), so this is a deliberately generous
# fixed size rather than pixel-perfect. Good enough to click and drag
# elements that are reasonably spaced, which is the normal case for an
# 8-element-max, 160x43 screen.
ELEMENT_HIT_W = 50
ELEMENT_HIT_H = 10
RESIZE_HANDLE_PX = 5   # half-size of the little resize square, in LCD px
MIN_BAR_WIDTH = 10
MAX_BAR_WIDTH = 140


class ScreenPreviewCanvas(QWidget):
    """The live LCD preview, but interactive: click and drag an element
    to move it, or drag its resize handle (bar elements only) to change
    the bar's length -- both re-render the preview (throttled) as you
    go, same underlying --preview mechanism as before, just wired to
    mouse events instead of typed X/Y/width numbers."""
    element_moved = pyqtSignal(int, int, int)   # index, new_x, new_y (LCD-space)
    element_resized = pyqtSignal(int, int)        # index, new_width (LCD-space)
    drag_started = pyqtSignal()
    drag_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._pixmap = None
        self._elements = []
        self._bounds = {}   # index -> real pixel geometry from the C renderer, see _parse_bounds_meta
        self._drag_index = None
        self._drag_offset = QPoint(0, 0)
        self._resize_index = None
        self._resize_start_x = 0
        self._resize_start_width = 0
        self._hover_index = None  # bar element the mouse is currently near -- only ITS handle is drawn
        self.setFixedSize(LCD_WIDTH * PREVIEW_SCALE, LCD_HEIGHT * PREVIEW_SCALE)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    def set_data(self, pixmap, elements, bounds=None):
        self._pixmap = pixmap
        self._elements = elements
        self._bounds = bounds or {}
        self.update()

    def _element_rect(self, index):
        el = self._elements[index]
        if el.get("kind") == "image":
            # Images know their own exact size (set once at import time
            # by png-to-lcd.py and never changes) -- no need for the
            # C-reported .meta bounds that sensor elements need, since
            # there's no font-metric unknown here.
            return QRect(el["x"] * PREVIEW_SCALE, el["y"] * PREVIEW_SCALE,
                         el["width"] * PREVIEW_SCALE, el["height"] * PREVIEW_SCALE)
        b = self._bounds.get(index)
        if b and "label_x1" in b:
            # Real geometry: covers the label through the end of the
            # bar (if any), so the whole visible element is grabbable,
            # not just an approximate box that might miss a long label
            # or a short/long bar.
            x1, y1 = b["label_x1"], b["label_y1"]
            x2 = b.get("bar_x2", b["label_x2"] + 30)  # +30 is a light pad for the value text on number-style, which has no measured width either
            y2 = max(b["label_y2"], b.get("bar_y2", 0))
            return QRect(x1 * PREVIEW_SCALE, y1 * PREVIEW_SCALE,
                         (x2 - x1) * PREVIEW_SCALE, (y2 - y1) * PREVIEW_SCALE)
        # Fallback for the brief window before the first real preview
        # has come back (or if the metadata sidecar is ever missing) --
        # approximate, not pixel-accurate, but never crashes.
        return QRect(
            el["x"] * PREVIEW_SCALE, el["y"] * PREVIEW_SCALE,
            ELEMENT_HIT_W * PREVIEW_SCALE, ELEMENT_HIT_H * PREVIEW_SCALE,
        )

    def _resize_handle_rect(self, index):
        el = self._elements[index]
        b = self._bounds.get(index)
        r = RESIZE_HANDLE_PX * PREVIEW_SCALE
        if b and "bar_x2" in b:
            # Exactly where the real bar ends -- this is the fix for
            # the handle drifting away from the actual bar, reported
            # directly as the preview being "hard to control."
            hx = b["bar_x2"] * PREVIEW_SCALE
            hy = ((b["bar_y1"] + b["bar_y2"]) * PREVIEW_SCALE) // 2
            return QRect(hx - r, hy - r, r * 2, r * 2)
        hx = el["x"] * PREVIEW_SCALE + ELEMENT_HIT_W * PREVIEW_SCALE
        hy = el["y"] * PREVIEW_SCALE + (ELEMENT_HIT_H * PREVIEW_SCALE) // 2
        return QRect(hx - r, hy - r, r * 2, r * 2)

    def _element_at(self, pos):
        # Last element in the list is drawn/added most recently -- check
        # in reverse so an overlapping newer element wins, matching what
        # you'd visually expect to grab.
        for i in range(len(self._elements) - 1, -1, -1):
            if self._element_rect(i).contains(pos):
                return i
        return None

    def _resize_handle_at(self, pos):
        for i in range(len(self._elements) - 1, -1, -1):
            el = self._elements[i]
            if el.get("style") == "bar" and self._resize_handle_rect(i).contains(pos):
                return i
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap is not None:
            painter.drawPixmap(0, 0, self._pixmap)
        # Only the bar you're actively resizing, or the one you're
        # currently hovering near, gets its handle drawn -- showing
        # every bar's handle at once (the original approach) cluttered
        # a screen this small badly enough to be reported directly as
        # confusing ("wtf are the blue squares for?").
        handle_owner = self._resize_index if self._resize_index is not None else self._hover_index
        if handle_owner is not None and 0 <= handle_owner < len(self._elements) \
                and self._elements[handle_owner].get("style") == "bar":
            painter.setPen(QPen(QColor(120, 120, 120), 1))
            painter.setBrush(QColor(70, 140, 230, 180))
            painter.drawRect(self._resize_handle_rect(handle_owner))
        active = self._drag_index if self._drag_index is not None else self._resize_index
        if active is not None:
            painter.setPen(QPen(QColor(70, 140, 230), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._element_rect(active))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        r_idx = self._resize_handle_at(event.pos())
        if r_idx is not None:
            self._resize_index = r_idx
            self._resize_start_x = event.pos().x()
            self._resize_start_width = self._elements[r_idx].get("width", 40)
            self.update()
            self.drag_started.emit()
            return
        idx = self._element_at(event.pos())
        if idx is None:
            return
        self._drag_index = idx
        el = self._elements[idx]
        el_pos = QPoint(el["x"] * PREVIEW_SCALE, el["y"] * PREVIEW_SCALE)
        self._drag_offset = event.pos() - el_pos
        self.update()
        self.drag_started.emit()

    def mouseMoveEvent(self, event):
        if self._resize_index is not None:
            self.setCursor(Qt.SizeHorCursor)
            delta = round((event.pos().x() - self._resize_start_x) / PREVIEW_SCALE)
            new_width = max(MIN_BAR_WIDTH, min(MAX_BAR_WIDTH, self._resize_start_width + delta))
            el = self._elements[self._resize_index]
            if el.get("width", 40) != new_width:
                el["width"] = new_width
                self.element_resized.emit(self._resize_index, new_width)
            self.update()
            return

        if self._drag_index is None:
            idx = self._element_at(event.pos())
            over_handle = self._resize_handle_at(event.pos()) is not None
            new_hover = idx if (idx is not None and self._elements[idx].get("style") == "bar") else None
            if new_hover != self._hover_index:
                self._hover_index = new_hover
                self.update()
            if over_handle:
                self.setCursor(Qt.SizeHorCursor)
            elif idx is not None:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            return
        self.setCursor(Qt.ClosedHandCursor)
        new_pos = event.pos() - self._drag_offset
        x = max(0, min(LCD_WIDTH - 1, round(new_pos.x() / PREVIEW_SCALE)))
        y = max(0, min(LCD_HEIGHT - 1, round(new_pos.y() / PREVIEW_SCALE)))
        el = self._elements[self._drag_index]
        if el["x"] != x or el["y"] != y:
            el["x"], el["y"] = x, y
            self.element_moved.emit(self._drag_index, x, y)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._resize_index is not None:
            self._resize_index = None
            self.setCursor(Qt.ArrowCursor)
            self.update()
            self.drag_finished.emit()
            return
        if self._drag_index is None:
            return
        self._drag_index = None
        self.setCursor(Qt.ArrowCursor)
        self.update()
        self.drag_finished.emit()

    def leaveEvent(self, event):
        if self._hover_index is not None:
            self._hover_index = None
            self.update()


class CustomScreensTab(QWidget):
    """AIDA64-style dashboard builder for the L2-L5 buttons. Pick a
    screen, add sensors with a display style, drag them into place on
    the live preview -- the preview is the real LCD-drawing code
    running in a one-shot mode, so what you see here is exactly what
    the keyboard will show."""
    def __init__(self):
        super().__init__()
        self.current_screen = "L2"
        self.config = load_custom_screens()

        root = QHBoxLayout()

        canvas_col = QVBoxLayout()
        canvas_col.setSpacing(6)

        screen_row = QHBoxLayout()
        screen_row.setSpacing(8)
        self.screen_buttons = {}
        for key in SCREEN_PREVIEW_KEYS:
            btn = QPushButton(key)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { font-weight: bold; padding: 4px 12px; text-align: center; }"
                "QPushButton:checked { background-color: #4a90d9; color: white; }"
            )
            btn.clicked.connect(lambda _, k=key: self.select_screen(k))
            screen_row.addWidget(btn)
            self.screen_buttons[key] = btn
        screen_row.addStretch()
        self.screen_buttons["L2"].setChecked(True)
        canvas_col.addLayout(screen_row)

        # Live, interactive preview -- scaled up 4x (160x43 -> 640x172)
        # so it's actually readable, tinted to match the real
        # green-on-black LCD. Elements are click-and-drag movable
        # directly on this; bar elements also get a small drag handle
        # to resize their length.
        self.preview_canvas = ScreenPreviewCanvas()
        self.preview_canvas.element_moved.connect(self.on_element_dragged)
        self.preview_canvas.element_resized.connect(self.on_element_resized)
        self.preview_canvas.drag_started.connect(self.on_drag_started)
        self.preview_canvas.drag_finished.connect(self.on_drag_finished)
        canvas_col.addWidget(self.preview_canvas)

        drag_hint = QLabel(
            "Drag an element or image to move it. Hover a bar to reveal its "
            "resize handle (right edge). Images resize by re-importing."
        )
        drag_hint.setWordWrap(True)
        drag_hint.setObjectName("Status")
        canvas_col.addWidget(drag_hint)
        canvas_col.addStretch()
        root.addLayout(canvas_col, stretch=1)

        panel = QWidget()
        panel.setObjectName("Panel")
        panel.setFixedWidth(230)
        panel_layout = QVBoxLayout()

        title = QLabel("Custom Screens")
        title.setObjectName("Title")
        panel_layout.addWidget(title)

        panel_layout.addWidget(QLabel("Add Element:"))
        self.sensor_combo = QComboBox()
        for key, label in SENSOR_CHOICES:
            self.sensor_combo.addItem(label, key)
        self.sensor_combo.currentIndexChanged.connect(self.on_sensor_changed)
        panel_layout.addWidget(self.sensor_combo)

        self.style_combo = QComboBox()
        self.style_combo.addItem("Number", "number")
        self.style_combo.addItem("Bar", "bar")
        panel_layout.addWidget(self.style_combo)

        self.bar_hint_label = QLabel(
            "No honest 0-100 scale for this sensor -- shows as a number."
        )
        self.bar_hint_label.setObjectName("Status")
        self.bar_hint_label.setWordWrap(True)
        self.bar_hint_label.hide()
        panel_layout.addWidget(self.bar_hint_label)

        self.add_btn = add_btn = QPushButton("Add")
        add_btn.setObjectName("Primary")
        add_btn.clicked.connect(self.on_add_element)
        panel_layout.addWidget(add_btn)

        self.import_image_btn = QPushButton("Import Image...")
        self.import_image_btn.clicked.connect(self.on_import_image)
        panel_layout.addWidget(self.import_image_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("Separator")
        panel_layout.addSpacing(6)
        panel_layout.addWidget(sep)
        panel_layout.addSpacing(6)

        panel_layout.addWidget(QLabel("Elements on this screen:"))
        # Fixed-height scroll area -- previously a long unbounded list
        # of elements would push the whole layout down past the
        # preview as you added more (reported directly: "if i add too
        # many items they just fall under the preview screen"). This
        # caps it so the window shape never depends on element count.
        elements_scroll = QScrollArea()
        elements_scroll.setWidgetResizable(True)
        elements_scroll.setFixedHeight(180)
        elements_scroll.setFrameShape(QFrame.NoFrame)
        elements_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        elements_container = QWidget()
        self.elements_layout = QVBoxLayout()
        self.elements_layout.setSpacing(2)
        self.elements_layout.setContentsMargins(0, 0, 0, 0)
        self.elements_layout.addStretch()
        elements_container.setLayout(self.elements_layout)
        elements_scroll.setWidget(elements_container)
        panel_layout.addWidget(elements_scroll)

        panel_layout.addStretch()
        panel.setLayout(panel_layout)
        root.addWidget(panel)

        self.setLayout(root)

        self.on_sensor_changed()
        self.refresh_elements_list()
        self.refresh_preview()

        # Keeps the preview live (matches the real daemon's own refresh
        # cadence for these screens) so it feels the same as watching
        # the actual keyboard.
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.refresh_preview)
        self.preview_timer.start(1000)

        # Separate, faster timer -- only running while actively
        # dragging -- so the preview visibly follows your mouse instead
        # of waiting up to a second for the next idle tick.
        self.drag_refresh_timer = QTimer(self)
        self.drag_refresh_timer.timeout.connect(self.refresh_preview)

    def select_screen(self, key):
        self.current_screen = key
        for k, btn in self.screen_buttons.items():
            btn.setChecked(k == key)
        editable = key != "L1"
        l1_reason = "L1 is the built-in clock -- it can't be edited." if not editable else ""
        self.sensor_combo.setEnabled(editable)
        self.sensor_combo.setToolTip(l1_reason)
        self.style_combo.setEnabled(editable)
        self.style_combo.setToolTip(l1_reason)
        self.add_btn.setEnabled(editable)
        self.add_btn.setToolTip(l1_reason)
        self.import_image_btn.setEnabled(editable)
        self.import_image_btn.setToolTip(l1_reason)
        self.refresh_elements_list()
        self.refresh_preview()

    def on_sensor_changed(self):
        sensor_key = self.sensor_combo.currentData()
        capable = sensor_key in BAR_CAPABLE_SENSORS
        self.bar_hint_label.setVisible(not capable)

    def screen_number(self):
        return int(self.current_screen[1])  # "L2" -> 2

    def on_add_element(self):
        if self.current_screen == "L1":
            return  # button is disabled for this case, this is just a safety guard
        elements = self.config[self.current_screen]
        sensor_count = sum(1 for el in elements if el.get("kind", "sensor") == "sensor")
        if sensor_count >= 8:
            QMessageBox.warning(self, "Screen full", "Each screen supports up to 8 sensor elements.")
            return
        # No X/Y fields anymore -- new elements land at a default spot
        # (stacked below whatever's already there) and you drag them
        # into their real place on the preview. y wraps back to the top
        # once it'd run off the bottom of the 43px screen, rather than
        # placing something permanently off-screen.
        default_y = (6 + 12 * sensor_count) % LCD_HEIGHT
        elements.append({
            "kind": "sensor",
            "sensor": self.sensor_combo.currentData(),
            "style": self.style_combo.currentData(),
            "x": 6,
            "y": default_y,
            "width": 40,
        })
        save_custom_screens(self.config)
        self.refresh_elements_list()
        self.refresh_preview()

    def on_import_image(self):
        if self.current_screen == "L1":
            return  # button is disabled for this case, this is just a safety guard
        elements = self.config[self.current_screen]
        image_count = sum(1 for el in elements if el.get("kind") == "image")
        if image_count >= MAX_IMAGES_PER_SCREEN:
            QMessageBox.warning(
                self, "Screen full",
                f"Each screen supports up to {MAX_IMAGES_PER_SCREEN} images -- "
                "the 160x43 screen is small, more than that rarely fits usefully anyway."
            )
            return

        src_path, _ = QFileDialog.getOpenFileName(
            self, "Choose an image", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)",
        )
        if not src_path:
            return

        CUSTOM_SCREEN_IMAGES_DIR.mkdir(exist_ok=True)
        # A stable, filesystem-safe name derived from the source file,
        # with a numeric suffix if that name's already taken -- so
        # re-importing the same file twice (or two different files with
        # the same name) doesn't silently clobber an existing one.
        stem = "".join(c if c.isalnum() else "_" for c in Path(src_path).stem) or "image"
        out_path = CUSTOM_SCREEN_IMAGES_DIR / f"{stem}.bin"
        n = 1
        while out_path.exists():
            out_path = CUSTOM_SCREEN_IMAGES_DIR / f"{stem}_{n}.bin"
            n += 1

        # No manual crop/resize UI -- trust png-to-lcd.py's own
        # automatic resize + dithering (already Floyd-Steinberg,
        # confirmed the right algorithm for this), matching the user's
        # own stated preference for "minimum necessary" over a fiddly
        # editor. 60px is a reasonable default max width for a 160px
        # screen that likely also has sensor elements on it.
        max_width = 60
        png_to_lcd = PROJECT_DIR / "src" / "png-to-lcd.py"
        try:
            result = subprocess.run(
                [sys.executable, str(png_to_lcd), src_path, str(out_path), str(max_width), str(LCD_HEIGHT)],
                capture_output=True, text=True, timeout=15,
            )
        except Exception as e:
            QMessageBox.critical(self, "Import failed", f"Couldn't run the converter: {e}")
            return
        if result.returncode != 0:
            QMessageBox.critical(self, "Import failed", result.stderr.strip() or "Unknown error converting the image.")
            return
        try:
            w, h = (int(x) for x in result.stdout.split())
        except ValueError:
            QMessageBox.critical(self, "Import failed", f"Unexpected converter output: {result.stdout!r}")
            return

        # Stagger the default drop spot by how many images are already on
        # this screen (mirrors on_add_element's default_y wrap for sensors)
        # -- otherwise a second import lands exactly on top of the first,
        # invisible until you notice and drag the top one out of the way.
        default_x = min(6 + 20 * image_count, max(0, LCD_WIDTH - w))
        default_y = min(6 + 15 * image_count, max(0, LCD_HEIGHT - h))
        elements.append({
            "kind": "image",
            "path": f"custom_screen_images/{out_path.name}",  # relative -- matches how the C side resolves it against data_dir()
            "x": default_x, "y": default_y,
            "width": w, "height": h,
        })
        save_custom_screens(self.config)
        self.refresh_elements_list()
        self.refresh_preview()

    def on_remove_element(self, index):
        del self.config[self.current_screen][index]
        save_custom_screens(self.config)
        self.refresh_elements_list()
        self.refresh_preview()

    def on_element_dragged(self, index, x, y):
        # Called continuously while dragging. Saving here (a cheap text
        # write, not the render itself) is what actually makes the live
        # preview live -- render_preview() runs the real C binary,
        # which reads custom_screens.txt fresh from disk every time.
        # Without saving mid-drag, the drag_refresh_timer's periodic
        # refresh_preview() calls kept re-rendering the OLD saved
        # position the whole time you were dragging -- only the dashed
        # selection outline moved with the mouse, the actual rendered
        # bar/label stayed frozen until release. Real bug, reported
        # directly as the preview being "hard to control."
        save_custom_screens(self.config)
        self.refresh_elements_list()

    def on_element_resized(self, index, width):
        # Same idea and same fix as on_element_dragged.
        save_custom_screens(self.config)
        self.refresh_elements_list()

    def on_drag_started(self):
        self.drag_refresh_timer.start(120)

    def on_drag_finished(self):
        self.drag_refresh_timer.stop()
        save_custom_screens(self.config)
        self.refresh_preview()  # one final, accurate, untimed refresh

    def refresh_elements_list(self):
        # Clear everything including the trailing stretch, then rebuild
        # it fresh each time -- simplest way to keep the stretch at the
        # end regardless of how many rows there are now.
        while self.elements_layout.count():
            item = self.elements_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self.current_screen == "L1":
            info = QLabel("L1 is the built-in clock screen -- shown here for reference, not editable.")
            info.setWordWrap(True)
            info.setObjectName("Status")
            self.elements_layout.addWidget(info)
            self.elements_layout.addStretch()
            return

        elements = self.config[self.current_screen]
        if not elements:
            self.elements_layout.addWidget(QLabel("Nothing on this screen yet."))
            self.elements_layout.addStretch()
            return
        for i, el in enumerate(elements):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            # Position/width shown on the canvas itself now (drag to
            # move, drag the handle to resize) -- repeating exact
            # coordinates here just made rows overflow the narrow panel
            # and need a horizontal scrollbar, so this stays short.
            if el.get("kind") == "image":
                name = Path(el["path"]).stem
                text = QLabel(f"Image: {name}")
                text.setToolTip(f"x={el['x']} y={el['y']} {el['width']}x{el['height']}px")
            else:
                label = SENSOR_LABELS.get(el["sensor"], el["sensor"])
                text = QLabel(f"{label} – {el['style']}")
                text.setToolTip(f"x={el['x']} y={el['y']}" + (f" width={el.get('width', 40)}" if el.get("style") == "bar" else ""))
            text.setStyleSheet("font-size: 11px;")
            row.addWidget(text)
            row.addStretch()
            remove_btn = QPushButton("✕")
            remove_btn.setFixedWidth(24)
            remove_btn.setStyleSheet("padding: 1px;")
            remove_btn.clicked.connect(lambda _, idx=i: self.on_remove_element(idx))
            row.addWidget(remove_btn)
            container = QWidget()
            container.setLayout(row)
            self.elements_layout.addWidget(container)
        self.elements_layout.addStretch()

    def refresh_preview(self):
        pixmap, bounds, err = render_preview(self.screen_number())
        if pixmap is None:
            print(f"Custom Screens preview error: {err}")  # surfaced in the panel below instead of blocking the canvas
            return
        scaled = pixmap.scaled(
            LCD_WIDTH * PREVIEW_SCALE, LCD_HEIGHT * PREVIEW_SCALE,
            Qt.KeepAspectRatio, Qt.FastTransformation,
        )
        elements = self.config.get(self.current_screen, [])  # L1 isn't a key in self.config -- no draggable elements there
        self.preview_canvas.set_data(scaled, elements, bounds)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G510 LCD Control")
        self.setStyleSheet(STYLESHEET)

        tabs = QTabWidget()
        tabs.addTab(KeyboardTab(), "Backlight + G-Keys")
        tabs.addTab(CustomScreensTab(), "Custom Screens (WIP)")
        self.setCentralWidget(tabs)

        # A hardcoded resize() goes stale the moment tab content's
        # natural size differs (bit us on the sibling G910 app) --
        # adjustSize() sizes the window to what's actually in it.
        self.adjustSize()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
