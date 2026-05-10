import array
import struct
import rp2
from machine import Pin
from time import ticks_ms, ticks_diff, sleep_ms

import ws281xx_control
import anim_players

PIXEL_ORDER = "WRGB"


# =========================================================
# Configuration
# =========================================================
NUM_LEDS = 70
PIN_NUM = 0
STATE_MACHINE = 0
RGBW_MODE = True

#ANIM_FILE = "alternate_purple_yellow_fade_out_and_back_70x300_140.dlt"
NUM_LEDS = 188
ANIM_FILE = "aurora_70_grb32_188.dlt"

FPS = 30
FRAME_MS = 1000 // FPS
FRAME_WORDS = NUM_LEDS

strip = ws281xx_control.FastWS281x(
    PIN_NUM,
    NUM_LEDS,
    rgbw=RGBW_MODE,
    sm_id=STATE_MACHINE,
    freq=8_000_000
)


# =========================================================
# Player selection
# =========================================================
def make_player(filename, num_leds, default_frame_ms):
    with open(filename, "rb") as probe:
        magic = probe.read(4)

    if magic == b"DLTA":
        player = anim_players.DeltaPlayer(filename, num_leds,PIXEL_ORDER)
        player.open()
        print("Detected DLT animation")
        print("DLT uses PIXEL_ORDER =", PIXEL_ORDER)
        print("DLT LED count =", num_leds)
        print("DLT frame time (ms):", player.frame_ms)
        return player

    player = RawBinPlayer(filename, num_leds, default_frame_ms,PIXEL_ORDER)
    player.open()
    print("Detected raw BIN animation")
    print("BIN is assumed pre-packed for", num_leds, "RGBW pixels")
    print("BIN frame time (ms):", default_frame_ms)
    return player


# =========================================================
# Playback loop
# =========================================================
def play_loop(PIXEL_ORDER):
    frame_buf = array.array("I", [0] * FRAME_WORDS)
    player = make_player(ANIM_FILE, NUM_LEDS, FRAME_MS)

    stats_interval_ms = 3000
    stats_start = ticks_ms()
    stats_frames = 0
    stats_total_frame_ms = 0
    stats_worst_frame_ms = 0

    try:
        while True:
            frame_start = ticks_ms()

            player.next_frame_into(frame_buf,PIXEL_ORDER)
            strip.show_buf(frame_buf)

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

            if stats_elapsed_ms >= stats_interval_ms:
                achieved_fps = (stats_frames * 1000.0) / stats_elapsed_ms
                avg_frame_ms = stats_total_frame_ms / stats_frames if stats_frames else 0

                print(
                    "FPS {:.2f} | avg frame {:.2f} ms | worst frame {} ms | target {} ms".format(
                        achieved_fps,
                        avg_frame_ms,
                        stats_worst_frame_ms,
                        target_frame_ms
                    )
                )

                stats_start = now
                stats_frames = 0
                stats_total_frame_ms = 0
                stats_worst_frame_ms = 0

    finally:
        player.close()


play_loop(PIXEL_ORDER)