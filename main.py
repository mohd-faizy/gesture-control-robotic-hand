"""
Entry Point — Robot Hand Gesture Controlled
Supports live webcam feed or video file input via command-line arguments.
"""
import os
import sys
import argparse

# Set current directory to project root and add src to sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

os.chdir(PROJECT_ROOT)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Robot Hand Gesture Controlled — Real-time gesture tracking and 5-DOF robotic hand controller/simulator."
    )
    parser.add_argument(
        "--webcam",
        nargs="?",
        const=0,
        type=int,
        default=None,
        metavar="INDEX",
        help="Use live webcam feed. Optionally specify camera index (e.g. --webcam or --webcam 1, default: 0)."
    )
    parser.add_argument(
        "--video",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to video file for gesture detection (e.g. assets/videos/sample.mp4)."
    )
    parser.add_argument(
        "--no-loop",
        action="store_true",
        help="Disable continuous looping for video files (videos loop by default)."
    )
    return parser.parse_args()


if __name__ == "__main__":
    from robot_hand_control import RobotHandControllerApp

    args = parse_args()

    print("Starting Robot Hand Gesture Controlled...")
    app = RobotHandControllerApp(
        webcam_index=args.webcam,
        video_path=args.video,
        loop=not args.no_loop
    )
    app.run()
