# Open-KneeExtensor-Force
Knee extensor force sensor documentation and code files etc.



## 🔌 System Architecture

At the core of the system is an ESP32 with a custom shield, which acts as the central hub for all signal routing, acquisition, and triggering.

The ESP32 interfaces with stimulation devices, sensors, and the MRI scanner, while a PyQt6-based GUI running on a host computer provides full control over all modes via USB.
🧭 System Schematic
```text
                           +----------------------+
                           |      PyQt6 GUI       |
                           |  (Control & Display) |
                           +----------+-----------+
                                      |
                                      | USB (Serial)
                                      v
                           +----------------------+
                           |       ESP32 +        |
                           |        Shield        |
                           +----+----+----+-------+
                                |    |    |
        ------------------------+    |    +------------------------
        |                             |                             |
        |                             |                             |
        v                             v                             v

+------------------+     +----------------------+     +----------------------+
|   Load Cell      |     |  NMES Beurer (Ch2)   |     |   Digitimer DS7A/R   |
| (via Ethernet)   |     |      Input Signal    |     |   Pulse Generator    |
+------------------+     +----------------------+     +----------------------+

                                |
                                |
                                v
                        +------------------+
                        |   MRI Scanner    |
                        | (Trigger Input)  |
                        +------------------+
```


## 🔧 Wiring: Load Cell → Ethernet Interface

The load cell is connected to the ESP32 shield via an Ethernet cable. The following mapping defines how each load cell wire is routed to the Ethernet connector pins. Multiple load cells can be connected in parallel to increase total measurable force while maintaining a single signal output.
🧭 Wiring Diagram
```text
Load Cell                          Ethernet Cable 
-----------                        ----------------------
 Red   (VCC / E+)   -------------> Pin 1

 White (DATA / A−)  -------------> Pin 2

 Green (CLK / A+)   -------------> Pin 3

 Black (GND / E−)   -------------> Pin 6

 Shield (Bare)      -------------> Shield (Connector Housing)
```



## 🔄 Signal Capabilities

The ESP32 system supports the following signal pathways:

📥 Input

Force data from load cell (via Ethernet connection)

Stimulation signal from NMES Beurer (Channel 2)

📤 Output

Trigger signal to MRI scanner

Pulse control signal to Digitimer DS7A/R

🔁 Bidirectional Control

Full communication with GUI via USB (serial)

## 🎛️ Operation Modes

The GUI controls the system and can operate in three distinct modes:

1. ⚡ NMES Beurer Mode (Synchronized Input Mode)

Receives stimulation signal from NMES Beurer (Channel 2)

Detects timing of incoming pulses

Generates a synchronized trigger signal to the MRI scanner

✅ Use case:

Synchronizing externally generated stimulation with MRI acquisition

2. 🔋 Digitimer Mode (Pulse Generation Mode)

GUI defines stimulation parameters:

Frequency

Pulse width

Train timing

ESP32 sends:

Control signal to Digitimer DS7A/R

Simultaneous trigger signal to MRI scanner

✅ Use case:

Fully controlled electrical stimulation experiments

3. 💪 Voluntary Motion Mode (Force Feedback Mode)

GUI generates configurable trigger signals

Trigger is sent to:

MRI scanner

Feedback interface (second display window)

Simultaneously:

Force is acquired from the load cell

Participant sees:

Real-time force output

Target force profile

Synchronized visual + audio cues

✅ Use case:

Motor control and neurofeedback experiments


## 🧑‍💻 Author

Developed by Sabine Räuber,
BAMM, DBE, University of Basel
