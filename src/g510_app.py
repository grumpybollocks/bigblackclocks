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
    QMessageBox, QDialog, QLineEdit, QSpinBox, QFrame,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QImage, QPixmap, QColor
import evdev
from evdev import ecodes

import g510_canvas

PROJECT_DIR = Path(__file__).resolve().parent.parent  # repo root (this file lives in src/)
LED_DIR = Path("/sys/class/leds/g15::kbd_backlight")
DEFAULTS_SCRIPT = PROJECT_DIR / "scripts" / "set-backlight-color.sh"
MACROS_FILE = PROJECT_DIR / "macros.json"
MAIN_KEYBOARD_DEVICE = "/dev/input/by-id/usb-Logitech_G510s_Gaming_Keyboard-event-kbd"
STATS_BINARY = PROJECT_DIR / "src" / "g510_lcd_stats"
CUSTOM_SCREENS_FILE = PROJECT_DIR / "custom_screens.txt"
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

        self.canvas = g510_canvas.G510Canvas()
        current_rgb = read_current_rgb()
        if current_rgb:
            self.canvas.set_board_color(QColor(*current_rgb))
        self.canvas.gkey_clicked.connect(self.open_key_dialog)
        self.canvas.mkey_clicked.connect(self.select_profile)
        self.refresh_assigned_keys()
        root.addWidget(self.canvas, stretch=1)

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
    ("VRAM_PCT", "VRAM %"),
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


def load_custom_screens():
    """Returns {"L2": [ {sensor,style,x,y}, ... ], "L3": [...], ...}"""
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
            el = {"sensor": "", "style": "number", "x": 0, "y": 0}
            for tok in line[len("ELEMENT "):].split():
                if "=" not in tok:
                    continue
                k, v = tok.split("=", 1)
                if k in ("x", "y"):
                    try:
                        el[k] = int(v)
                    except ValueError:
                        pass
                elif k in ("sensor", "style"):
                    el[k] = v
            if el["sensor"]:
                config[current].append(el)
    return config


def save_custom_screens(config):
    lines = []
    for key in CUSTOM_SCREEN_KEYS:
        lines.append(f"SCREEN {key}")
        for el in config[key]:
            lines.append(f"ELEMENT sensor={el['sensor']} style={el['style']} x={el['x']} y={el['y']}")
    CUSTOM_SCREENS_FILE.write_text("\n".join(lines) + "\n")


def render_preview(screen_num):
    """Runs the same C binary that draws the real LCD, in one-shot
    --preview mode, and returns a QPixmap -- guaranteed pixel-identical
    to what the real screen shows, since it's the same drawing code."""
    if not STATS_BINARY.exists():
        return None, "Not built yet -- run install.sh or rebuild the C programs."
    out_path = Path("/tmp/g510_app_preview.ppm")
    try:
        result = subprocess.run(
            [str(STATS_BINARY), "--preview", str(screen_num), str(out_path)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None, f"Preview render failed: {result.stderr.strip()}"
    except Exception as e:
        return None, f"Couldn't run preview: {e}"

    try:
        data = out_path.read_bytes()
    except Exception as e:
        return None, f"Couldn't read preview output: {e}"

    # Minimal hand-rolled P6 PPM parser -- avoids depending on Qt's
    # optional ppm plugin being present on whatever system this runs on.
    if not data.startswith(b"P6"):
        return None, "Preview output wasn't a valid PPM image."
    parts = data.split(b"\n", 3)
    if len(parts) < 4:
        return None, "Malformed PPM header."
    try:
        w, h = (int(x) for x in parts[1].split())
    except ValueError:
        return None, "Malformed PPM header."
    pixels = parts[3]
    img = QImage(w, h, QImage.Format_RGB888)
    if len(pixels) < w * h * 3:
        return None, "Truncated PPM data."
    for y in range(h):
        row_start = y * w * 3
        img.scanLine(y)  # ensure detach
        for x in range(w):
            i = row_start + x * 3
            img.setPixel(x, y, (pixels[i] << 16) | (pixels[i + 1] << 8) | pixels[i + 2])
    return QPixmap.fromImage(img), None


class CustomScreensTab(QWidget):
    """AIDA64-style dashboard builder for the L2-L5 buttons. Pick a
    screen, add sensors with a display style and position, see the
    result live -- the preview is the real LCD-drawing code running in
    a one-shot mode, so what you see here is exactly what the keyboard
    will show."""
    def __init__(self):
        super().__init__()
        self.current_screen = "L2"
        self.config = load_custom_screens()

        layout = QVBoxLayout()
        layout.addWidget(QLabel("<b>Custom Screens</b> (L2-L5 buttons)"))

        screen_row = QHBoxLayout()
        screen_row.setSpacing(24)
        screen_row.addStretch()
        self.screen_buttons = {}
        for key in CUSTOM_SCREEN_KEYS:
            btn = QPushButton(key)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { font-weight: bold; font-size: 14px; padding: 6px 14px; }"
                "QPushButton:checked { background-color: #4a90d9; color: white; }"
            )
            btn.clicked.connect(lambda _, k=key: self.select_screen(k))
            screen_row.addWidget(btn)
            self.screen_buttons[key] = btn
        screen_row.addStretch()
        self.screen_buttons["L2"].setChecked(True)
        layout.addLayout(screen_row)

        # Live preview -- scaled up 4x (160x43 -> 640x172) so it's
        # actually readable, tinted to match the real green-on-black LCD.
        self.preview_label = QLabel("Preview loading...")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setFixedSize(LCD_WIDTH * 4, LCD_HEIGHT * 4)
        self.preview_label.setStyleSheet("background-color: #bed691; border: 1px solid #555;")
        preview_row = QHBoxLayout()
        preview_row.addStretch()
        preview_row.addWidget(self.preview_label)
        preview_row.addStretch()
        layout.addLayout(preview_row)

        layout.addWidget(self._hline())

        layout.addWidget(QLabel("<b>Add Element</b>"))
        form_row = QHBoxLayout()
        self.sensor_combo = QComboBox()
        for key, label in SENSOR_CHOICES:
            self.sensor_combo.addItem(label, key)
        self.sensor_combo.currentIndexChanged.connect(self.on_sensor_changed)
        form_row.addWidget(self.sensor_combo)

        self.style_combo = QComboBox()
        self.style_combo.addItem("Number", "number")
        self.style_combo.addItem("Bar", "bar")
        form_row.addWidget(self.style_combo)

        form_row.addWidget(QLabel("X:"))
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, LCD_WIDTH - 1)
        self.x_spin.setValue(6)
        form_row.addWidget(self.x_spin)

        form_row.addWidget(QLabel("Y:"))
        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, LCD_HEIGHT - 1)
        self.y_spin.setValue(3)
        form_row.addWidget(self.y_spin)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.on_add_element)
        form_row.addWidget(add_btn)
        layout.addLayout(form_row)

        self.bar_hint_label = QLabel(
            "Bar isn't available for this sensor (no honest 0-100 scale) -- it'll show as a number."
        )
        self.bar_hint_label.setStyleSheet("color: #888; font-style: italic;")
        self.bar_hint_label.hide()
        layout.addWidget(self.bar_hint_label)

        layout.addWidget(QLabel("<b>Elements on this screen</b>"))
        self.elements_layout = QVBoxLayout()
        layout.addLayout(self.elements_layout)

        layout.addStretch()
        self.setLayout(layout)

        self.on_sensor_changed()
        self.refresh_elements_list()
        self.refresh_preview()

        # Keeps the preview live (matches the real daemon's own refresh
        # cadence for these screens) so it feels the same as watching
        # the actual keyboard.
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.refresh_preview)
        self.preview_timer.start(1000)

    def _hline(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def select_screen(self, key):
        self.current_screen = key
        for k, btn in self.screen_buttons.items():
            btn.setChecked(k == key)
        self.refresh_elements_list()
        self.refresh_preview()

    def on_sensor_changed(self):
        sensor_key = self.sensor_combo.currentData()
        capable = sensor_key in BAR_CAPABLE_SENSORS
        self.bar_hint_label.setVisible(not capable)

    def screen_number(self):
        return int(self.current_screen[1])  # "L2" -> 2

    def on_add_element(self):
        elements = self.config[self.current_screen]
        if len(elements) >= 8:
            QMessageBox.warning(self, "Screen full", "Each screen supports up to 8 elements.")
            return
        elements.append({
            "sensor": self.sensor_combo.currentData(),
            "style": self.style_combo.currentData(),
            "x": self.x_spin.value(),
            "y": self.y_spin.value(),
        })
        save_custom_screens(self.config)
        self.refresh_elements_list()
        self.refresh_preview()

    def on_remove_element(self, index):
        del self.config[self.current_screen][index]
        save_custom_screens(self.config)
        self.refresh_elements_list()
        self.refresh_preview()

    def refresh_elements_list(self):
        while self.elements_layout.count():
            item = self.elements_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        elements = self.config[self.current_screen]
        if not elements:
            self.elements_layout.addWidget(QLabel("Nothing on this screen yet."))
            return
        for i, el in enumerate(elements):
            row = QHBoxLayout()
            label = SENSOR_LABELS.get(el["sensor"], el["sensor"])
            row.addWidget(QLabel(f"{label} - {el['style']} @ ({el['x']}, {el['y']})"))
            row.addStretch()
            remove_btn = QPushButton("Remove")
            remove_btn.clicked.connect(lambda _, idx=i: self.on_remove_element(idx))
            row.addWidget(remove_btn)
            container = QWidget()
            container.setLayout(row)
            self.elements_layout.addWidget(container)

    def refresh_preview(self):
        pixmap, err = render_preview(self.screen_number())
        if pixmap is None:
            self.preview_label.setText(err or "Preview unavailable.")
            return
        scaled = pixmap.scaled(
            LCD_WIDTH * 4, LCD_HEIGHT * 4, Qt.KeepAspectRatio, Qt.FastTransformation
        )
        self.preview_label.setPixmap(scaled)


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
