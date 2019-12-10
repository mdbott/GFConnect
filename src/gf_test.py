from __future__ import print_function
import argparse
import binascii
import os
import sys
import time
import struct
from bluepy import btle
from binascii import hexlify

print("Hello")


class MyDelegate(btle.DefaultDelegate):
    def __init__(self, hndl):
        btle.DefaultDelegate.__init__(self)
        #print("handleNotification init")
        self.hndl = hndl
    def handleNotification(self, cHandle, data):
        if (cHandle == self.hndl):
            #print("data: %s" % data)
            payload = data[1:].split(',')
            if data[0] == 'X':
                print("Current Setpoint: %s" % payload[0])
                print("Current Temperature: %s" % payload[1])
            if data[0] == 'Y':
                print("Heater Power: %s" % payload[0])
                print("Pump Status: %s" % payload[1])
                print("Auto Mode Status: %s" % payload[2])
                print("Stage Ramp Status: %s" % payload[3])
                print("Interaction Mode Status: %s" % payload[4])
                print("Interaction Code: %s" % payload[5])
                print("Stage Number: %s" % payload[6])
                print("Delayed Heat Mode: %s" % payload[7])
            if data[0] == 'W':
                print("Heat Power Output Percentage: %s" % payload[0])
                print("Is Timer Paused: %s" % payload[1])
                print("Step Mash Mode: %s" % payload[2])
                print("Is Recipe Interrupted: %s" % payload[3])
                print("Manual Power Mode: %s" % payload[4])
                print("Sparge Water Alert Displayed: %s" % payload[5])
            if data[0] == 'T':
                print("Timer Active: %s" % payload[0])
                print("Time Left (Minutes): %s" % payload[1])
                print("Timer Total Start Time: %s" % payload[2])
                print("Time Left (Seconds): %s" % payload[3])
            if data[0] == 'C':
                print("Boil Temperature: %s" % payload[0])
            if data[0] == 'I':
                print("Interaction Code: %s" % payload[0])
        else:
            print("handleNotification handle 0x%04X unknown" % (cHandle))



notifOn = b"\x01\x00"
notifOff = b"\x00\x00"
gf_ble_mac = "BB:A0:50:03:31:19"
GATTUUID = "0000cdd0-0000-1000-8000-00805f9b34fb"
WRITEUUID = "0003cdd2-0000-1000-8000-00805f9b0131"
NOTIFYUUID = "0003cdd1-0000-1000-8000-00805f9b0131"

print("Connecting to BLE device MAC: " + gf_ble_mac)

per = btle.Peripheral(gf_ble_mac)
services = per.getServices()
services[2].getCharacteristics(WRITEUUID)
gfService = per.getServiceByUUID(GATTUUID)
writechar = gfService.getCharacteristics(WRITEUUID)[0]
writehandle = gfService.getCharacteristics(WRITEUUID)[0].getHandle()
notifychar = gfService.getCharacteristics(NOTIFYUUID)[0]
notifyhandle = gfService.getCharacteristics(NOTIFYUUID)[0].getHandle()
per.withDelegate(MyDelegate(notifyhandle))

print("Enabling notifications...")
char = per.getCharacteristics(uuid=NOTIFYUUID)[0]
ccc_desc = char.getDescriptors(forUUID=0x2902)[0]
ccc_desc.write(notifOn, withResponse=True)
print("\tDone")
per.waitForNotifications(0.5)

sec = 0
while True:
    if per.waitForNotifications(0.5):
        # print("Notification received")
        continue
    print("Waiting for notifications...")
    sec += 1
    if sec >= 5:
        break

per.disconnect()
