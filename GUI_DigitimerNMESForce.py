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
from pyDigitimerNMESForce import Ui_PyForceSenseWidget  # your compiled UI
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
    force = data["force"] * 9.81  # Convert to N
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
        
        self.sampleInterval = SERIAL_TIMER_INTERVAL / 1000.0  # 0.02 s sampling
        self.timeData = []

        
        #setup Plot
        self.MAXPLOTLENGTH = 100
        self.yellowPen = mkPen('w', width=1)
        #self.flashPen = pg.mkPen('y', width=4)
        self.forcePlotObj = self.ui.VoluntaryforcePlot.plot (pen='w')
        self.targetPlot = self.ui.VoluntaryforcePlot.plot (pen = 'r')
        self.ui.VoluntaryforcePlot.setLabel('left', 'Force', units='N')
        self.ui.VoluntaryforcePlot.setLabel('bottom', 'Time', units='s')
        
        #setup SoundEffect
        self.soundEffect = QSoundEffect()
        self.soundEffect.setSource(QUrl.fromLocalFile(SOUND_FILE))
        self.soundEffect.setVolume(0.9)
        
    
            
    def updateForce(self,value):
        self.currForce = value
        if self.currForce > self.maxForce:
            self.maxForce = self.currForce
        self.plotData.append(self.currForce)
            
        #do some magic to make target force run with real force 
        if len(self.timeData) == 0:
            self.timeData.append(0)
        else:
                self.timeData.append(self.timeData[-1] + self.sampleInterval)
        
        if len(self.plotData) > len(self.targetData):
            self.plotData.pop(0)
            self.timeData.pop(0)
        
        # scroll like main window
        #while len(self.plotData) > self.MAXPLOTLENGTH:
        #    self.plotData.pop(0)
        #    while self.trigPositions and self.trigPositions[0].value() <= 0:
        #        self.ui.VoluntaryforcePlot.removeItem(self.trigPositions[0])
        #        self.trigPositions.pop(0)
        #    for line in self.trigPositions:
        #        line.setValue(line.value() - 1)

        self.forcePlotObj.setData(self.timeData, self.plotData)
        self.targetPlot.setData(np.linspace(0, len(self.targetData)*self.sampleInterval, len(self.targetData)), self.targetData)
        # self.targetPlot.setData(self.targetData)
        
    def addTrigger(self):
        "Draw a vertical line at the current position"
        """Reset force trace and start a new cycle synced with NMES trigger."""
        # Clear previous force/time data
        self.plotData = []
        self.timeData = []
        line = InfiniteLine(angle=90, movable=False, pen=self.yellowPen, pos=0)
        self.ui.VoluntaryforcePlot.addItem(line)
        self.trigPositions.append(line)
        
        
        line.setPen(mkPen('y', width=4))  # immediately make the line red and thicker
        QTimer.singleShot(300, lambda: line.setPen(self.yellowPen))  # after 0.3 s, revert to normal
        # Play sound only if ready
        #if self.soundEffect.status() == QSoundEffect.Status.Ready:
        #    self.soundEffect.play()
        # Stop any current sound to avoid overlaps
        self.soundEffect.stop()
        # Play beep
        QTimer.singleShot(0, self.soundEffect.play)  # small delay avoids PyQt6 race conditions
                
    def generateTargetProfile(self, freq=1.0, amplitude=5.0):
        t = np.linspace(0, self.MAXPLOTLENGTH, self.MAXPLOTLENGTH)
        y = amplitude * np.sin(2 * np.pi * freq * t / self.MAXPLOTLENGTH)
        self.targetData = y.tolist()
        
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
            self.generateTargetProfile(freq=1.0, amplitude=amplitude)
            self.targetPlot.setData(self.targetData)
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
            self.targetData = mean_curve.tolist()
            self.ui.VoluntaryforcePlot.setLabel('bottom', f"Time (0–{cycle_time:.2f}s)", units='s')
            self.targetPlot.setData(self.targetData)
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

        # NMES set button
        self.ui.setButton.clicked.connect(self.sendNMESParameters)

        # Logging
        self.logging = False
        self.logFile = None
        self.autoName()
        
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
        else:
            self.ui.serialOutputText.appendPlainText(line)
            if self.logging and self.logFile:
                self.logFile.write(f"{time.time()},,{line}\n")

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
            self.ui.serialOutputText.appendPlainText(">>> Logging stopped.")
        
        else:
            self.logFile = open(self.ui.logName.text(), 'w')
            self.logFile.write("time,force,other\n")
            self.logging = True
            self.ui.logButton.setText("Stop logging")
            self.ui.serialOutputText.appendPlainText(f">>> Logging started → {self.ui.logName.text()}")

    # ==================== NMES CONTROL ====================
    def sendNMESParameters(self):
        if not self.serial:
            QMessageBox.warning(self, "No Serial", "Connect to ESP32 first!")
            return
        freq = self.ui.freqSpin.value()
        on_time = self.ui.onSpin.value()
        off_time = self.ui.offSpin.value()
        cmd = f"{freq},{on_time},{off_time}\n"
        self.serial.write(cmd.encode())
        self.ui.serialOutputText.appendPlainText(f"Sent NMES: {cmd.strip()}")
    # ==================== Open Second Window for Voluntary Motion Control ====================   
    def open_voluntaryM_window(self):
        self.voluntaryM_window = PyVoluntaryMotion()
        self.forceSignal.connect(self.voluntaryM_window.updateForce) #connecting stremed signal for function
        self.triggerSignal.connect(self.voluntaryM_window.addTrigger) #connecting streamd signal to function
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
