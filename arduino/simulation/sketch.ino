#include <Servo.h>

Servo servoThumb;
Servo servoIndex;
Servo servoMiddle;
Servo servoRing;
Servo servoPinky;

String inputString = "";
bool stringComplete = false;

void setup() {
  Serial.begin(9600);
  servoThumb.attach(8);
  servoIndex.attach(9);
  servoMiddle.attach(10);
  servoRing.attach(11);
  servoPinky.attach(12);
}

void loop() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '$') {
      inputString = "";
    } else if (inChar == '#') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }

  if (stringComplete) {
    if (inputString.length() == 5) {
      servoThumb.write(inputString.charAt(0) == '1' ? 180 : 0);
      servoIndex.write(inputString.charAt(1) == '1' ? 180 : 0);
      servoMiddle.write(inputString.charAt(2) == '1' ? 180 : 0);
      servoRing.write(inputString.charAt(3) == '1' ? 180 : 0);
      servoPinky.write(inputString.charAt(4) == '1' ? 180 : 0);
    }
    inputString = "";
    stringComplete = false;
  }
}
