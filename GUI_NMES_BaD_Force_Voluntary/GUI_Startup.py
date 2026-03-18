#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
import time
import serial
import glob
import math
import numpy as np
from PyQt6.QtWidgets import QApplication, QWidget, QMessageBox, QInputDialog, QFileDialog
from PyQt6.QtCore import QTimer
from PyQt6.QtMultimedia import QSoundEffect #sound
from PyQt6.QtGui import QColor
from PyQt6.QtCore import QUrl #sound
from PyQt6.QtCore import pyqtSignal
from pyDigitimerNMESForceBeurer_ui import Ui_PyForceSenseWidget  # your compiled UI
from pyDigitimerNMESForceVoluntary import Ui_VolunatryMotionWidget # the second window 
from pyqtgraph import PlotWidget, mkPen, InfiniteLine


BAUD = 115200
SERIAL_TIMER_INTERVAL = 20  # ms
MAXPLOTLENGTH = 100
forceStringPattern = re.compile(r'Force:(\s*[-.0-9]+)')
SOUND_FILE = "beep.wav" 


def serial_ports():
    """ Lists serial port names """
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    result.append("Simulation")
    return result

def load_mean_force_profile(filepath):
    """
    Load a force log file and compute the mean force curve between triggers.
    Returns: (mean_force_array, cycle_time)
    """
    data = np.genfromtxt(
    filepath,
    skip_header=1,
    delimiter=',',
    dtype=None,
    encoding='utf-8',
    names=["time", "force", "other"]
    )

    time = data["time"]
    force = data["force"]   # Convert to N
    time = time - time[0]
    trigger_indices = np.where(data["other"] == 'TRIG')[0]

    if len(trigger_indices) < 2:
        raise ValueError("Not enough triggers found in log file to define cycles.")

    # Interpolate each contraction segment to the same length
    num_points = 200
    segments = []
    for i in range(len(trigger_indices) - 1):
        start, end = trigger_indices[i], trigger_indices[i + 1]
        t_seg = time[start:end] - time[start]
        f_seg = force[start:end]
        t_norm = np.linspace(0, t_seg[-1], num_points)
        f_interp = np.interp(t_norm, t_seg, f_seg)
        segments.append(f_interp)

    mean_curve = np.mean(segments, axis=0)
    cycle_time = time[trigger_indices[1]] - time[trigger_indices[0]]
    t_cycle = np.linspace(0, cycle_time, num_points)  # cycle_time = 1.56 s
    return mean_curve, cycle_time

class PyVoluntaryMotion(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = Ui_VolunatryMotionWidget()
        self.ui.setupUi(self)
        # Add closing option here!
        #connecting Buttons
        self.ui.pushButtonDefaultTargetForceProfile.clicked.connect(self.LoadDefaultTargetForceProfile)
        self.ui.pushButtonLoadTargetForceProfile.clicked.connect(self.LoadUserTargetForceProfile)
        
        #Data containers, Force Tracking
        self.currForce = 0.0
        self.maxForce = 0.0
        self.plotData = []
        self.trigPositions = []
        self.targetData=[]
        self.cycleTime = 1.56 
        #self.currentTime = 0.0
        self.cycleStartTime = time.time()
        
        self.sampleInterval = SERIAL_TIMER_INTERVAL / 1000.0  # 0.02 s sampling
        self.timeData = []

        
        #setup Plot
        self.MAXPLOTLENGTH = 100
        self.yellowPen = mkPen('w', width=1)
        #self.flashPen = pg.mkPen('y', width=4)
        self.forcePlotObj = self.ui.VoluntaryforcePlot.plot (pen=mkPen('w', width=3))
        self.targetPlot = self.ui.VoluntaryforcePlot.plot (pen = mkPen('g', width=3))
        self.ui.VoluntaryforcePlot.setLabel('left', 'Force', units='N')
        self.ui.VoluntaryforcePlot.setLabel('bottom', 'Time', units='s')
        self.ui.VoluntaryforcePlot.setXRange(0, self.cycleTime)
        
        
        #setup SoundEffect
        self.soundEffect = QSoundEffect()
        self.soundEffect.setSource(QUrl.fromLocalFile(SOUND_FILE))
        self.soundEffect.setVolume(0.9)
    
        
    def updateCycleTime(self, cycle_time):
        self.cycleTime = cycle_time if cycle_time > 0 else 1.56 #cycle time in s
        print(f"Cycle time updated: {cycle_time:.3f} s")
        #lock x-axis of plot to cylce time 
        self.ui.VoluntaryforcePlot.setXRange(0, self.cycleTime)
        print("reload target force profile to match cycle time")

            
    def updateForce(self,value):
        self.currForce = value
        # compute elapsed time in current cycle
        elapsed = time.time() - self.cycleStartTime
        # wrap if exceeding cycle 
        if elapsed > self.cycleTime:
            elapsed = 0.0
            self.plotData = []
            self.timeData = []
            
        self.timeData.append(elapsed)
        self.plotData.append(self.currForce)
        
        self.forcePlotObj.setData(self.timeData, self.plotData)
            
        #OLD but BackUP do some magic to make target force run with real force 
        #if len(self.timeData) == 0:
        #    self.timeData.append(0)
        #else:
        #        self.timeData.append(self.timeData[-1] + self.sampleInterval)
       # 
        #if len(self.plotData) > len(self.targetData):
        #    self.plotData.pop(0)
        #    self.timeData.pop(0)
        #self.forcePlotObj.setData(self.timeData, self.plotData)
        #self.targetPlot.setData(np.linspace(0, len(self.targetData)*self.sampleInterval, len(self.targetData)), self.targetData)
       
        
    def addTrigger(self):
        "Draw a vertical line at the current position"
        """Reset force trace and start a new cycle synced with NMES trigger."""
        # reset force trace
        self.cycleStartTime=time.time()
        self.plotData = []
        self.timeData = []
        # remove old trigger lines
        # realy needed?
        # draw new trigger line at x= 0
        line = InfiniteLine(angle=90, movable=False, pen=mkPen('y', width=4), pos=0)
        self.ui.VoluntaryforcePlot.addItem(line)
        self.trigPositions.append(line)
        
        # remove Trig line after 500 ms| make invisivle
        QTimer.singleShot(500, lambda: line.setPen(mkPen('y', width=0)))  # after 0.3 s, revert to normal
        
        self.soundEffect.stop()
        # Play beep
        QTimer.singleShot(0, self.soundEffect.play)  # small delay avoids PyQt6 race conditions
                
    def generateTargetProfile(self, amplitude=5.0):
        num_points = int(self.cycleTime/self.sampleInterval)
        t = np.linspace(0, self.cycleTime, num_points)
        #simple half-sine contraction example
        y = amplitude * np.sin(np.pi * t / self.cycleTime)
        self.targetData = y.tolist() #makes pyhton copy of this data
        self.targetTime = t.tolist() #makes pyhton copy of this data
        
        self.targetPlot.setData(self.targetTime, self.targetData)
        
    def LoadDefaultTargetForceProfile(self):
        # Ask user for amplitude / magnitude
        amplitude, ok = QInputDialog.getDouble(
            self,
            "Set Target Force Amplitude",
            "Enter desired amplitude (N):",
            0.5,    # default value
            0.0,    # min
            100.0,  # max
            2       # decimals
        )
    
        if ok:
            # Optional: also ask for frequency if you want         
            self.generateTargetProfile(amplitude=amplitude)
            t_cycle = np.linspace(0, len(self.targetData)*self.sampleInterval, len(self.targetData))
            self.targetPlot.setData(t_cycle, self.targetData)
            self.ui.VoluntaryforcePlot.setTitle(f"Target: {amplitude:.2f} N")
        else:
            # user cancelled input → do nothing
            return
        
    
    
    def LoadUserTargetForceProfile(self):
            # Ask user to select a log file
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Force Log File",
            "/Volumes/ExtremeSSD/AA_PhD_Projects/NMESOptimization-Local/data/ForceLogFiles/",
            "Text Files (*.txt)"
        )
    
        if not filepath:
            return  # user cancelled
    
        try:
            mean_curve, cycle_time = load_mean_force_profile(filepath)
            # Ask user for scaling factor
            scale_factor, ok = QInputDialog.getDouble(
                self,
                "Scale Target Profile",
                "Enter scale factor:",
                1.0,     # default value
                -100.0,     # minimum
                1000.0,  # maximum
                3        # decimals
            )
            # Apply scaling
            mean_curve = mean_curve * scale_factor
            t_cycle = np.linspace(0, cycle_time, len(self.targetData))
            self.targetData = mean_curve.tolist()
            self.ui.VoluntaryforcePlot.setLabel('bottom', f"Time (0–{cycle_time:.2f}s)", units='s')
            self.targetPlot.setData(t_cycle, self.targetData)
            self.ui.VoluntaryforcePlot.setTitle(f"Loaded mean target profile ({cycle_time:.2f}s cycle)")
        except Exception as e:
            QMessageBox.warning(self, "Error Loading File", f"Failed to load force profile:\n{e}")
    
    def setCycleTime(self, cycleTime):
        self.cycleTime = cycleTime
        # reset x axis for plot
        self.currForcePlot.setXRange(0, self.cycleTime)
        # Optional: regenerate target curve based on this cycle
        freq = 1 / self.cycleTime if self.cycleTime > 0 else 1.0
        self.generateTargetProfile(freq=freq, amplitude=0.5)
        self.targetPlot.setData(self.targetData)
        
    
        


class PyForceSense(QWidget):
        # broadcat force readout to multiple windows 
    forceSignal = pyqtSignal(float) 
    triggerSignal = pyqtSignal()
    cycletimeSignal = pyqtSignal(float)
    # iniate class 
    def __init__(self):
        super().__init__()
        self.ui = Ui_PyForceSenseWidget()
        self.ui.setupUi(self)
        # === Populate COM port combo box ===
        ports = serial_ports()
        if not ports:
            ports = ["No device found"]
        self.ui.comportCombo.addItems(ports)
        
        # Force tracking
        self.curForce = 0.0
        self.maxForce = 0.0
        self.plotData = []
        self.trigPositions = []

        # Setup plot
        self.yellowPen = mkPen('y')
        self.forcePlotObj = self.ui.forcePlot.plot()

        # Serial
        self.serial = None
        self.serialTimer = QTimer()
        self.serialTimer.timeout.connect(self.readSerial)
        

        # Connect buttons
        self.ui.connectButton.clicked.connect(self.serialConnect)
        self.ui.resetMaxBtn.clicked.connect(self.resetMax)
        self.ui.clearButton.clicked.connect(lambda: self.ui.serialOutputText.clear())
        self.ui.resetTareButton.clicked.connect(self.resetTare)
        self.ui.autoNameButton.clicked.connect(self.autoName)
        self.ui.logButton.clicked.connect(self.toggleLog)
        self.ui.pushButtonVoluntaryM.clicked.connect(self.open_voluntaryM_window)
        self.ui.pushButtonScaleFKTInfo.clicked.connect(self.requestScaleInfo)

        # NMES set button
        self.ui.setButton.clicked.connect(self.sendNMESParameters)
        # --- Digitimer NMES checkbox control ---
        #self.ui.checkBoxDigiNMES.stateChanged.connect(self.updateNMESControls)
        #self.updateNMESControls()  # set correct initial state
        
        self.ui.checkBoxBeurerNMES.stateChanged.connect(self.handleNMESModeChange)
        self.ui.checkBoxDigiNMES.stateChanged.connect(self.handleNMESModeChange)
        #  Force correct initial GUI state
        self.handleNMESModeChange()
        
        
        # ScaleFkt Update Buttons
        self.ui.checkBoxUpdateScaleFkt.stateChanged.connect(self.updateScaleFktControls)
        self.ui.pushButton_2_UpdateScaleFkt.clicked.connect(self.sendScaleUpdate)
        # Set correct initial state on startup
        self.updateScaleFktControls()
        # Clear existing items (optional but safe)
        self.ui.comboBox_ToggleDevice.clear()
        
        # Add devices
        self.ui.comboBox_ToggleDevice.addItem("01: GripSensor", 1) #updated for your devices here
        self.ui.comboBox_ToggleDevice.addItem("02: QuadSensor", 2)
        self.ui.comboBox_ToggleDevice.addItem("03: FootSensor", 3)
        self.ui.comboBox_ToggleDevice.currentIndexChanged.connect(self.sendSelectedSensor)



        # Logging
        self.logging = False
        self.logFile = None
        self.autoName()
        
        # --- Stopwatch for logging ---
        self.logStartTime = None
        self.logTimer = QTimer()
        self.logTimer.timeout.connect(self.updateStopwatch)
        
        # --- Init sound effect ---
        self.soundEffect = QSoundEffect()
        self.soundEffect.setSource(QUrl.fromLocalFile(SOUND_FILE))
        self.soundEffect.setVolume(0.9)
        

    # ==================== SERIAL ====================
    def serialConnect(self):
        if self.serial:
            self.serial.close()
            self.serial = None
            self.ui.connectButton.setText("Connect")
            self.serialTimer.stop()
            return

        port = self.ui.comportCombo.currentText()
        if port=="Simulation":
            self.serial = None
            self.simulationTime=0.0
            self.simulationTrigCounter = 0
            self.ui.serialOutputText.appendPlainText("Simulation mode enabled")
            self.serialTimer.start(SERIAL_TIMER_INTERVAL)
        else:
            #real serial communication 
            try:
                self.serial = serial.Serial(port, BAUD, timeout=0.5)
                self.ui.serialOutputText.appendPlainText(f"Opened {port} OK")
            except Exception as e:
                self.ui.serialOutputText.appendPlainText(f"Cannot open serial: {e}")
                self.serial = None
                return
            self.ui.serialOutputText.appendPlainText(f"Serial connected to {port}")
            self.serialTimer.start(SERIAL_TIMER_INTERVAL)
            self.serial.write(b"INFO\n")
            
        self.ui.connectButton.setText("Disconnect")
        
    

    
    #def readSerial(self):
    #    if not self.serial or not self.serial.readable():
    #        return
    #    while self.serial.in_waiting:
    #        line = self.serial.readline().decode(errors='ignore').strip()
    #        self.processSerial(line)
            
    def readSerial(self):
        if self.ui.comportCombo.currentText() == "Simulation":
            #genrate Sinwave force
            self.simulationTime += SERIAL_TIMER_INTERVAL / 1000.0 #to generater seconds
            freq= 1.0
            amplitude = 5.0
            force = amplitude * math.sin(2 * math.pi * freq * self.simulationTime)
            line = f"Force:{force:.2f}"
            self.processSerial(line)
            #generate fake trigger ever 1.57 sec
            trig_interval_ticks =( 3.0 / (SERIAL_TIMER_INTERVAL / 1000.0)) #to generater seconds)
            self.simulationTrigCounter += 1
            if self.simulationTrigCounter >= trig_interval_ticks:
                self.simulationTrigCounter = 0
                self.processSerial("TRIG")
                
        elif self.serial and self.serial.readable():
            while self.serial.in_waiting:
                line = self.serial.readline().decode(errors='ignore').strip()
                if line:
                    if not line.startswith("Force:"):
                        self.ui.serialOutputText.appendPlainText(f"[RAW] {line}")
                self.processSerial(line)


    def processSerial(self, line):
        m = forceStringPattern.match(line)
        if m:
            self.curForce = float(m.group(1))
            self.forceSignal.emit(self.curForce) # sends the force signal, all open windows can rececie it 
            if self.curForce > self.maxForce:
                self.maxForce = self.curForce
            if self.logging and self.logFile:
                self.logFile.write(f"{time.time()},{self.curForce},\n")
            self.updateUi()
        elif line.upper() == "TRIG":
            self.trigPositions.append(self.makeLine(len(self.plotData)))
            self.ui.serialOutputText.appendPlainText("TRIG")
            self.triggerSignal.emit() #emit rigger signal to second window
            # --- Play sound here ---
            #if not self.soundEffect.isPlaying():
                #self.soundEffect.play()  # <-- Play sound on trigger
            if self.logging and self.logFile:
                self.logFile.write(f"{time.time()},,TRIG\n")
        elif line.startswith("Pulse Status:"):
            try:
                parts = line.split(":")[1].strip().split(",")
                freq = float(parts[0])
                onTime = float(parts[1])
                offTime = float(parts[2])
                cycleTime = onTime + offTime
                self.ui.serialOutputText.appendPlainText(f"NMES status: freq={freq}, on={onTime}, off={offTime}, cycle={cycleTime}")
                if hasattr(self, "voluntaryM_window"):
                    self.voluntaryM_window.setCycleTime(cycleTime)
            except Exception as e:
                self.ui.serialOutputText.appendPlainText(f"Error parsing status: {e}")
        elif line.startswith("INFO"):
            # Display info in dedicated GUI box
            try:
                parts = line.split()
                sensor_number = int(parts[1])
                self.updateSensorCombo(sensor_number)
                self.ui.serialOutputText.appendPlainText(f"[Device INFO RECEIVED]:, {line}\n")
            except:
                self.ui.serialOutputText.appendPlainText("Eorr Parsing Active Sensor response")
                    
        else:
            self.ui.serialOutputText.appendPlainText(line)
            if self.logging and self.logFile:
                self.logFile.write(f"{time.time()},,{line}\n")

    #serial communication for NMES Beurer/Digitimer Mode
    def handleNMESModeChange(self):

        digi = self.ui.checkBoxDigiNMES.isChecked()
        beurer = self.ui.checkBoxBeurerNMES.isChecked()
    
        # Prevent both checked
        if digi and beurer:
            sender = self.sender()
            if sender == self.ui.checkBoxDigiNMES:
                self.ui.checkBoxBeurerNMES.setChecked(False)
            else:
                self.ui.checkBoxDigiNMES.setChecked(False)
        self.updateNMESControls()
        # Send mode only if serial connected
        if not self.serial:
            return
    
        if self.ui.checkBoxDigiNMES.isChecked():
            self.serial.write(b"NMESDigitimer\n")
            self.ui.serialOutputText.appendPlainText("Sent: NMESDigitimer")
    
        elif self.ui.checkBoxBeurerNMES.isChecked():
            self.serial.write(b"NMESBeurer\n")
            self.ui.serialOutputText.appendPlainText("Sent: NMESBeurer")
    
        else:
            # No mode selected
            self.serial.write(b"NMESNone\n")
            self.ui.serialOutputText.appendPlainText("Sent: NMESNone")
    ## Scale Info Button 
    # ==================== ScaleFkt Info and Update ====================
    def requestScaleInfo(self):
        if self.ui.comportCombo.currentText() == "Simulation":
            # Fake response for testing
            self.processSerial("INFO: Simulation Scale | ScaleFkt:128 ")
            return
    
        if not self.serial:
            QMessageBox.warning(self, "No Serial", "Connect to ESP32 first!")
            return
    
        try:
            self.serial.write(b"INFO\n")
            self.ui.serialOutputText.appendPlainText("Sent: INFO")
        except Exception as e:
            QMessageBox.warning(self, "Serial Error", f"Failed to send INFO:\n{e}")
    def updateScaleFktControls(self):
        enabled = self.ui.checkBoxUpdateScaleFkt.isChecked()
    
        self.ui.ScaleFktUpdate.setEnabled(enabled)
        self.ui.label_7_updateto.setEnabled(enabled)
        self.ui.lineEdit_SkaleFkt.setEnabled(enabled)
        self.ui.label_8_fordevice.setEnabled(enabled)
        self.ui.spinBoxDeviceNumber.setEnabled(enabled)
        self.ui.pushButton_2_UpdateScaleFkt.setEnabled(enabled)
        
    def sendScaleUpdate(self):
        if not self.serial:
            self.ui.serialOutputText.appendPlainText("Error: Serial not connected")
            return 
        # get devive number
        sensor_number = self.ui.spinBoxDeviceNumber.value()
        #get scale fkt 
        scalefkt_text = self.ui.lineEdit_SkaleFkt.text().strip()
        try:
            new_scale_fkt = float(scalefkt_text)
        except ValueError:
            self.ui.serialOutputText.appendPlainText("Error.Ivalid Scale Fkt. Enter a floating value")
            return
        command = f"SET_SCALE {sensor_number} {new_scale_fkt}\n"
        #send serial command 
        self.serial.write(command.encode())
        self.ui.serialOutputText.appendPlainText(f"Sent:{command.strip()}")
        
    def sendSelectedSensor(self):
        # Make sure serial is connected
        if not self.serial:
            self.ui.serialOutputText.appendPlainText("Error: Serial not connected.")
            return
    
        # Get selected device number (from userData)
        device_number = self.ui.comboBox_ToggleDevice.currentData()
    
        if device_number is None:
            return
    
        # Build command
        command = f"SET_SENSOR {device_number}\n"
    
        # Send to ESP32
        self.serial.write(command.encode())
    
        # Log in GUI
        self.ui.serialOutputText.appendPlainText(f"Sent: {command.strip()}")

    def updateSensorCombo(self, sensor_number):
        combo = self.ui.comboBox_ToggleDevice
    
        # Block signal so we don't send SET_SENSOR again
        combo.blockSignals(True)
    
        # Find item with matching userData
        for i in range(combo.count()):
            if combo.itemData(i) == sensor_number:
                combo.setCurrentIndex(i)
                break
    
        combo.blockSignals(False)
    
        self.ui.serialOutputText.appendPlainText(
            f"GUI updated to ACTIVE_SENSOR {sensor_number}"
        )
        
    #def makeLine(self, value):
    #    line = PlotWidget.InfiniteLine(angle=90, movable=False, pen=self.yellowPen, pos=value)
    #    self.ui.forcePlot.addItem(line)
    #    return line
    def makeLine(self, value):
        line = InfiniteLine(angle=90, movable=False, pen=self.yellowPen, pos=value)
        self.ui.forcePlot.addItem(line)
        return line


    def updateUi(self):
        self.ui.curForceLabel.setText(f"{self.curForce:.2f}")
        self.ui.maxForceLabel.setText(f"{self.maxForce:.2f}")
        self.plotData.append(self.curForce)

        while len(self.plotData) > MAXPLOTLENGTH:
            self.plotData.pop(0)
            while self.trigPositions and self.trigPositions[0].value() <= 0:
                self.ui.forcePlot.removeItem(self.trigPositions[0])
                self.trigPositions.pop(0)
            for line in self.trigPositions:
                line.setValue(line.value() - 1)

        self.forcePlotObj.setData(self.plotData)

    # ==================== LOGGING ====================
    def resetMax(self):
        self.maxForce = 0.0
        self.updateUi()

    def resetTare(self):
        if self.serial:
            ans = QMessageBox.warning(self, "Reset Tare", "Resetting tare. Are you sure?", 
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ans == QMessageBox.StandardButton.Yes:
                self.serial.write(b"RESET\n")

    def autoName(self):
        self.ui.logName.setText(f"Log_{time.strftime('%Y-%m-%d_%H.%M.%S')}.txt")

    def toggleLog(self):
        if self.logging:
            self.logging = False
            self.ui.logButton.setText("Start logging")
            if self.logFile:
                self.logFile.close()
                self.logFile = None
            self.logTimer.stop()
            self.logStartTime = None
            self.ui.serialOutputText.appendPlainText(">>> Logging stopped.")
        
        else:
            self.logFile = open(self.ui.logName.text(), 'w')
            self.logFile.write("time,force,other\n")
            self.logging = True
            # Start stopwatch
            self.logStartTime = time.time()
            self.logTimer.start(100)  # update every 100 ms
            self.ui.logButton.setText("Stop logging")
            self.ui.serialOutputText.appendPlainText(f">>> Logging started → {self.ui.logName.text()}")

    def updateStopwatch(self):
        if self.logStartTime is None:
            return
    
        elapsed = time.time() - self.logStartTime
    
        # Format as mm:ss or hh:mm:ss
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
    
        if hours > 0:
            text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            text = f"{minutes:02d}:{seconds:02d}"
    
        self.ui.OnTimeDisyplay.display(text)
    # ==================== NMES CONTROL ====================
    def updateNMESControls(self):
        enabled = self.ui.checkBoxDigiNMES.isChecked()

        # Enable/disable all NMES related widgets
        self.ui.freqSpin.setEnabled(enabled)
        self.ui.onSpin.setEnabled(enabled)
        self.ui.offSpin.setEnabled(enabled)
        self.ui.setButton.setEnabled(enabled)
    
    def sendNMESParameters(self):
        if not self.ui.checkBoxDigiNMES.isChecked():
            QMessageBox.warning(self, "Digitimer NMES Disabled", 
                            "Enable 'Digitimer NMES' checkbox first.")
            return
        if not self.serial:
            QMessageBox.warning(self, "No Serial", "Connect to ESP32 first!")
            return
        freq = self.ui.freqSpin.value()
        on_time = self.ui.onSpin.value()
        off_time = self.ui.offSpin.value()
        cycle_time = (on_time + off_time)/1000 #ms to s
        self.cycletimeSignal.emit(cycle_time)
        cmd = f"{freq},{on_time},{off_time}\n"
        self.serial.write(cmd.encode())
        self.ui.serialOutputText.appendPlainText(f"Sent NMES: {cmd.strip()}")
    # ==================== Open Second Window for Voluntary Motion Control ====================   
    def open_voluntaryM_window(self):
        self.voluntaryM_window = PyVoluntaryMotion()
        self.forceSignal.connect(self.voluntaryM_window.updateForce) #connecting stremed signal for function
        self.triggerSignal.connect(self.voluntaryM_window.addTrigger) #connecting streamd signal to function
        self.cycletimeSignal.connect(self.voluntaryM_window.updateCycleTime) #connection streamd signla to function
        self.voluntaryM_window.show()
        self.voluntaryM_window.raise_()
        self.voluntaryM_window.activateWindow()
        
        # request NMES paratmers to scale plot
        if self.ui.comportCombo.currentText() == "Simulation":
            line = "Pulse Status: 35,2,3"
            self.processSerial(line)
        elif self.serial:
            self.serial.write(b"?\n")
            self.ui.serialOutputText.appendPlainText("Requested NMES status (?)")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PyForceSense()
    window.show()
    sys.exit(app.exec())
