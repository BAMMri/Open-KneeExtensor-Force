#include <EEPROM.h>
#include <Ticker.h>
#include "HX711.h"
  // --- NMES Pulse Generator Option BEURER MODE // -------- --------
#define NMESINPUTPIN 15
#define PULSEDURATION 100      // ms trigger pulse
#define OFFPERIOD 200          // ms non-retriggerable window
// --- MultipleSensors Epromp ---
#define NUM_SENSORS 3
float scaleFactors[NUM_SENSORS];
int activeSensor = 0;
// ---------- Pulse Generator Pins ----------
#define DIGITIMERPIN 13
#define TRIGGEROUTPIN 2
// #define LEDPIN 2 // LED is now linked to Trigger Pin //

#define ON 1
#define OFF (!ON)

enum NMESMode { NONE, DIGITIMER, BEURER };
NMESMode currentMode = NONE;
volatile bool beurerRunPulse = false;
unsigned long beurerLastPulse = 0;
unsigned long beurerTriggerOnTime = 0;

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

  // --- read scale factors -----
  for (int i=0; i < NUM_SENSORS; i++){
    EEPROM.get(eeAddress, scaleFactors[i]);
    if (isnan(scaleFactors[i])){
      scaleFactors[i]= 3108.5f; // defaul fallback
    }
    eeAddress += sizeof(float);
  }

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
  eeAddress += sizeof(offTime);
  // ---- write scale factors to eeprom ----
  for (int i=0; i < NUM_SENSORS; i++){
    EEPROM.put(eeAddress, scaleFactors[i]);
    eeAddress += sizeof(float);
  }

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

void IRAM_ATTR pulseReceivedInterrupt() {
  if (!beurerRunPulse) {
    beurerRunPulse = true;
  }
}

// ---------- HX711 Pins ----------
#define DATA_PIN 14
#define CLK_PIN 12
//#define SCALE 3108.5f old scale fkt for esp32 processing
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
  pinMode(TRIGGEROUTPIN, OUTPUT);
  pinMode(NMESINPUTPIN, INPUT);

  // Beurer NMES Mode
  attachInterrupt(digitalPinToInterrupt(NMESINPUTPIN), pulseReceivedInterrupt, RISING);

  // Pulse generator
  readEEPROM();
  printStatus();
  //pulseTicker.attach_ms(1000 / (frequency * 2), checkPulse); //no autostart anymore

  // HX711
  Serial.println("Initializing force sensor...");
  scale.begin(DATA_PIN, CLK_PIN);
  scale.set_scale(scaleFactors[activeSensor]);
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
    // Pulse generator mode commands
    else if (cmd.equalsIgnoreCase("NMESDigitimer")) {
      currentMode = DIGITIMER;
      pulseTicker.attach_ms(1000 / (frequency * 2), checkPulse);
      Serial.println("Mode set: DIGITIMER");
    }
    else if (cmd.equalsIgnoreCase("NMESBeurer")) {
          currentMode = BEURER;
          pulseTicker.detach();              // stop Digitimer pulses
          digitalWrite(DIGITIMERPIN, OFF);   // ensure low
          Serial.println("Mode set: BEURER");
        }
    else if(cmd.startsWith("SET_SENSOR")){
      int sensor;
      sscanf(cmd.c_str(), "SET_SENSOR %d", &sensor);
      if (sensor >= 1 && sensor <= 3) {
        activeSensor = sensor - 1;
        scale.set_scale(scaleFactors[activeSensor]);
        Serial.print("ACTIVE_SENSOR ");
        Serial.println(sensor);
        }
    }
    else if (cmd.equalsIgnoreCase("INFO")) {

      Serial.print("INFO_ACTIVE_SENSOR ");
      Serial.print(activeSensor + 1);
      Serial.print(" ");
      Serial.println(scaleFactors[activeSensor], 4);
    }
    else if(cmd.startsWith("SET_SCALE")){
      int sensor;
      float newScale;
      sscanf(cmd.c_str(), "SET_SCALE %d %f", &sensor, &newScale);
      if (sensor >= 1 && sensor <= 3 && newScale > 1) {
        scaleFactors[sensor - 1] = newScale;
        if (activeSensor == sensor - 1) {
          scale.set_scale(newScale);
        }
        writeEEPROM();
        Serial.print("SCALE_UPDATED_for ");
        Serial.print(sensor);
        Serial.print(" to ");
        Serial.println(newScale);
      }
    }

    else {
      parsePulseCommand(cmd);
    }
  }

  // --- Pulse timing ---
  if (currentMode == DIGITIMER) {
    unsigned long m = micros();
    if (m >= lastOn + ((onTime + offTime) * 1000UL)) {
      lastOn = m;
      runPulse = true;
      digitalWrite(TRIGGEROUTPIN, ON);
      Serial.println("TRIG");
    }

    if (m >= lastOn + (triggerLength * 1000UL)) {
      digitalWrite(TRIGGEROUTPIN, OFF);
    }

    if (m >= lastOn + (onTime * 1000UL)) {
      runPulse = false;
    }
  }
  if (currentMode == BEURER) {
    // Turn off trigger after pulse duration
    if (beurerTriggerOnTime > 0 &&
        millis() - beurerTriggerOnTime >= PULSEDURATION) {

      digitalWrite(TRIGGEROUTPIN, OFF);
      beurerTriggerOnTime = 0;
    }

    // If interrupt occurred
    if (beurerRunPulse) {

      // Only allow pulse if OFFPERIOD passed
      if (millis() - beurerLastPulse >= OFFPERIOD) {

        digitalWrite(TRIGGEROUTPIN, ON);
        Serial.println("TRIG");

        beurerTriggerOnTime = millis();
      }

      beurerLastPulse = millis();
      beurerRunPulse = false;
    }
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






