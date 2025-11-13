# Open-KneeExtensor-Force
Knee extensor force sensor documentation and code files etc.

# PyDigitimer NMES Force GUI

A PyQt6-based graphical user interface (GUI) for controlling neuromuscular electrical stimulation (NMES) parameters on the **Digitimer DS7A/DS7R** stimulator and visualizing **voluntary motion feedback** through real-time force plotting.

This repository also includes the **ESP32 code** used for acquiring force sensor data and communicating with the GUI over a serial connection.  

## 🔌 System Overview


+--------------------+ +-------------------+
| PyQt6 GUI | <--> | ESP32 Board |
| (Force Plot, NMES) | UART | (Force Sensor I/O)|
+--------------------+ +-------------------+
| |
| USB Serial | Analog / Digital
v v
+------------------+ +------------------+
| Digitimer DS7A/R | | Force Sensor |
+------------------+ +------------------+


The interface application provides two main modes:
1. **NMES Control Panel** — control and log Digitimer DS7 pulse train parameters (frequency, on/off timing, etc.)
2. **Voluntary Motion Feedback** — visualize voluntary contraction force and load target force profiles.

---

## 🧠 Features

### 🖥 GUI (Python / PyQt6)
- Control Digitimer DS7A/DS7R stimulation parameters:
  - Frequency (1–200 Hz)
  - On/off durations (100–10,000 ms)
- Real-time serial data streaming from the ESP32.
- Live force feedback visualization using **pyqtgraph**.
- Logging of stimulation and force data.
- Calibration and reset tools (Max/Tare).
- Launch a **Voluntary Motion Feedback** window for target tracking tasks.
- Load or reset default target force profiles.

### ⚙️ ESP32 Firmware
- Acquires force sensor data (e.g. via analog amplifier or load cell ADC).
- Sends continuous data streams over UART/USB serial.
- Can optionally trigger NMES commands or synchronization signals.
- Communicates directly with the Python GUI.
  
---

## 🧰 Requirements

Make sure you have the following Python environment:

```bash
python >= 3.10
PyQt6 >= 6.9.1
pyqtgraph >= 0.13.7
pyserial >= 3.5
numpy

pip install -r requirements.txt

## 🧑‍💻 Author

Developed by Sabine Räuber,
BAMM, DBE, University of Basel
