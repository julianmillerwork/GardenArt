from time import sleep, ticks_ms
import math
from pi_pico_neopixel.pi_pico_neopixel import Neopixel


# =========================
# Configuration
# =========================
NUM_LEDS = 160
STATE_MACHINE = 0
PIN = 0
BRIGHTNESS = 180   # brighter overall, 0-255

pixels = Neopixel(NUM_LEDS, STATE_MACHINE, PIN, "GRB", transfer_mode="PUT")
pixels.brightness(BRIGHTNESS)


# =========================
# Helpers
# =========================
def clamp(v, lo=0, hi=255):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return int(v)

def smoothstep(x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return x * x * (3 - 2 * x)

def aurora_colour(x, t):
    p = x / NUM_LEDS

    # Main broad curtain layers
    wave1 = 0.5 + 0.5 * math.sin((p * 2.1 * math.pi) + (t * 0.42))
    wave2 = 0.5 + 0.5 * math.sin((p * 4.7 * math.pi) - (t * 0.28) + 1.3)
    wave3 = 0.5 + 0.5 * math.sin((p * 1.2 * math.pi) + (t * 0.18) + 2.7)

    base_glow = (wave1 * 0.45) + (wave2 * 0.35) + (wave3 * 0.20)
    base_glow = base_glow ** 1.8

    # Slow colour drift
    drift_g = 0.5 + 0.5 * math.sin(t * 0.16 + 0.4)
    drift_b = 0.5 + 0.5 * math.sin(t * 0.11 + 2.1)
    drift_p = 0.5 + 0.5 * math.sin(t * 0.13 + 4.3)

    # Shimmering curtain layer:
    # narrow, brighter moving highlights that appear only in some regions
    curtain_wave = 0.5 + 0.5 * math.sin((p * 14.0 * math.pi) + (t * 1.8))
    curtain_mask = 0.5 + 0.5 * math.sin((p * 2.6 * math.pi) - (t * 0.33) + 0.8)
    curtain_mask = smoothstep(curtain_mask)
    curtain = (curtain_wave ** 6) * curtain_mask

    # Fine shimmer / sparkle texture in the bright zones
    shimmer1 = 0.5 + 0.5 * math.sin((p * 34.0 * math.pi) - (t * 3.8) + 0.7)
    shimmer2 = 0.5 + 0.5 * math.sin((p * 21.0 * math.pi) + (t * 2.7) + 1.9)
    shimmer = (shimmer1 * shimmer2) ** 8
    shimmer *= smoothstep(base_glow)

    # Combine everything
    glow = base_glow + curtain * 0.9 + shimmer * 0.5
    glow = min(glow, 1.0)

    # Brighter palette:
    # vivid green/cyan with blue and purple highlights
    green = glow * (140 + 100 * drift_g)
    blue  = glow * (70 + 130 * drift_b)
    red   = glow * (20 + 90 * drift_p * (0.35 + curtain * 0.65))

    # Push curtain highlights toward icy cyan / violet
    green += curtain * 60
    blue  += curtain * 90
    red   += curtain * 25

    # Slight shaping
    r = clamp(red * 0.72)
    g = clamp(green)
    b = clamp(blue * 0.95)

    return (r, g, b)


# =========================
# Main loop
# =========================
while True:
    t = ticks_ms() / 1000.0

    for i in range(NUM_LEDS):
        pixels.set_pixel(i, aurora_colour(i, t))

    pixels.show()
    sleep(0.025)   # about 40 FPS