#include <EEPROM.h>
#include <Ticker.h>
#include "HX711.h"

// ---------- Pulse Generator Pins ----------
#define DIGITIMERPIN 13
#define TRIGGERPIN 12
#define LEDPIN 2

#define ON 1
#define OFF (!ON)

const unsigned long triggerLength = 100;
unsigned long lastForcePrint = 0;

volatile bool runPulse = false;
unsigned int onTime = 765;
unsigned int offTime = 765;
unsigned long lastOn = 0;
unsigned int frequency = 60;
String receivedString = "";

// Ticker instance
Ticker pulseTicker;

void checkPulse() {
  if (runPulse) {
    digitalWrite(DIGITIMERPIN, !digitalRead(DIGITIMERPIN));
  } else {
    digitalWrite(DIGITIMERPIN, OFF);
  }
}

void readEEPROM() {
  EEPROM.begin(512);
  unsigned int tmp;
  int eeAddress = 0;
  EEPROM.get(eeAddress, tmp);
  if (tmp > 0 && tmp < 1000) frequency = tmp;

  eeAddress += sizeof(tmp);
  EEPROM.get(eeAddress, tmp);
  if (tmp > 100 && tmp < 10000) onTime = tmp;

  eeAddress += sizeof(tmp);
  EEPROM.get(eeAddress, tmp);
  if (tmp > 100 && tmp < 10000) offTime = tmp;

  EEPROM.end();
}

void writeEEPROM() {
  EEPROM.begin(512);
  int eeAddress = 0;
  EEPROM.put(eeAddress, frequency);
  eeAddress += sizeof(frequency);
  EEPROM.put(eeAddress, onTime);
  eeAddress += sizeof(onTime);
  EEPROM.put(eeAddress, offTime);
  EEPROM.commit();
  EEPROM.end();
}

void printStatus() {
  Serial.print("Pulse Status: ");
  Serial.print(frequency);
  Serial.print(",");
  Serial.print(onTime);
  Serial.print(",");
  Serial.println(offTime);
}

// ---------- HX711 Pins ----------
#define DATA_PIN 16
#define CLK_PIN 4
#define SCALE 3108.5f


HX711 scale;

void parsePulseCommand(String s) {
  if (s == "?") {
    printStatus();
    return;
  }

  int freq, onT, offT;
  char strChar[512];
  s.toCharArray(strChar, 512);
  sscanf(strChar, "%d,%d,%d", &freq, &onT, &offT);
  if (freq > 0 && (onT > 100 && onT < 10000) && (offT > 100 && offT < 10000)) {
    frequency = freq;
    pulseTicker.detach(); // stop old ticker
    pulseTicker.attach_ms(1000 / (frequency * 2), checkPulse); // toggle twice per period
    onTime = onT;
    offTime = offT;
    Serial.print("Setting freq: ");
    Serial.print(frequency);
    Serial.print(" Hz, OnTime: ");
    Serial.print(onTime);
    Serial.print(" ms, OffTime: ");
    Serial.print(offTime);
    Serial.println(" ms");
    writeEEPROM();
  } else {
    Serial.println("Pulse Command format: [freq (Hz)],[onTime (ms)],[offTime (ms)]");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(DIGITIMERPIN, OUTPUT);
  pinMode(TRIGGERPIN, OUTPUT);
  pinMode(LEDPIN, OUTPUT);

  // Pulse generator
  readEEPROM();
  printStatus();
  pulseTicker.attach_ms(1000 / (frequency * 2), checkPulse);

  // HX711
  Serial.println("Initializing force sensor...");
  scale.begin(DATA_PIN, CLK_PIN);
  scale.set_scale(SCALE);
  scale.tare(20);
  Serial.println("Setup complete.");
}

void loop() {
  // --- Serial Command Handling ---
  while (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    // HX711 Reset
    if (cmd.equalsIgnoreCase("RESET")) {
      Serial.println("Resetting force sensor tare...");
      scale.tare(20);
      Serial.println("Done.");
    }
    // Pulse generator commands
    else {
      parsePulseCommand(cmd);
    }
  }

  // --- Pulse timing ---
  unsigned long m = micros();
  if (m >= lastOn + ((onTime + offTime) * 1000UL)) {
    lastOn = m;
    runPulse = true;
    digitalWrite(LEDPIN, ON);
    digitalWrite(TRIGGERPIN, ON);
    Serial.println("TRIG");
  }

  if (m >= lastOn + (triggerLength * 1000UL)) {
    digitalWrite(LEDPIN, OFF);
    digitalWrite(TRIGGERPIN, OFF);
  }

  if (m >= lastOn + (onTime * 1000UL)) {
    runPulse = false;
  }
  
  // --- HX711 Reading ---
  unsigned long now = millis();

  // HX711 reading at 50 ms interval
  if (now - lastForcePrint >= 50) {
    lastForcePrint = now;
    if (scale.is_ready()) {
      float val = scale.get_units();
      Serial.print("Force: ");
      Serial.println(val, 1);
    }
  }
}





