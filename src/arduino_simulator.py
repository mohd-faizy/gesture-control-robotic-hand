"""
Virtual Arduino Uno & 5-DOF Robotic Hand Simulator
Provides real-time AVR serial protocol emulation, kinematics animation,
and graphical visualization for Arduino-less testing and demonstration.
"""

import os
import json
import time
import math
import cv2
import numpy as np


def _load_gesture_names():
    """Loads gesture name mappings from gesture_presets.json."""
    module_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(module_dir)
    presets_path = os.path.join(project_root, "gesture_presets.json")

    gesture_names = {}
    try:
        with open(presets_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for gesture in data.get("gestures", []):
            pattern = tuple(gesture["pattern"])
            gesture_names[pattern] = gesture["name"].upper()
    except Exception:
        # Fallback if file is missing
        gesture_names = {
            (0, 0, 0, 0, 0): "FIST (ALL CLOSED)",
            (1, 1, 1, 1, 1): "OPEN PALM (FIVE)",
        }
    return gesture_names


class VirtualServo:
    """Simulates a micro servo motor (e.g. SG90) with angular velocity limits."""

    def __init__(self, pin, name, color=(0, 255, 255)):
        self.pin = pin
        self.name = name
        self.color = color
        self.current_angle = 180.0  # Default open (180 deg)
        self.target_angle = 180.0
        self.max_speed = 600.0      # Deg per second (approx 60 deg / 0.1s for SG90)
        self.last_update = time.time()

    def set_target_angle(self, angle):
        self.target_angle = max(0.0, min(180.0, float(angle)))

    def update(self):
        now = time.time()
        dt = max(0.001, min(0.1, now - self.last_update))
        self.last_update = now

        diff = self.target_angle - self.current_angle
        if abs(diff) > 0.1:
            step = math.copysign(min(abs(diff), self.max_speed * dt), diff)
            self.current_angle += step
        else:
            self.current_angle = self.target_angle

        return self.current_angle


class VirtualArduinoUno:
    """
    Emulates an Arduino Uno board running RobotHandArduino.ino.
    Parses $11000# packets and updates servo angles.
    """

    def __init__(self):
        self.baud_rate = 9600
        self.input_string = ""
        self.string_complete = False
        self.last_packet = "$11111#"
        self.packet_count = 0
        self.last_rx_time = 0.0

        # Servos attached to pins 8, 9, 10, 11, 12
        self.servos = [
            VirtualServo(8, "Thumb", (0, 165, 255)),     # Orange
            VirtualServo(9, "Index", (255, 180, 50)),    # Light Blue
            VirtualServo(10, "Middle", (50, 220, 50)),   # Green
            VirtualServo(11, "Ring", (0, 220, 255)),     # Yellow
            VirtualServo(12, "Pinky", (180, 50, 255)),   # Magenta/Red
        ]

    def write(self, data: bytes):
        """Simulates Serial.write() from PC to Arduino."""
        if not data:
            return
        text = data.decode("utf-8", errors="ignore")
        for char in text:
            if char == "$":
                self.input_string = ""
            elif char == "#":
                self.string_complete = True
                self._execute_sketch_loop()
            else:
                self.input_string += char

        self.last_rx_time = time.time()

    def _execute_sketch_loop(self):
        """Executes the loop() logic from RobotHandArduino.ino."""
        if self.string_complete:
            if len(self.input_string) == 5:
                self.last_packet = f"${self.input_string}#"
                self.packet_count += 1
                for i in range(5):
                    ch = self.input_string[i]
                    target = 180.0 if ch == "1" else 0.0
                    self.servos[i].set_target_angle(target)
            self.input_string = ""
            self.string_complete = False

    def update(self):
        """Updates physics and kinematics of all servos."""
        for s in self.servos:
            s.update()

    def get_angles(self):
        return [s.current_angle for s in self.servos]

    def is_rx_active(self):
        """Returns True if RX LED should be glowing."""
        return (time.time() - self.last_rx_time) < 0.18


class RobotHandVisualizer:
    """
    Renders a clean, polished robotics telemetry dashboard:
    - Side-by-side Arduino Uno & Serial Monitor telemetry cards (no overlapping boxes)
    - High-visibility recognized gesture banner with ample vertical breathing room
    - Articulated 5-DOF robotic prosthetic hand with forward kinematics animation
    - Bottom telemetry cards for individual servo angles and open/closed states
    """

    def __init__(self, width=640, height=720):
        self.width = width
        self.height = height
        self.gesture_names = _load_gesture_names()

    def render(self, arduino: VirtualArduinoUno, detected_fingers=None, fps=0.0, mode_text="VIRTUAL ARDUINO"):
        """Renders the complete 640x720 simulator dashboard."""
        canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # 1. Subtle dark background with fine technical grid lines
        canvas[:] = (20, 18, 16)  # Deep slate navy (BGR)
        for gx in range(0, self.width, 40):
            cv2.line(canvas, (gx, 54), (gx, self.height), (28, 25, 22), 1)
        for gy in range(54, self.height, 40):
            cv2.line(canvas, (0, gy), (self.width, gy), (28, 25, 22), 1)

        # 2. Header Bar (y = 0..52)
        self._draw_header(canvas, mode_text, fps)

        # 3. Top Section: Arduino Uno Card & Serial Monitor Card side-by-side (y = 64..184)
        self._draw_arduino_card(canvas, arduino, x=20, y=64, w=340, h=120)
        self._draw_serial_card(canvas, arduino, x=372, y=64, w=248, h=120)

        # 4. Recognized Pose Banner (y = 196..236) — Safe from finger tips!
        self._draw_pose_banner(canvas, arduino, detected_fingers, x=20, y=196, w=600, h=40)

        # 5. Articulated 5-DOF Robotic Hand (y = 245..595)
        self._draw_robot_hand(canvas, arduino, center_x=320, base_y=590)

        # 6. Bottom Section: 5 Servo Angle & Telemetry Gauges (y = 606..708)
        self._draw_servo_gauges(canvas, arduino, top_y=606)

        return canvas

    def _draw_card(self, canvas, x, y, w, h, bg_color=(28, 24, 22), border_color=(50, 44, 40)):
        """Utility to draw a flat card container with border."""
        cv2.rectangle(canvas, (x, y), (x + w, y + h), bg_color, cv2.FILLED)
        cv2.rectangle(canvas, (x, y), (x + w, y + h), border_color, 1, cv2.LINE_AA)

    def _draw_header(self, canvas, mode_text, fps):
        """Top navigation bar with project title and status indicator."""
        cv2.rectangle(canvas, (0, 0), (self.width, 52), (16, 14, 12), cv2.FILLED)
        cv2.line(canvas, (0, 52), (self.width, 52), (45, 40, 35), 1)

        # Title & Subtitle
        cv2.putText(canvas, "ROBOT HAND SIMULATOR", (20, 24),
                    cv2.FONT_HERSHEY_DUPLEX, 0.58, (245, 245, 245), 1, cv2.LINE_AA)
        cv2.putText(canvas, "5-DOF Tendon Kinematics & AVR Firmware", (20, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 150, 160), 1, cv2.LINE_AA)

        # Mode Badge Pill
        pill_w, pill_h = 240, 32
        px, py = self.width - pill_w - 20, 10
        cv2.rectangle(canvas, (px, py), (px + pill_w, py + pill_h), (26, 23, 20), cv2.FILLED)
        cv2.rectangle(canvas, (px, py), (px + pill_w, py + pill_h), (50, 45, 40), 1, cv2.LINE_AA)

        # Glowing green status dot
        is_hw = "HARDWARE" in mode_text
        dot_color = (0, 220, 100) if is_hw else (240, 180, 50)
        cv2.circle(canvas, (px + 14, py + 16), 5, dot_color, cv2.FILLED)
        cv2.circle(canvas, (px + 14, py + 16), 8, dot_color, 1, cv2.LINE_AA)

        cv2.putText(canvas, mode_text, (px + 28, py + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, (230, 230, 230), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"{fps:4.1f} FPS", (px + 175, py + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.33, (140, 150, 160), 1, cv2.LINE_AA)

    def _draw_arduino_card(self, canvas, arduino: VirtualArduinoUno, x, y, w, h):
        """Clean representation of an Arduino Uno R3 board."""
        # Board body (Arduino Cyan/Slate PCB)
        self._draw_card(canvas, x, y, w, h, bg_color=(45, 35, 15), border_color=(80, 70, 40))

        # Silkscreen Branding
        cv2.putText(canvas, "ARDUINO", (x + 14, y + 26),
                    cv2.FONT_HERSHEY_DUPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, "UNO R3", (x + 112, y + 26),
                    cv2.FONT_HERSHEY_DUPLEX, 0.44, (240, 190, 60), 1, cv2.LINE_AA)

        # ATmega328P Microcontroller Chip
        ic_x, ic_y, ic_w, ic_h = x + 14, y + 42, 160, 36
        cv2.rectangle(canvas, (ic_x, ic_y), (ic_x + ic_w, ic_y + ic_h), (20, 18, 16), cv2.FILLED)
        cv2.rectangle(canvas, (ic_x, ic_y), (ic_x + ic_w, ic_y + ic_h), (60, 55, 50), 1)
        cv2.putText(canvas, "ATmega328P-PU", (ic_x + 14, ic_y + 23),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 205, 210), 1, cv2.LINE_AA)

        # IC Pins indicators
        for p in range(ic_x + 10, ic_x + ic_w - 10, 14):
            cv2.line(canvas, (p, ic_y - 3), (p, ic_y), (140, 145, 150), 1)
            cv2.line(canvas, (p, ic_y + ic_h), (p, ic_y + ic_h + 3), (140, 145, 150), 1)

        # Status LEDs
        # Power LED (Green)
        cv2.circle(canvas, (x + 200, y + 48), 4, (0, 220, 100), cv2.FILLED)
        cv2.putText(canvas, "PWR", (x + 212, y + 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (160, 170, 180), 1)

        # RX LED (Amber blink on data packet)
        rx_active = arduino.is_rx_active()
        rx_col = (0, 210, 255) if rx_active else (35, 45, 55)
        cv2.circle(canvas, (x + 265, y + 48), 4, rx_col, cv2.FILLED)
        if rx_active:
            cv2.circle(canvas, (x + 265, y + 48), 7, (0, 210, 255), 1)
        cv2.putText(canvas, "RX", (x + 277, y + 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (160, 170, 180), 1)

        # Servo Output Header Pins (D8 to D12)
        cv2.putText(canvas, "SERVO PWM OUTPUTS (PINS 8-12):", (x + 14, y + 96),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (150, 160, 170), 1)

        pin_start_x = x + 185
        for i, s in enumerate(arduino.servos):
            px = pin_start_x + i * 28
            py = y + 92

            # Socket
            cv2.rectangle(canvas, (px - 10, py - 10), (px + 10, py + 10), (22, 20, 18), cv2.FILLED)
            cv2.rectangle(canvas, (px - 10, py - 10), (px + 10, py + 10), s.color, 1)
            cv2.putText(canvas, f"{s.pin}", (px - 6, py + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.30, (230, 230, 230), 1)

    def _draw_serial_card(self, canvas, arduino: VirtualArduinoUno, x, y, w, h):
        """Clean packet monitor card showing current serial communication."""
        self._draw_card(canvas, x, y, w, h, bg_color=(24, 22, 20), border_color=(45, 40, 35))

        # Title
        cv2.putText(canvas, "SERIAL PACKET MONITOR", (x + 14, y + 24),
                    cv2.FONT_HERSHEY_DUPLEX, 0.38, (240, 180, 50), 1, cv2.LINE_AA)

        # Active Packet Pill
        pill_w, pill_h = w - 28, 38
        px, py = x + 14, y + 36
        cv2.rectangle(canvas, (px, py), (px + pill_w, py + pill_h), (16, 24, 20), cv2.FILLED)
        cv2.rectangle(canvas, (px, py), (px + pill_w, py + pill_h), (30, 120, 60), 1, cv2.LINE_AA)

        cv2.putText(canvas, "PACKET:", (px + 10, py + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 160, 150), 1, cv2.LINE_AA)
        cv2.putText(canvas, arduino.last_packet, (px + 82, py + 27),
                    cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 255, 130), 1, cv2.LINE_AA)

        # Statistics row
        cv2.putText(canvas, f"BAUD: 9600  |  PACKETS: {arduino.packet_count}", (x + 14, y + 94),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (150, 155, 165), 1)
        cv2.putText(canvas, "STATUS: BUFFER SYNCHRONIZED", (x + 14, y + 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, (100, 190, 240), 1)

    def _draw_pose_banner(self, canvas, arduino: VirtualArduinoUno, detected_fingers, x, y, w, h):
        """Displays currently active recognized gesture with ample vertical space from the hand."""
        if detected_fingers is not None and len(detected_fingers) == 5:
            pattern = tuple(detected_fingers)
        else:
            pattern = tuple(1 if s.current_angle > 90 else 0 for s in arduino.servos)

        name = self.gesture_names.get(pattern, "CUSTOM GESTURE")

        self._draw_card(canvas, x, y, w, h, bg_color=(28, 25, 22), border_color=(60, 52, 45))

        # Glowing cyan status dot on left
        cv2.circle(canvas, (x + 22, y + h // 2), 5, (250, 190, 50), cv2.FILLED)
        cv2.circle(canvas, (x + 22, y + h // 2), 9, (250, 190, 50), 1, cv2.LINE_AA)

        # Label + Gesture Name
        cv2.putText(canvas, "RECOGNIZED POSE:", (x + 40, y + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (160, 170, 180), 1, cv2.LINE_AA)
        cv2.putText(canvas, name, (x + 185, y + 26),
                    cv2.FONT_HERSHEY_DUPLEX, 0.48, (0, 240, 180), 1, cv2.LINE_AA)

    def _draw_robot_hand(self, canvas, arduino: VirtualArduinoUno, center_x, base_y):
        """
        Draws the articulated 5-finger prosthetic robot hand with realistic joints and kinematics.
        Middle finger tip when fully open reaches y ~ 358, providing 120+ px cushion below the banner.
        """
        angles = arduino.get_angles()  # [thumb, index, middle, ring, pinky] in 0..180 deg

        # 1. Robotic Wrist Base
        wrist_w = 180
        wrist_h = 45
        wrist_top = base_y - wrist_h

        wrist_pts = np.array([
            [center_x - wrist_w // 2 + 15, base_y],
            [center_x + wrist_w // 2 - 15, base_y],
            [center_x + wrist_w // 2, wrist_top],
            [center_x - wrist_w // 2, wrist_top],
        ], np.int32)
        cv2.fillPoly(canvas, [wrist_pts], (35, 32, 28))
        cv2.polylines(canvas, [wrist_pts], True, (65, 60, 52), 1, cv2.LINE_AA)

        # 5 Mini Servos inside wrist base
        for i, s in enumerate(arduino.servos):
            sx = center_x - 64 + i * 32
            sy = base_y - 22
            # Servo body
            cv2.rectangle(canvas, (sx - 10, sy - 14), (sx + 10, sy + 14), (160, 80, 20), cv2.FILLED)
            cv2.rectangle(canvas, (sx - 10, sy - 14), (sx + 10, sy + 14), (200, 200, 200), 1)

            # Rotating servo horn
            horn_ang = math.radians(angles[i])
            hx = int(sx + 8 * math.cos(horn_ang))
            hy = int(sy - 8 * math.sin(horn_ang))
            cv2.line(canvas, (sx, sy), (hx, hy), (255, 255, 255), 2, cv2.LINE_AA)
            cv2.circle(canvas, (sx, sy), 2, (255, 255, 255), cv2.FILLED)

        # 2. Robotic Palm Chassis (Hexagonal plate)
        palm_top = wrist_top - 85
        palm_pts = np.array([
            [center_x - 80, wrist_top],
            [center_x - 95, wrist_top - 40],   # Thumb notch
            [center_x - 72, palm_top],
            [center_x + 72, palm_top],
            [center_x + 85, wrist_top - 35],
            [center_x + 80, wrist_top]
        ], np.int32)
        cv2.fillPoly(canvas, [palm_pts], (30, 28, 25))
        cv2.polylines(canvas, [palm_pts], True, (75, 70, 60), 1, cv2.LINE_AA)

        # Palm center pulse core
        core_y = wrist_top - 44
        cv2.circle(canvas, (center_x, core_y), 20, (20, 18, 16), cv2.FILLED)
        cv2.circle(canvas, (center_x, core_y), 20, (240, 180, 50), 1, cv2.LINE_AA)
        cv2.circle(canvas, (center_x, core_y), 8, (0, 220, 100), cv2.FILLED)
        cv2.putText(canvas, "PROSTHETIC-5", (center_x - 38, wrist_top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (150, 155, 165), 1, cv2.LINE_AA)

        # 3. Knuckle Anchors & Segment Lengths
        finger_bases = [
            (center_x - 88, wrist_top - 32, -45),  # Thumb (offset left, tilted)
            (center_x - 48, palm_top + 4, -8),      # Index
            (center_x - 16, palm_top - 2, 0),       # Middle
            (center_x + 18, palm_top + 2, 6),       # Ring
            (center_x + 52, palm_top + 10, 14),     # Pinky
        ]

        finger_lengths = [
            (26, 22, 18),  # Thumb
            (36, 28, 20),  # Index
            (40, 32, 22),  # Middle
            (36, 28, 20),  # Ring
            (28, 22, 16),  # Pinky
        ]

        # Draw each finger
        for i in range(5):
            bx, by, natural_tilt = finger_bases[i]
            cur_angle = angles[i]
            seg_lens = finger_lengths[i]

            # Tendon wire from servo to knuckle
            sx = center_x - 64 + i * 32
            sy = base_y - 22
            cv2.line(canvas, (sx, sy), (bx, by), (65, 60, 55), 1, cv2.LINE_AA)

            self._draw_articulated_finger(canvas, bx, by, natural_tilt, cur_angle, seg_lens,
                                          arduino.servos[i].color, is_thumb=(i == 0))

    def _draw_articulated_finger(self, canvas, base_x, base_y, natural_tilt_deg, servo_angle,
                                 seg_lengths, accent_color, is_thumb=False):
        """Draws multi-joint linkage for each finger using forward kinematics."""
        ext = servo_angle / 180.0  # 1.0 = fully open, 0.0 = fully closed

        if is_thumb:
            # Thumb kinematic curl
            base_rot = math.radians(natural_tilt_deg + (1.0 - ext) * 50.0)
            curl1 = math.radians((1.0 - ext) * 45.0)
            curl2 = math.radians((1.0 - ext) * 45.0)
        else:
            # 4 Fingers curl inward towards palm
            base_rot = math.radians(-90 + natural_tilt_deg + (1.0 - ext) * 35.0)
            curl1 = math.radians((1.0 - ext) * 55.0)
            curl2 = math.radians((1.0 - ext) * 60.0)

        l1, l2, l3 = seg_lengths

        # Joint 1 -> Joint 2
        a1 = base_rot
        j2_x = int(base_x + l1 * math.cos(a1))
        j2_y = int(base_y + l1 * math.sin(a1))

        # Joint 2 -> Joint 3
        a2 = a1 + curl1
        j3_x = int(j2_x + l2 * math.cos(a2))
        j3_y = int(j2_y + l2 * math.sin(a2))

        # Joint 3 -> Tip
        a3 = a2 + curl2
        tip_x = int(j3_x + l3 * math.cos(a3))
        tip_y = int(j3_y + l3 * math.sin(a3))

        # Segment 1 (Proximal)
        cv2.line(canvas, (base_x, base_y), (j2_x, j2_y), (50, 45, 40), 10, cv2.LINE_AA)
        cv2.line(canvas, (base_x, base_y), (j2_x, j2_y), (120, 115, 110), 4, cv2.LINE_AA)
        cv2.line(canvas, (base_x, base_y), (j2_x, j2_y), accent_color, 2, cv2.LINE_AA)

        # Segment 2 (Intermediate)
        cv2.line(canvas, (j2_x, j2_y), (j3_x, j3_y), (45, 40, 36), 8, cv2.LINE_AA)
        cv2.line(canvas, (j2_x, j2_y), (j3_x, j3_y), (110, 105, 100), 3, cv2.LINE_AA)

        # Segment 3 (Distal Tip)
        cv2.line(canvas, (j3_x, j3_y), (tip_x, tip_y), (40, 36, 32), 6, cv2.LINE_AA)
        cv2.line(canvas, (j3_x, j3_y), (tip_x, tip_y), (100, 95, 90), 2, cv2.LINE_AA)

        # Joint Pivot Pins
        for jx, jy, r in [(base_x, base_y, 6), (j2_x, j2_y, 5), (j3_x, j3_y, 4)]:
            cv2.circle(canvas, (jx, jy), r, (18, 16, 14), cv2.FILLED)
            cv2.circle(canvas, (jx, jy), r, (160, 165, 175), 1, cv2.LINE_AA)

        # Fingertip Sensor Dot
        tip_glow = (0, 230, 120) if ext > 0.5 else (50, 60, 220)
        cv2.circle(canvas, (tip_x, tip_y), 4, tip_glow, cv2.FILLED)
        cv2.circle(canvas, (tip_x, tip_y), 5, (255, 255, 255), 1, cv2.LINE_AA)

    def _draw_servo_gauges(self, canvas, arduino: VirtualArduinoUno, top_y):
        """Draws 5 clean, evenly spaced telemetry cards along the bottom."""
        card_w = 110
        gap = 12
        left_margin = 20

        for i, s in enumerate(arduino.servos):
            gx = left_margin + i * (card_w + gap)
            gy = top_y

            ang = s.current_angle
            is_open = ang > 90.0
            status_text = "OPEN" if is_open else "CLOSED"
            status_col = (0, 220, 100) if is_open else (60, 60, 220)

            # Card Container
            self._draw_card(canvas, gx, gy, card_w, 98, bg_color=(26, 23, 20), border_color=(48, 42, 36))

            # Finger Name & Pin Tag
            cv2.putText(canvas, s.name.upper(), (gx + 10, gy + 20),
                        cv2.FONT_HERSHEY_DUPLEX, 0.38, (240, 240, 240), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"D{s.pin}", (gx + 78, gy + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, s.color, 1, cv2.LINE_AA)

            # Degree Readout
            cv2.putText(canvas, f"{ang:5.1f}°", (gx + 10, gy + 44),
                        cv2.FONT_HERSHEY_DUPLEX, 0.46, (230, 235, 240), 1, cv2.LINE_AA)

            # Progress Bar Track
            bar_x, bar_y, bar_w, bar_h = gx + 10, gy + 54, card_w - 20, 8
            cv2.rectangle(canvas, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (35, 30, 26), cv2.FILLED)

            # Filled bar
            fill_w = int(bar_w * (ang / 180.0))
            if fill_w > 0:
                cv2.rectangle(canvas, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), status_col, cv2.FILLED)
            cv2.rectangle(canvas, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (55, 48, 42), 1)

            # Status Badge Pill
            tag_y = gy + 72
            cv2.rectangle(canvas, (gx + 10, tag_y), (gx + card_w - 10, tag_y + 18), (18, 16, 14), cv2.FILLED)
            cv2.rectangle(canvas, (gx + 10, tag_y), (gx + card_w - 10, tag_y + 18), status_col, 1)
            cv2.putText(canvas, status_text, (gx + 32, tag_y + 13),
                        cv2.FONT_HERSHEY_DUPLEX, 0.34, status_col, 1, cv2.LINE_AA)
