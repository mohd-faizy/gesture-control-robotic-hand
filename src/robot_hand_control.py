"""
Robot Hand Gesture Controller
Control a 5-fingered robotic prosthetic/animatronic hand using your webcam,
an Arduino Uno microcontroller, or the built-in Virtual Arduino & 5-DOF Robot Simulator.
"""

import os
import sys
import json
import time
import cv2
import numpy as np

# Audio feedback on Windows
try:
    import winsound
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

# Serial communication
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# Import local modules
import hand_tracking as htm
import arduino_simulator as sim


def _load_manual_presets():
    """Loads manual keyboard gesture presets from gesture_presets.json."""
    module_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(module_dir)
    presets_path = os.path.join(project_root, "gesture_presets.json")

    presets = {}
    try:
        with open(presets_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for gesture in data.get("gestures", []):
            name = gesture["name"].lower()
            pattern = gesture["pattern"]
            # Map keyboard shortcuts based on gesture names
            if "fist" in name:
                presets["f"] = pattern
            elif "open" in name or "five" in name:
                presets["o"] = pattern
            elif "peace" in name or "victory" in name:
                presets["p"] = pattern
            elif "thumbs up" in name:
                presets["t"] = pattern
            elif "rock" in name or "horns" in name:
                presets["r"] = pattern
            elif "ok" in name:
                presets["k"] = pattern
    except Exception:
        # Fallback defaults
        presets = {
            "f": [0, 0, 0, 0, 0],
            "o": [1, 1, 1, 1, 1],
            "p": [0, 1, 1, 0, 0],
            "t": [1, 0, 0, 0, 0],
            "r": [0, 1, 0, 0, 1],
            "k": [0, 0, 1, 1, 1],
        }
    return presets


class RobotHandControllerApp:
    def __init__(self, webcam_index=None, video_path=None, loop=True):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(self.script_dir)
        self.assets_dir = os.path.join(self.project_root, "assets")

        # Determine video path
        if video_path:
            if os.path.isabs(video_path):
                self.video_sample_path = video_path
            else:
                self.video_sample_path = os.path.join(self.project_root, video_path)
        else:
            video_candidates = [
                os.path.join(self.assets_dir, "videos", "demo_vid.mp4"),
                os.path.join(self.assets_dir, "videos", "Video Project.mp4"),
                os.path.join(self.assets_dir, "videos", "gesture_test_1.mp4"),
            ]
            self.video_sample_path = video_candidates[0]
            for cand in video_candidates:
                if os.path.exists(cand):
                    self.video_sample_path = cand
                    break
            else:
                vids_dir = os.path.join(self.assets_dir, "videos")
                if os.path.isdir(vids_dir):
                    for f in os.listdir(vids_dir):
                        if f.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
                            self.video_sample_path = os.path.join(vids_dir, f)
                            break

        self.loop_video = loop
        self.audio_servo_path = os.path.join(self.assets_dir, "audio", "servo_move.wav")
        self.audio_beep_path = os.path.join(self.assets_dir, "audio", "gesture_beep.wav")

        # Load gesture presets from JSON
        self.manual_presets = _load_manual_presets()

        # Serial / Hardware setup
        self.port = "COM3"
        self.baud_rate = 9600
        self.arduino = None
        self.hardware_connected = False
        self._init_serial()

        # Virtual Arduino & Visualizer
        self.virtual_arduino = sim.VirtualArduinoUno()
        self.visualizer = sim.RobotHandVisualizer(width=640, height=720)

        # Video source state configuration
        self.camera_index = 0
        self.explicit_webcam = False
        self.explicit_video = False

        if video_path is not None:
            self.use_camera = False
            self.explicit_video = True
        elif webcam_index is not None:
            self.use_camera = True
            self.camera_index = webcam_index
            self.explicit_webcam = True
        else:
            self.use_camera = True
            self.camera_index = 0

        self.cap = None
        self._init_video_source()

        # Detector
        self.detector = htm.HandDetector(detectionCon=0.75, trackCon=0.75, maxHands=1)

        # State tracking
        self.last_fingers = [1, 1, 1, 1, 1]
        self.manual_fingers = [1, 1, 1, 1, 1]
        self.manual_mode = False
        self.sound_enabled = True
        self.view_mode = 0  # 0: Dual (Cam + Sim), 1: Sim Only, 2: Cam Only

        # Performance
        self.prev_time = time.time()
        self.fps = 0.0

    def _init_serial(self):
        """Attempts to connect to physical Arduino, falls back cleanly to Virtual Simulator."""
        if not SERIAL_AVAILABLE:
            print("[INFO] pyserial not available. Running with Virtual Arduino Simulator.")
            return

        # Auto-detect available COM ports
        ports = [p.device for p in serial.tools.list_ports.comports()]
        target_ports = [self.port] + [p for p in ports if p != self.port]

        for p in target_ports:
            try:
                self.arduino = serial.Serial(p, self.baud_rate, timeout=0.08)
                time.sleep(1.5)
                self.port = p
                self.hardware_connected = True
                print(f"[SUCCESS] Connected to Physical Arduino on {self.port} at {self.baud_rate} baud.")
                return
            except Exception:
                continue

        print("[INFO] No physical Arduino detected. Virtual Arduino Simulator initialized seamlessly.")

    def _init_video_source(self):
        """Initializes webcam or video file based on configuration."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        if self.use_camera:
            print(f"[INFO] Opening live webcam (Index {self.camera_index})...")
            backends = [cv2.CAP_ANY]
            if hasattr(cv2, "CAP_DSHOW") and sys.platform.startswith("win"):
                backends.insert(0, cv2.CAP_DSHOW)

            opened = False
            for backend in backends:
                try:
                    cap = cv2.VideoCapture(self.camera_index, backend)
                    if cap.isOpened():
                        # Try reading warmup frames
                        for _ in range(5):
                            ret, frame = cap.read()
                            if ret and frame is not None and frame.size > 0:
                                self.cap = cap
                                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                                print(f"[SUCCESS] Live webcam (Index {self.camera_index}) opened successfully.")
                                return
                            time.sleep(0.05)
                        cap.release()
                except Exception:
                    pass

            if self.explicit_webcam:
                print(f"\n[ERROR] Could not capture frames from webcam (Index {self.camera_index}).")
                print("  Possible reasons:")
                print("   1. Another application (e.g. Windows Camera app, Chrome, Teams, Zoom, Discord) is currently using the camera.")
                print("   2. Camera access is blocked in Windows Settings -> Privacy & security -> Camera ('Let desktop apps access your camera').")
                print("   3. An incorrect camera index was given (try `--webcam 0` or `--webcam 1`).")
                print("  -> Remaining in webcam mode. Close conflicting apps and press [S] to retry.\n")
                self.cap = None
                return
            else:
                print(f"[WARN] Webcam (Index {self.camera_index}) unavailable or inaccessible. Switching to sample video.")

            self.use_camera = False

        # Load video file (only when use_camera is False)
        if os.path.exists(self.video_sample_path):
            self.cap = cv2.VideoCapture(self.video_sample_path)
            loop_str = "continuous loop" if self.loop_video else "single play"
            print(f"[INFO] Playing video ({loop_str}): {self.video_sample_path}")
        else:
            print(f"[WARN] Video file not found at: {self.video_sample_path}. Creating synthetic feed.")
            self.cap = None

    def toggle_video_source(self):
        """Toggles between live webcam and pre-recorded sample video."""
        if self.use_camera and self.cap is None:
            print(f"[INFO] Retrying live webcam (Index {self.camera_index})...")
            self._init_video_source()
            if self.cap is not None and self.cap.isOpened():
                return
        self.use_camera = not self.use_camera
        self._init_video_source()

    def play_sound(self, sound_type="servo"):
        """Plays sound effect asynchronously without blocking."""
        if not self.sound_enabled or not AUDIO_AVAILABLE:
            return
        target = self.audio_servo_path if sound_type == "servo" else self.audio_beep_path
        if os.path.exists(target):
            try:
                winsound.PlaySound(target, winsound.SND_ASYNC | winsound.SND_FILENAME)
            except Exception:
                pass

    def send_packet(self, fingers):
        """Dispatches packet to physical Arduino and/or Virtual Arduino Simulator."""
        packet_str = "$" + "".join(str(f) for f in fingers) + "#"
        packet_bytes = packet_str.encode()

        # Send to Virtual Arduino
        self.virtual_arduino.write(packet_bytes)

        # Send to Physical Arduino if connected
        if self.hardware_connected and self.arduino and self.arduino.is_open:
            try:
                self.arduino.write(packet_bytes)
            except Exception as e:
                print(f"[WARN] Serial write error: {e}. Falling back to virtual.")
                self.hardware_connected = False

        # Play servo sound when finger state changes
        if fingers != self.last_fingers:
            self.play_sound("servo")
            self.last_fingers = list(fingers)

        return packet_str

    def run(self):
        """Main application execution loop."""
        win_name = "Robot Hand Gesture Controller & Simulator"
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, 1280, 720)

        print("\n" + "=" * 65)
        print(" ROBOT HAND GESTURE CONTROL & ARDUINO SIMULATOR")
        print("=" * 65)
        print(" [S] - Toggle Video Source (Webcam <-> Sample Video)")
        print(" [M] - Toggle Manual Keyboard Mode")
        print(" [V] - Toggle View Mode (Dual <-> Simulator <-> Camera)")
        print(" [A] - Toggle Audio Feedback")
        print(" [1-5] - Toggle Fingers (Thumb, Index, Middle, Ring, Pinky)")
        print(" [F]ist / [O]pen / [P]eace / [T]humbs Up / [R]ock On (Manual Presets)")
        print(" [Q] - Quit Application")
        print("=" * 65 + "\n")

        while True:
            # Calculate FPS
            curr_time = time.time()
            self.fps = 1.0 / max(0.001, (curr_time - self.prev_time))
            self.prev_time = curr_time

            # Update Virtual Arduino physics
            self.virtual_arduino.update()

            # Read frame
            if self.cap is not None and self.cap.isOpened():
                success, frame = self.cap.read()
                if not success:
                    if not self.use_camera:
                        if self.loop_video:
                            # Loop video if reached end of file
                            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            success, frame = self.cap.read()
                        else:
                            # End of non-looping video
                            success = False
            else:
                success, frame = False, None

            if not success or frame is None:
                # Synthetic frame
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                if self.use_camera:
                    cv2.putText(frame, "WEBCAM ACCESS FAILED", (50, 190),
                                cv2.FONT_HERSHEY_DUPLEX, 0.75, (0, 0, 255), 2)
                    cv2.putText(frame, f"Cannot read from Camera Index {self.camera_index}", (50, 230),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (220, 220, 220), 1)
                    cv2.putText(frame, "Another app (Windows Camera, Teams, Zoom) is locking it", (50, 260),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1)
                    cv2.putText(frame, "Close conflicting apps, then press [S] to retry", (50, 300),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 200), 1)
                elif not self.loop_video:
                    cv2.putText(frame, "VIDEO PLAYBACK COMPLETED", (80, 220),
                                cv2.FONT_HERSHEY_DUPLEX, 0.75, (0, 220, 255), 2)
                    cv2.putText(frame, "Press [S] to switch source or [Q] to quit", (100, 260),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1)
                else:
                    cv2.putText(frame, "NO VIDEO SOURCE DETECTED", (80, 220),
                                cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 0, 255), 2)
                    cv2.putText(frame, "Press [M] for Manual Keyboard Control", (100, 260),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            # Process frame for gestures
            if self.use_camera:
                frame = cv2.flip(frame, 1)  # Mirror live selfie camera

            # Resize frame to standard 640x480
            frame = cv2.resize(frame, (640, 480))

            detected_fingers = None
            if not self.manual_mode:
                frame = self.detector.findHands(frame, draw=True)
                lm_list, bbox = self.detector.findPosition(frame, draw=False)

                if lm_list:
                    detected_fingers = self.detector.fingersUp()
                    self.send_packet(detected_fingers)
            else:
                self.send_packet(self.manual_fingers)
                detected_fingers = self.manual_fingers

            # Render Left Panel (Camera Feed + Tech HUD)
            camera_panel = self._render_camera_panel(frame, detected_fingers)

            # Render Right Panel (Virtual Arduino & Robot Hand)
            status_text = "HARDWARE ON " + self.port if self.hardware_connected else "VIRTUAL ARDUINO"
            sim_panel = self.visualizer.render(
                self.virtual_arduino,
                detected_fingers=detected_fingers,
                fps=self.fps,
                mode_text=status_text
            )

            # Assemble View Mode
            if self.view_mode == 0:
                # Dual View: Left = Camera HUD (640x720), Right = Simulator (640x720)
                composite = np.hstack((camera_panel, sim_panel))
            elif self.view_mode == 1:
                composite = sim_panel
            else:
                composite = camera_panel

            cv2.imshow(win_name, composite)

            # Keyboard event handling
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                self.toggle_video_source()
            elif key == ord('m'):
                self.manual_mode = not self.manual_mode
                print(f"[MODE] Manual Mode: {'ENABLED' if self.manual_mode else 'DISABLED'}")
            elif key == ord('v'):
                self.view_mode = (self.view_mode + 1) % 3
            elif key == ord('a'):
                self.sound_enabled = not self.sound_enabled
                print(f"[AUDIO] Sound Feedback: {'ON' if self.sound_enabled else 'OFF'}")
            elif self.manual_mode:
                self._handle_manual_keys(key)

        # Cleanup
        if self.cap:
            self.cap.release()
        if self.arduino and self.arduino.is_open:
            self.arduino.close()
        cv2.destroyAllWindows()
        print("[EXIT] Program closed cleanly.")

    def _handle_manual_keys(self, key):
        """Processes manual keypresses to manipulate fingers."""
        if ord('1') <= key <= ord('5'):
            idx = key - ord('1')
            self.manual_fingers[idx] = 1 - self.manual_fingers[idx]
        else:
            # Check if the key matches any loaded preset
            char = chr(key) if 32 <= key <= 126 else None
            if char and char in self.manual_presets:
                self.manual_fingers = list(self.manual_presets[char])

    def _render_camera_panel(self, frame_640x480, detected_fingers):
        """Composes 640x720 Left Panel with camera frame and sleek dark robotics HUD."""
        panel = np.zeros((720, 640, 3), dtype=np.uint8)
        panel[:] = (20, 18, 16)  # Deep slate navy background

        # Place 640x480 frame at y=54..534
        panel[54:534, 0:640] = frame_640x480

        # Viewfinder border and subtle corner brackets
        cv2.rectangle(panel, (0, 54), (640, 534), (45, 40, 35), 1)
        for cx, cy, dx, dy in [(12, 66, 18, 18), (628, 66, -18, 18),
                               (12, 522, 18, -18), (628, 522, -18, -18)]:
            cv2.line(panel, (cx, cy), (cx + dx, cy), (240, 180, 50), 2, cv2.LINE_AA)
            cv2.line(panel, (cx, cy), (cx, cy + dy), (240, 180, 50), 2, cv2.LINE_AA)

        # 1. Top Header Bar (y = 0..52)
        cv2.rectangle(panel, (0, 0), (640, 52), (16, 14, 12), cv2.FILLED)
        cv2.line(panel, (0, 52), (640, 52), (45, 40, 35), 1)

        source_label = f"LIVE WEBCAM #{self.camera_index} (MIRRORED)" if self.use_camera else f"VIDEO: {os.path.basename(self.video_sample_path)}"
        cv2.putText(panel, "COMPUTER VISION TRACKER", (20, 24),
                    cv2.FONT_HERSHEY_DUPLEX, 0.58, (245, 245, 245), 1, cv2.LINE_AA)
        cv2.putText(panel, f"SOURCE: {source_label}", (20, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 150, 160), 1, cv2.LINE_AA)

        # Top-right packet badge
        pkt = self.virtual_arduino.last_packet
        cv2.rectangle(panel, (440, 10), (620, 42), (26, 23, 20), cv2.FILLED)
        cv2.rectangle(panel, (440, 10), (620, 42), (48, 42, 36), 1, cv2.LINE_AA)
        cv2.putText(panel, "PKT:", (452, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 150, 160), 1, cv2.LINE_AA)
        cv2.putText(panel, pkt, (492, 30),
                    cv2.FONT_HERSHEY_DUPLEX, 0.52, (0, 255, 130), 1, cv2.LINE_AA)

        # 2. 5 Finger Status Cards (y = 544..626)
        names = ["THUMB", "INDEX", "MIDDLE", "RING", "PINKY"]
        pins = ["D8", "D9", "D10", "D11", "D12"]
        accent_colors = [
            (20, 130, 245),  # Thumb orange
            (240, 170, 40),  # Index blue
            (100, 210, 30),  # Middle green
            (30, 210, 240),  # Ring yellow
            (200, 60, 230)   # Pinky magenta
        ]
        fingers = detected_fingers if detected_fingers else [0, 0, 0, 0, 0]

        card_w = 110
        gap = 12
        left_margin = 20

        for i, (name, pin, val, col) in enumerate(zip(names, pins, fingers, accent_colors)):
            cx = left_margin + i * (card_w + gap)
            cy = 544

            is_up = (val == 1)
            card_bg = (28, 25, 22) if is_up else (22, 20, 18)
            status_col = (0, 220, 100) if is_up else (80, 85, 95)
            tag = "OPEN" if is_up else "CLOSED"

            # Card Container
            cv2.rectangle(panel, (cx, cy), (cx + card_w, cy + 80), card_bg, cv2.FILLED)
            cv2.rectangle(panel, (cx, cy), (cx + card_w, cy + 80), (48, 42, 36), 1, cv2.LINE_AA)

            # Name & Pin Tag
            cv2.putText(panel, name, (cx + 10, cy + 22),
                        cv2.FONT_HERSHEY_DUPLEX, 0.38, (240, 240, 240), 1, cv2.LINE_AA)
            cv2.putText(panel, pin, (cx + 78, cy + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, col, 1, cv2.LINE_AA)

            # Status Tag Pill
            cv2.rectangle(panel, (cx + 10, cy + 38), (cx + card_w - 10, cy + 68), (18, 16, 14), cv2.FILLED)
            cv2.rectangle(panel, (cx + 10, cy + 38), (cx + card_w - 10, cy + 68), status_col, 1)
            cv2.putText(panel, tag, (cx + 30, cy + 58),
                        cv2.FONT_HERSHEY_DUPLEX, 0.40, status_col, 1, cv2.LINE_AA)

        # 3. Control & Shortcut Bar (y = 634..710)
        leg_y = 634
        cv2.rectangle(panel, (20, leg_y), (620, leg_y + 74), (24, 22, 20), cv2.FILLED)
        cv2.rectangle(panel, (20, leg_y), (620, leg_y + 74), (48, 42, 36), 1, cv2.LINE_AA)

        mode_str = "[MANUAL KEYBOARD ACTIVE]" if self.manual_mode else "[GESTURE TRACKING ACTIVE]"
        mode_col = (0, 210, 255) if self.manual_mode else (0, 220, 100)
        cv2.putText(panel, f"MODE: {mode_str}", (32, leg_y + 20),
                    cv2.FONT_HERSHEY_DUPLEX, 0.38, mode_col, 1, cv2.LINE_AA)

        guide_line1 = "[S] Video/Cam  |  [M] Manual Mode  |  [V] View Mode  |  [A] Audio  |  [Q] Quit"
        guide_line2 = "[1-5] Servos   |  [F]ist  [O]pen  [P]eace  [T]humb  [R]ock  [K] OK"
        cv2.putText(panel, guide_line1, (32, leg_y + 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.34, (160, 165, 175), 1, cv2.LINE_AA)
        cv2.putText(panel, guide_line2, (32, leg_y + 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.34, (160, 165, 175), 1, cv2.LINE_AA)

        return panel


if __name__ == "__main__":
    app = RobotHandControllerApp()
    app.run()
