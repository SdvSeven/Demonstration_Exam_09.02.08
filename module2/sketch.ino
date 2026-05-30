const int PIN_R = 8, PIN_Y = 9, PIN_G = 10;
const int BTN1 = 2, BTN2 = 3;

void setTL(char c) {
  digitalWrite(PIN_R, c == 'R');
  digitalWrite(PIN_Y, c == 'Y');
  digitalWrite(PIN_G, c == 'G');
}

void setup() {
  Serial.begin(9600);
  pinMode(PIN_R, OUTPUT);
  pinMode(PIN_Y, OUTPUT);
  pinMode(PIN_G, OUTPUT);
  pinMode(BTN1, INPUT_PULLUP);
  pinMode(BTN2, INPUT_PULLUP);
  setTL('Y');
}

void loop() {
  if (Serial.available() > 0) {
    char c = Serial.read();
    if (c == 'R' || c == 'Y' || c == 'G') setTL(c);
  }
  if (!digitalRead(BTN1)) { Serial.println("B1"); delay(300); }
  if (!digitalRead(BTN2)) { Serial.println("B2"); delay(300); }
}
