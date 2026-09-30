"""
Arduino Sketch Compilation & Upload Utility
Uses arduino-cli to verify, compile, and upload the RobotHandArduino
sketch to an Arduino Uno board.
"""

import os
import sys
import subprocess
import shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.path.dirname(PROJECT_ROOT)
ARDUINO_CLI = os.path.join(WORKSPACE_ROOT, "arduino_tools", "arduino-cli.exe")
SKETCH_DIR = os.path.join(PROJECT_ROOT, "arduino", "RobotHandArduino")


def compile_sketch(export_binaries=True):
    if not os.path.exists(ARDUINO_CLI):
        # Fallback to system arduino-cli
        cli = shutil.which("arduino-cli")
        if not cli:
            print("[ERROR] arduino-cli not found in arduino_tools/ or system PATH.")
            return False
    else:
        cli = ARDUINO_CLI

    cmd = [
        cli,
        "compile",
        "--fqbn", "arduino:avr:uno",
        SKETCH_DIR
    ]
    if export_binaries:
        cmd.append("--export-binaries")

    print(f"\n[COMPILING] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("[SUCCESS] Compilation Succeeded!\n")
        print(result.stdout)
        build_dir = os.path.join(SKETCH_DIR, "build", "arduino.avr.uno")
        hex_file = os.path.join(build_dir, "RobotHandArduino.ino.hex")
        if os.path.exists(hex_file):
            size = os.path.getsize(hex_file)
            print(f"[BINARY] Generated hex firmware: {hex_file} ({size} bytes)")
        return True
    else:
        print("[FAILED] Compilation error:\n")
        print(result.stderr or result.stdout)
        return False


def upload_sketch(port="COM3"):
    cli = ARDUINO_CLI if os.path.exists(ARDUINO_CLI) else shutil.which("arduino-cli")
    if not cli:
        print("[ERROR] arduino-cli not found.")
        return False

    cmd = [
        cli,
        "upload",
        "-p", port,
        "--fqbn", "arduino:avr:uno",
        SKETCH_DIR
    ]
    print(f"[UPLOADING] Uploading to {port}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("[SUCCESS] Upload Succeeded!")
        print(result.stdout)
        return True
    else:
        print(f"[ERROR] Could not upload to {port}:")
        print(result.stderr or result.stdout)
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "upload":
        port = sys.argv[2] if len(sys.argv) > 2 else "COM3"
        upload_sketch(port)
    else:
        success = compile_sketch()
        sys.exit(0 if success else 1)
