"""
Hand Tracking Module
Universal hand detector supporting MediaPipe (legacy + tasks) and OpenCV contour fallback.
"""

import cv2
import numpy as np
import time
import math
import os
import urllib.request
import ssl
import contextlib

# Suppress MediaPipe/TF internal C++ logging
os.environ["GLOG_minloglevel"] = "2"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["ABSL_LOGGING_MIN_SEVERITY"] = "2"

@contextlib.contextmanager
def _suppress_c_stderr():
    """Silences low-level C++ stderr logging from MediaPipe/TFLite."""
    devnull = None
    old_stderr = None
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
    except Exception:
        pass

    try:
        yield
    finally:
        if old_stderr is not None:
            try:
                os.dup2(old_stderr, 2)
                os.close(old_stderr)
            except Exception:
                pass
        if devnull is not None:
            try:
                os.close(devnull)
            except Exception:
                pass

try:
    with _suppress_c_stderr():
        import mediapipe as mp
    MP_AVAILABLE = True
except ImportError:
    MP_AVAILABLE = False


class HandDetector:
    """
    Universal HandDetector compatible with:
    - Legacy MediaPipe (mp.solutions.hands)
    - Modern MediaPipe (mp.tasks.vision.HandLandmarker for Python 3.12+)
    - OpenCV contour & convex hull fallback
    """

    HAND_CONNECTIONS = [
        (0, 1), (1, 2), (2, 3), (3, 4),
        (0, 5), (5, 6), (6, 7), (7, 8),
        (5, 9), (9, 10), (10, 11), (11, 12),
        (9, 13), (13, 14), (14, 15), (15, 16),
        (13, 17), (17, 18), (18, 19), (19, 20),
        (0, 17)
    ]

    def __init__(self, mode=False, maxHands=2, detectionCon=0.5, trackCon=0.5):
        self.mode = mode
        self.maxHands = maxHands
        self.detectionCon = detectionCon
        self.trackCon = trackCon
        self.tipIds = [4, 8, 12, 16, 20]
        self.lmList = []
        self.multi_hand_landmarks = []

        self.backend = None

        if MP_AVAILABLE:
            if hasattr(mp, "solutions") and hasattr(mp.solutions, "hands"):
                self.backend = "solutions"
                self.mpHands = mp.solutions.hands
                self.hands = self.mpHands.Hands(
                    static_image_mode=self.mode,
                    max_num_hands=self.maxHands,
                    min_detection_confidence=self.detectionCon,
                    min_tracking_confidence=self.trackCon
                )
                self.mpDraw = mp.solutions.drawing_utils
            elif hasattr(mp, "tasks") and hasattr(mp.tasks, "vision"):
                self.backend = "tasks"
                self._init_tasks_landmarker()

        if self.backend is None:
            self.backend = "contour"
            print("Using lightweight OpenCV contour hand tracking backend.")

    def _init_tasks_landmarker(self):
        # First check local project models folder
        module_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(module_dir)
        local_asset_model = os.path.join(project_root, "models", "hand_landmarker.task")

        cache_dir = os.path.join(os.path.expanduser("~"), ".mediapipe_models")
        os.makedirs(cache_dir, exist_ok=True)
        cached_model = os.path.join(cache_dir, "hand_landmarker.task")

        if os.path.exists(local_asset_model):
            model_path = local_asset_model
        elif os.path.exists(cached_model):
            model_path = cached_model
        else:
            print("Downloading MediaPipe hand_landmarker model (one-time setup)...")
            url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
            try:
                ctx = ssl._create_unverified_context()
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, context=ctx) as resp, open(cached_model, "wb") as f:
                    f.write(resp.read())
                print("Model downloaded successfully.")
                model_path = cached_model
            except Exception as e:
                print(f"Could not download tasks model: {e}")
                self.backend = "contour"
                return

        try:
            BaseOptions = mp.tasks.BaseOptions
            HandLandmarker = mp.tasks.vision.HandLandmarker
            HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode

            options = HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                running_mode=VisionRunningMode.IMAGE,
                num_hands=self.maxHands,
                min_hand_detection_confidence=self.detectionCon,
                min_tracking_confidence=self.trackCon
            )
            with _suppress_c_stderr():
                self.landmarker = HandLandmarker.create_from_options(options)
        except Exception as e:
            print(f"Failed to initialize MediaPipe tasks landmarker: {e}")
            self.backend = "contour"

    def drawHandSkeleton(self, img, landmarks):
        """
        Draws high-contrast white skeletal connection lines and
        vivid red landmark dots with crisp white borders.
        """
        h, w = img.shape[:2]
        pts = []
        for lm in landmarks:
            cx = int(lm.x * w)
            cy = int(lm.y * h)
            pts.append((cx, cy))

        # 1. Crisp white skeletal lines connecting joints
        for p1_id, p2_id in self.HAND_CONNECTIONS:
            if p1_id < len(pts) and p2_id < len(pts):
                cv2.line(img, pts[p1_id], pts[p2_id], (255, 255, 255), 2, cv2.LINE_AA)

        # 2. Vivid red dots (BGR: 0, 0, 255) with crisp white border
        for cx, cy in pts:
            cv2.circle(img, (cx, cy), 5, (0, 0, 255), cv2.FILLED, cv2.LINE_AA)
            cv2.circle(img, (cx, cy), 5, (255, 255, 255), 1, cv2.LINE_AA)

    def findHands(self, img, draw=True):
        self.multi_hand_landmarks = []

        if self.backend == "solutions":
            imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            self.results = self.hands.process(imgRGB)
            if self.results.multi_hand_landmarks:
                self.multi_hand_landmarks = self.results.multi_hand_landmarks
                if draw:
                    for handLms in self.multi_hand_landmarks:
                        self.drawHandSkeleton(img, handLms.landmark)

        elif self.backend == "tasks":
            imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=imgRGB)
            result = self.landmarker.detect(mp_image)
            self.results = result
            if result.hand_landmarks:
                self.multi_hand_landmarks = result.hand_landmarks
                if draw:
                    for hand in self.multi_hand_landmarks:
                        self.drawHandSkeleton(img, hand)

        elif self.backend == "contour":
            # Lightweight skin contour detector
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            lower = np.array([0, 20, 70], dtype=np.uint8)
            upper = np.array([20, 255, 255], dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)
            mask = cv2.GaussianBlur(mask, (5, 5), 100)
            contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                c = max(contours, key=cv2.contourArea)
                if cv2.contourArea(c) > 3000:
                    x, y, w, h = cv2.boundingRect(c)
                    # Generate approximate landmarks based on bounding box & hull
                    hull = cv2.convexHull(c, returnPoints=True)
                    pts = [hull[i][0] for i in range(min(5, len(hull)))]
                    fake_landmarks = []
                    for i in range(21):
                        class FakePoint:
                            def __init__(self, fx, fy): self.x, self.y = fx, fy
                        px = (x + w // 2) / img.shape[1]
                        py = (y + h // 2) / img.shape[0]
                        if i in self.tipIds and len(pts) > 0:
                            p = pts[self.tipIds.index(i) % len(pts)]
                            px, py = p[0] / img.shape[1], p[1] / img.shape[0]
                        fake_landmarks.append(FakePoint(px, py))
                    self.multi_hand_landmarks = [fake_landmarks]
                    if draw:
                        self.drawHandSkeleton(img, fake_landmarks)

        return img

    def findPosition(self, img, handNo=0, draw=True):
        self.lmList = []
        bbox = []
        if len(self.multi_hand_landmarks) > handNo:
            myHand = self.multi_hand_landmarks[handNo]
            landmarks = myHand.landmark if hasattr(myHand, "landmark") else myHand
            xList = []
            yList = []
            h, w, c = img.shape
            for id, lm in enumerate(landmarks):
                cx, cy = int(lm.x * w), int(lm.y * h)
                xList.append(cx)
                yList.append(cy)
                self.lmList.append([id, cx, cy])
                if draw:
                    cv2.circle(img, (cx, cy), 5, (0, 0, 255), cv2.FILLED, cv2.LINE_AA)
                    cv2.circle(img, (cx, cy), 5, (255, 255, 255), 1, cv2.LINE_AA)
            if xList and yList:
                xmin, xmax = min(xList), max(xList)
                ymin, ymax = min(yList), max(yList)
                bbox = [xmin, ymin, xmax, ymax]
                if draw:
                    cv2.rectangle(img, (bbox[0] - 20, bbox[1] - 20),
                                  (bbox[2] + 20, bbox[3] + 20), (255, 255, 255), 2)
        return self.lmList, bbox

    def fingersUp(self):
        fingers = []
        if not self.lmList or len(self.lmList) < 21:
            return [0, 0, 0, 0, 0]

        # Landmark 0: Wrist, 5: Index MCP, 17: Pinky MCP
        # Determine geometric handedness / orientation in camera view:
        # In a mirrored selfie feed:
        # If Index MCP x < Pinky MCP x, palm facing camera is Right Hand (Thumb extends to the left)
        # If Index MCP x > Pinky MCP x, palm facing camera is Left Hand (Thumb extends to the right)
        is_right_facing = self.lmList[5][1] < self.lmList[17][1]

        # Thumb detection:
        thumb_tip = self.lmList[self.tipIds[0]]      # Landmark 4
        thumb_ip = self.lmList[self.tipIds[0] - 1]   # Landmark 3
        pinky_mcp = self.lmList[17]                   # Landmark 17
        index_mcp = self.lmList[5]                    # Landmark 5

        # Distance from thumb tip to pinky MCP vs IP joint to pinky MCP
        d_tip_pinky = math.hypot(thumb_tip[1] - pinky_mcp[1], thumb_tip[2] - pinky_mcp[2])
        d_ip_pinky = math.hypot(thumb_ip[1] - pinky_mcp[1], thumb_ip[2] - pinky_mcp[2])
        d_tip_index = math.hypot(thumb_tip[1] - index_mcp[1], thumb_tip[2] - index_mcp[2])

        if is_right_facing:
            thumb_open = (thumb_tip[1] < thumb_ip[1]) or (d_tip_pinky > d_ip_pinky * 1.05 and d_tip_index > 40)
        else:
            thumb_open = (thumb_tip[1] > thumb_ip[1]) or (d_tip_pinky > d_ip_pinky * 1.05 and d_tip_index > 40)

        fingers.append(1 if thumb_open else 0)

        # 4 Fingers: Check both vertical position (y) and distance from wrist (0)
        wrist = self.lmList[0]
        for id in range(1, 5):
            tip_id = self.tipIds[id]
            pip_id = tip_id - 2
            tip_pt = self.lmList[tip_id]
            pip_pt = self.lmList[pip_id]

            d_tip = math.hypot(tip_pt[1] - wrist[1], tip_pt[2] - wrist[2])
            d_pip = math.hypot(pip_pt[1] - wrist[1], pip_pt[2] - wrist[2])

            # Finger extended if tip is above PIP or tip is farther from wrist than PIP
            if (tip_pt[2] < pip_pt[2]) or (d_tip > d_pip * 1.08):
                fingers.append(1)
            else:
                fingers.append(0)

        return fingers

    def findDistance(self, p1, p2, img=None):
        if not self.lmList or len(self.lmList) <= max(p1, p2):
            if img is not None:
                return 0, (0, 0, 0, 0, 0, 0), img
            return 0, (0, 0, 0, 0, 0, 0)

        x1, y1 = self.lmList[p1][1], self.lmList[p1][2]
        x2, y2 = self.lmList[p2][1], self.lmList[p2][2]
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        length = math.hypot(x2 - x1, y2 - y1)
        info = (x1, y1, x2, y2, cx, cy)
        if img is not None:
            cv2.circle(img, (x1, y1), 10, (255, 0, 255), cv2.FILLED)
            cv2.circle(img, (x2, y2), 10, (255, 0, 255), cv2.FILLED)
            cv2.line(img, (x1, y1), (x2, y2), (255, 0, 255), 3)
            cv2.circle(img, (cx, cy), 10, (255, 0, 255), cv2.FILLED)
            return length, info, img
        return length, info
