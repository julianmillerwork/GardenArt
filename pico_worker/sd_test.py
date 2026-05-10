import os
from machine import Pin, SPI
import sdcard

spi = SPI(
    0,
    baudrate=8_000_000,
    polarity=0,
    phase=0,
    sck=Pin(18),
    mosi=Pin(19),
    miso=Pin(16),
)

cs = Pin(17, Pin.OUT)

sd = sdcard.SDCard(spi, cs)
os.mount(sd, "/sd")

print(os.listdir("/sd"))


import os
import time

filename = "/sd/test_file.txt"

# -----------------------------
# Write file
# -----------------------------
with open(filename, "w") as f:
    f.write("Hello from Raspberry Pi Pico!\n")
    f.write("This file was written to the SD card.\n")
    f.write("Ticks: {}\n".format(time.ticks_ms()))

print("File written:", filename)

# -----------------------------
# List SD card contents
# -----------------------------
print("SD contents:")
print(os.listdir("/sd"))

# -----------------------------
# Read file back
# -----------------------------
with open(filename, "r") as f:
    contents = f.read()

print("File contents:")
print(contents)

# -----------------------------
# Optional: append to file
# -----------------------------
with open(filename, "a") as f:
    f.write("Appended line at ticks: {}\n".format(time.ticks_ms()))

print("File appended")

# -----------------------------
# Read back again
# -----------------------------
with open(filename, "r") as f:
    contents = f.read()

print("Updated file contents:")
print(contents)