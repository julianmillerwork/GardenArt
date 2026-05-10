# play_dlt.py
#
# Standalone DLT animation player for Pico / MicroPython.
#
# Usage:
#
#   import play_dlt
#   play_dlt.play("aurora_70_grb32_188.dlt")
#
# The player will look for the file:
#   1. exactly as passed
#   2. under /sd
#
# So this works for both:
#   play_dlt.play("my_file.dlt")       # checks local flash, then /sd
#   play_dlt.play("/sd/my_file.dlt")   # checks exact path
#   play_dlt.play("/my_file.dlt")      # checks exact path

import array
import gc
import os

from machine import Pin, SPI
from time import ticks_ms, ticks_diff, sleep_ms

import sdcard
import ws281xx_control
import anim_players


# =========================================================
# Configuration
# =========================================================

PIXEL_ORDER = "WRGB"

PIN_NUM = 3
STATE_MACHINE = 4
RGBW_MODE = True

NUM_LEDS = 188

SD_MOUNT = "/sd"

SPI_ID = 0
SPI_BAUDRATE = 8_000_000

SD_SCK_PIN = 18
SD_MOSI_PIN = 19
SD_MISO_PIN = 16
SD_CS_PIN = 17

DEFAULT_BRIGHTNESS = 255

# Edit this if you want the file to auto-play when running this module.
DLT_FILE = "blue_purple_pink_white_full_brightness_5min_rgbw_188.dlt"


# =========================================================
# LED strip setup
# =========================================================

strip = ws281xx_control.FastWS281x(
    PIN_NUM,
    NUM_LEDS,
    rgbw=RGBW_MODE,
    sm_id=STATE_MACHINE,
    freq=8_000_000,
)


# =========================================================
# Filesystem helpers
# =========================================================

_sd_mounted = False


def file_exists(filename):
    try:
        os.stat(filename)
        return True
    except OSError:
        return False


def mount_sd():
    """
    Mount the SD card at SD_MOUNT.

    Safe to call multiple times.
    If no SD card is present, this raises an exception.
    """
    global _sd_mounted

    if _sd_mounted:
        return True

    try:
        os.listdir(SD_MOUNT)
        _sd_mounted = True
        print("SD already mounted:", SD_MOUNT)
        return True
    except OSError:
        pass

    spi = SPI(
        SPI_ID,
        baudrate=SPI_BAUDRATE,
        polarity=0,
        phase=0,
        sck=Pin(SD_SCK_PIN),
        mosi=Pin(SD_MOSI_PIN),
        miso=Pin(SD_MISO_PIN),
    )

    cs = Pin(SD_CS_PIN, Pin.OUT)

    sd = sdcard.SDCard(spi, cs)
    os.mount(sd, SD_MOUNT)

    _sd_mounted = True

    print("Mounted SD at", SD_MOUNT)

    try:
        print("SD files:", os.listdir(SD_MOUNT))
    except Exception as e:
        print("Could not list SD:", repr(e))

    return True


def try_mount_sd():
    """
    Try to mount SD, but do not fail playback if SD is unavailable.

    This allows files on normal Pico flash to play even when no SD card
    is inserted or mounted.
    """
    try:
        return mount_sd()
    except Exception as e:
        print("SD mount failed:", repr(e))
        return False


def resolve_file(filename):
    """
    Resolve an animation filename.

    Search order:
      1. Exact filename/path as passed
      2. /sd/<filename>, but only for relative filenames

    Examples:
      "anim.dlt"       -> checks "anim.dlt", then "/sd/anim.dlt"
      "/anim.dlt"      -> checks "/anim.dlt" only
      "/sd/anim.dlt"   -> checks "/sd/anim.dlt" only
    """
    if file_exists(filename):
        return filename

    # Absolute paths should not be rewritten.
    if filename.startswith("/"):
        return None

    # Try SD card as fallback.
    try_mount_sd()

    sd_filename = SD_MOUNT + "/" + filename

    if file_exists(sd_filename):
        return sd_filename

    return None


# =========================================================
# Brightness
# =========================================================

def apply_brightness_to_buf(src_buf, dst_buf, brightness):
    """
    Applies brightness to packed 32-bit pixel buffer.

    Assumes packed word format:
        W in bits 24-31
        R in bits 16-23
        G in bits 8-15
        B in bits 0-7
    """
    if brightness >= 255:
        return src_buf

    if brightness <= 0:
        for i in range(len(src_buf)):
            dst_buf[i] = 0
        return dst_buf

    for i, px in enumerate(src_buf):
        w = (px >> 24) & 0xFF
        r = (px >> 16) & 0xFF
        g = (px >> 8) & 0xFF
        b = px & 0xFF

        w = (w * brightness) >> 8
        r = (r * brightness) >> 8
        g = (g * brightness) >> 8
        b = (b * brightness) >> 8

        dst_buf[i] = (w << 24) | (r << 16) | (g << 8) | b

    return dst_buf


# =========================================================
# DLT player
# =========================================================

def make_dlt_player(filename):
    """
    Open and return a DeltaPlayer for the given .dlt file.
    """
    with open(filename, "rb") as probe:
        magic = probe.read(4)

    if magic != b"DLTA":
        raise ValueError("Not a DLT file: {}".format(filename))

    player = anim_players.DeltaPlayer(filename, NUM_LEDS, PIXEL_ORDER)
    player.open()

    print("Opened DLT animation:", filename)
    print("PIXEL_ORDER:", PIXEL_ORDER)
    print("NUM_LEDS:", NUM_LEDS)
    print("Frame time ms:", player.frame_ms)

    return player


def play(filename, brightness=DEFAULT_BRIGHTNESS):
    """
    Play a DLT file forever.

    The file is searched for on:
      1. normal filesystem / flash
      2. SD card under /sd
    """
    resolved = resolve_file(filename)

    if resolved is None:
        raise OSError(
            "Animation file not found on flash or SD: {}".format(filename)
        )

    print("Using animation file:", resolved)

    frame_buf = array.array("I", [0] * NUM_LEDS)
    output_buf = array.array("I", [0] * NUM_LEDS)

    led = Pin("LED", Pin.OUT)
    led.on()

    player = None

    try:
        player = make_dlt_player(resolved)

        print("Starting playback")
        print("Brightness:", brightness)

        stats_start = ticks_ms()
        stats_frames = 0
        stats_total_frame_ms = 0
        stats_worst_frame_ms = 0

        while True:
            frame_start = ticks_ms()

            player.next_frame_into(frame_buf, PIXEL_ORDER)

            display_buf = apply_brightness_to_buf(
                frame_buf,
                output_buf,
                brightness,
            )

            strip.show_buf(display_buf)

            elapsed = ticks_diff(ticks_ms(), frame_start)

            stats_frames += 1
            stats_total_frame_ms += elapsed

            if elapsed > stats_worst_frame_ms:
                stats_worst_frame_ms = elapsed

            target_frame_ms = player.frame_ms
            remaining = target_frame_ms - elapsed

            if remaining > 0:
                sleep_ms(remaining)

            now = ticks_ms()
            stats_elapsed_ms = ticks_diff(now, stats_start)

            if stats_elapsed_ms >= 3000:
                achieved_fps = (stats_frames * 1000.0) / stats_elapsed_ms
                avg_frame_ms = (
                    stats_total_frame_ms / stats_frames
                    if stats_frames
                    else 0
                )

                print(
                    "FPS {:.2f} | avg frame {:.2f} ms | worst frame {} ms | target {} ms".format(
                        achieved_fps,
                        avg_frame_ms,
                        stats_worst_frame_ms,
                        target_frame_ms,
                    )
                )

                stats_start = now
                stats_frames = 0
                stats_total_frame_ms = 0
                stats_worst_frame_ms = 0

    finally:
        if player is not None:
            try:
                player.close()
            except Exception as e:
                print("Player close error:", repr(e))

        gc.collect()


def stop_leds():
    """
    Explicitly blank the LEDs.
    Useful when testing from the REPL.
    """
    off_buf = array.array("I", [0] * NUM_LEDS)
    strip.show_buf(off_buf)


# =========================================================
# Auto-start when run directly
# =========================================================

play(DLT_FILE, DEFAULT_BRIGHTNESS)