#!/usr/bin/env python
########################
#program name: gfConnect.py
#Author: S Taylor
#Date: 15-Jun-19
#Purpose: Proof of concept for connecting and controlling the Grainfather Connect Boiler Controller from my RPI (2 - with bluetooth dongle & 3)
#Version: 0.1
#Requires:  RPI (or Linux host!), Bluez, Bluepy (Python moodule), Python 2.7
########################
#Caller info: python gfConnect.py <GF Controller BLE Address> <command>
#<GF Controller address> = ble address for GF Controller
#<command> = enclosed command (including trailing commas where necessary) for activating functions on GF controller.
#Example run command: python gfConnect.py BB:A0:50:12:09:1G '$70,'
#########################
#command list so far:
#timer: Sx where x = mins to set - example: S1 for 1 minute timer, S5 for five minute timer.
#cancel: C0
#cancel timer: C
#pause or resume: G
#temp up: U
#temp down: D
#heat toggle: H
#pump toggle: P
#temp set point: $X, where X = temp value. Note the trailing comma - example: to set target temp to 70C, $70,
#delayed heating: Bx,y, where x = minutes, y = seconds. use C0 to cancel this function. Example: B2,0,
#set button press: T
#skip to: NX,0,0,0,0,1, - where X is step number. Count mash steps, sparge,
#                         boil and hopstand.  E.g. 3 mash steps (inc mash out),
#                         sparge, boil and hopstand: skip to hopstand would
#                         be N6,0,0,0,0,1,

#Status notifications:
#T0,0,0,0,ZZZZZZZZ : timer?
#X60.0,21.1,ZZZZZZ : temp setpoint and temp status
#Y0,0,0,0,0,0,0,0, : guessing pump or heat
#W0,0,0,0,0,0,ZZZZ : guessing pump or heat

#TBD: receipe mode options. - Connect controller characteristic seems to need 6 inputs for recipe mode.

###example recipe: simple 60 min recipe with no hop additions:
#R60,2,14.3,16.9,
#0,0,1,0,0,
#TEST SCHEDULE1
#0,0,0,0,
#65:60,
#75:10,

### example recipe
#"R90,2,17,15.3,", # 5 min boil, 2 mash steps, 17 mash water, 15.3 sparge
#"0,0,1,0,0,",  # mash additions, sparge indicator off, sparge water remind on
#"RECIPEE RECIPEE REC", # Recipe name, max 19 chars, capital letters
#"22,3,1,0,", # 22 min hopstand, 3 boil additions, boil control active
#"60,",       # first boil addition
#"15,",       # second boil addition
#"10,",       # third boil addition
#"23:1,",     # first mash step
#"23:1,"      # second mash step

###other stuff to be confirmed:

#set mash step 1 to 65C for 60 minutes: 'a1,60,65,'
# simple inquiry example

# "c2" : sets target to 0C and displays heat bar in display, not sure why.


import bluepy.btle as btle
import sys
import getopt
import time
import string

class ScanDelegate(btle.DefaultDelegate):
  def __init__(self):
    btle.DefaultDelegate.__init__(self)

  def handleDiscovery(self, dev, isNewDev, isNewData):
    if isNewDev:
      print("Discovered device %s" % dev.addr)
    elif isNewData:
      print("Received new data from %s" % dev.addr)

class GFDelegate(btle.DefaultDelegate):
  def __init__(self, hndl):
    btle.DefaultDelegate.__init__(self)
    self.hndl = hndl;

  def handleNotification(self, cHandle, data):
        if (cHandle == self.hndl):
            #print("data: %s" % data)
            payload = data[1:].split(',')
            if data[0] == 'X':
                Grainfather.parameters["setpoint"] = payload[0]
                Grainfather.parameters["temperature"] = payload[1]
            if data[0] == 'Y':
                Grainfather.parameters["heater_power"] = payload[0]
                Grainfather.parameters["pump_status"] = payload[1]
                Grainfather.parameters["auto_mode_status"] = payload[2]
                Grainfather.parameters["stage_ramp_status"] = payload[3]
                Grainfather.parameters["interaction_mode_status"] = payload[4]
                Grainfather.parameters["interaction_code"] = payload[5]
                Grainfather.parameters["stage_number"] = payload[6]
                Grainfather.parameters["delayed_heat_mode"] = payload[7]
            if data[0] == 'W':
                Grainfather.parameters["heater_percentage"] = payload[0]
                Grainfather.parameters["timer_paused"] = payload[1]
                Grainfather.parameters["step_mash_mode"] = payload[2]
                Grainfather.parameters["recipe_interrupted"] = payload[3]
                Grainfather.parameters["manual_power_mode"] = payload[4]
                Grainfather.parameters["sparge_alert_mode"] = payload[5]
            if data[0] == 'T':
                Grainfather.parameters["timer_active"] = payload[0]
                Grainfather.parameters["time_left_mins"] = payload[1]
                Grainfather.parameters["total_start_time"] = payload[2]
                Grainfather.parameters["time_left_secs"] = payload[3]
            if data[0] == 'C':
                Grainfather.parameters["boil_temperature"] = payload[0]
            if data[0] == 'I':
                Grainfather.parameters["interaction_code2"] = payload[0]
        else:
            print("handleNotification handle 0x%04X unknown" % (cHandle))

def pad_command(arg1):
  #GF Connect seems to require a max of 19 characters for commands
  outMsg = arg1.ljust(19)
  return outMsg

def scan():
  scanner = btle.Scanner().withDelegate(ScanDelegate())
  devices = scanner.scan(10.0)
  gfs = []
  for dev in devices:
    for (adtype, desc, value) in dev.getScanData():
      if desc == "Complete Local Name" and value == "Grain":
        gfs.append(dev.addr)
  del(scanner)
  return gfs

class Grainfather:
  notifOn = b"\x01\x00"
  notifOff = b"\x00\x00"
  GATTUUID = "0000cdd0-0000-1000-8000-00805f9b34fb"
  WRITEUUID = "0003cdd2-0000-1000-8000-00805f9b0131"
  NOTIFYUUID = "0003cdd1-0000-1000-8000-00805f9b0131"
  parameters = {}

  def __init__(self):
    self.mac = None
    self.peripheral = None
    self.writechar = None
    self.notifychar = None
    self.notifyhandle = None
    self.mashsteps = 0
    self.hopstand = 0
    #self.parameters = {}

  def write(self, cmd):
    if self.peripheral:
      self.writechar.write(pad_command(cmd.encode()), False)

  def subscribe(self):
    if self.peripheral:
      #print("Enabling notifications...")
      char = self.peripheral.getCharacteristics(uuid=self.NOTIFYUUID)[0]
      ccc_desc = char.getDescriptors(forUUID=0x2902)[0]
      ccc_desc.write(self.notifOn, withResponse=True)
      #print("\tDone")
      for i in range(10):
          self.peripheral.waitForNotifications(1.0)
          if self.peripheral.waitForNotifications(1.0):
              #print("Notification received")
              continue
          #print("Waiting for notifications...")
          time.sleep(0.1)

  def unsubscribe(self):
    "FIXME: to be implemented"
    pass

  def set_temp(self, temp):
    self.write("$%i," % temp)

  def beep(self):
    self.write("!")

  def status(self):
    pass

  def toggle_pump(self):
    self.write("P")

  def quit_session(self):
    self.write("Q1")

  def cancel(self):
    self.write("C0,")

  def cancel_timer(self):
    self.write("C")

  def pause(self):
    self.write("G")

  def timer(self, minutes):
    self.write("S%i" % minutes)

  def toggle_heat(self):
    self.write("H")

  def temp_up(self):
    self.write("U")

  def temp_down(self):
    self.write("D")

  def delayed_heating(self, minutes):
    self.write("B%i,0," % minutes)

  def press_set(self):
    self.write("P")

  def skip_to_sparge(self):
    self.write("N%i,0,0,0,0,1," % self.mashsteps + 1)

  def skip_to_boil(self):
    self.write("N%i,0,0,0,0,1," % self.mashsteps + 2)

  def skip_to_hopstand(self):
    if self.hopstand == 1:
      self.write("N%i,0,0,0,0,1," % self.mashsteps + 3)

  def connect(self, mac=""):
    if mac:
      self.mac = mac
    self.peripheral = btle.Peripheral(self.mac)
    services = self.peripheral.getServices()
    gfService = self.peripheral.getServiceByUUID(self.GATTUUID)
    self.writechar = gfService.getCharacteristics(self.WRITEUUID)[0]
    self.writehandle = gfService.getCharacteristics(self.WRITEUUID)[0].getHandle()
    self.notifychar = gfService.getCharacteristics(self.NOTIFYUUID)[0]
    self.notifyhandle = gfService.getCharacteristics(self.NOTIFYUUID)[0].getHandle()
    self.peripheral.withDelegate(GFDelegate(self.notifyhandle))

  def disconnect(self):
    if self.peripheral:
      self.peripheral.disconnect()

  def __del__(self):
    self.disconnect()

  def set_recipe(self, name, boiltime, mashsteps, fillvol, spargevol,
      boiladditions, boilpowerctrl=1, hopstand=0, spargeindicator=1,
      wateradditions=1, spargewaterremind=1):
    self.mashsteps = len(mashsteps)
    self.hopstand = hopstand
    cmds = ["R%i,%i,%.1f,%1f," % (boiltime, len(mashsteps), fillvol,
      spargevol)]
    cmds.append("%i,%i,%i,0,0," %
            (wateradditions, spargeindicator, spargewaterremind))
    cmds.append(name[0:19].upper())
    cmds.append("%i,%i,%i,0," % (hopstand, len(boiladditions), boilpowerctrl))
    for a in boiladditions:
      cmds.append("%i," % a)
    for mashstep in mashsteps:
      cmds.append("%i:%i," % mashstep)

    for cmd in cmds:
      self.write(cmd)
      time.sleep(0.1)


if __name__ == '__main__':
  mac = ""
  optlist, args = getopt.getopt(sys.argv[1:], 'b:h', ['device=', 'help'])
  for opt, optval in optlist:
    if opt in ("-h", "--help"):
      sys.exit("Usage:\n  %s [-b<MAC>] [--device=<MAC>] [command]" %
          sys.argv[0])
    if opt in ("-b", "--device"):
      mac=optval
  rawcmd = " ".join(args).encode()
  if not mac:
    mac = scan()[0]
  gf = Grainfather()
  gf.connect(mac)

  if rawcmd:
    gf.write(rawcmd)
  else:
    gf.subscribe()
    print("Current Setpoint: %s" % gf.parameters["setpoint"])
    print("Current Temperature: %s" % gf.parameters["temperature"])
    print("Heater Power: %s" % gf.parameters["heater_power"])
    print("Pump Status: %s" % gf.parameters["pump_status"])
    print("Auto Mode Status: %s" % gf.parameters["auto_mode_status"])
    print("Stage Ramp Status: %s" % gf.parameters["stage_ramp_status"])
    print("Interaction Mode Status: %s" % gf.parameters["interaction_mode_status"])
    print("Interaction Code: %s" % gf.parameters["interaction_code"])
    print("Stage Number: %s" % gf.parameters["stage_number"])
    print("Delayed Heat Mode: %s" % gf.parameters["delayed_heat_mode"])
    print("Heat Power Output Percentage: %s" % gf.parameters["heater_percentage"])
    print("Is Timer Paused: %s" % gf.parameters["timer_paused"])
    print("Step Mash Mode: %s" % gf.parameters["step_mash_mode"])
    print("Is Recipe Interrupted: %s" % gf.parameters["recipe_interrupted"])
    print("Manual Power Mode: %s" % gf.parameters["manual_power_mode"])
    print("Sparge Water Alert Displayed: %s" % gf.parameters["sparge_alert_mode"])
    print("Timer Active: %s" % gf.parameters["timer_active"])
    print("Time Left (Minutes): %s" % gf.parameters["time_left_mins"])
    print("Timer Total Start Time: %s" % gf.parameters["total_start_time"])
    print("Time Left (Seconds): %s" % gf.parameters["time_left_secs"])
    #print("Boil Temperature: %s" % gf.parameters["boil_temperature"])
    #print("Interaction Code 2: %s" % gf.parameters["interaction_code2"])
    # Test some stuff

    #gf.quit_session()
    # gf.toggle_pump()
    # name = "test recipe with a too long name".upper()
    # boiltime = 90
    # mashsteps = ((45,10), (67, 60), (75, 10))
    # fillvol = 16.7
    # spargevol = 13.3
    # boiladditions = (60, 30, 15)
    # gf.set_recipe(name, boiltime, mashsteps, fillvol, spargevol, boiladditions,
    #         hopstand=10)
    # time.sleep(1)

  time.sleep(0.5)
  del(gf)
