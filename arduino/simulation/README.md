# Wokwi Arduino Simulation Guide

This folder contains a ready-to-run hardware simulation for **Project 19: Robot Hand Gesture Controlled**.

## Circuit Overview
- **Microcontroller**: Arduino Uno R3
- **Actuators**: 5x SG90 Micro Servos
  - Servo 1 (Thumb): Pin 8 (Orange Horn)
  - Servo 2 (Index): Pin 9 (Blue Horn)
  - Servo 3 (Middle): Pin 10 (Green Horn)
  - Servo 4 (Ring): Pin 11 (Yellow Horn)
  - Servo 5 (Pinky): Pin 12 (Red Horn)
- **Power**: 5V rail and Common Ground
- **Baud Rate**: 9600 bps
- **Packet Protocol**: `$[Thumb][Index][Middle][Ring][Pinky]#` (e.g., `$11111#` opens all fingers to 180°, `$00000#` closes all fingers to 0°).

## Option 1: Run Online in Wokwi Browser
1. Go to [https://wokwi.com/projects/new/arduino-uno](https://wokwi.com/projects/new/arduino-uno).
2. Replace `diagram.json` with the contents of `assets/simulation/diagram.json`.
3. Replace the sketch code with `assets/simulation/sketch.ino`.
4. Click the green **Play** button to start the simulation.
5. In the Serial Monitor input bar, type packets like:
   - `$11111#` -> All 5 servos rotate to 180° (Open Hand)
   - `$00000#` -> All 5 servos rotate to 0° (Fist)
   - `$10000#` -> Only Thumb rotates to 180° (Thumbs Up)
   - `$01100#` -> Index and Middle rotate to 180° (Peace Sign)

## Option 2: Run via VS Code Wokwi Extension
1. Install the "Wokwi Simulator" extension in VS Code.
2. Press `F1` and choose `Wokwi: Start Simulator`.
3. The simulator will load `diagram.json` and the pre-compiled `.elf` binary in `arduino/RobotHandArduino/build/`.

## Option 3: Built-In Live Python Graphical Simulator
The Python application includes a built-in virtual Arduino engine and animated 5-DOF robotic hand visualizer that runs simultaneously without needing any external tools.
Run:
```bash
python main.py
```
