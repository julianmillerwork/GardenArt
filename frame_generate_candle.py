import math
import struct

NUM_LEDS = 300
TOTAL_FRAMES = 240          # 20 s at 12 FPS
OUTPUT = "candle_flicker_600x240_grb32.bin"


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def candle_pixel(i, theta):
    """
    Gentle candle-like flicker.
    theta runs 0 .. 2*pi over the full loop.
    """
    p = i / NUM_LEDS
    x = 2.0 * math.pi * p

    # Slow global breathing
    breath = 0.5 + 0.5 * math.sin(theta)

    # Broad warm variation along the strip
    spatial1 = 0.5 + 0.5 * math.sin(0.9 * x + 1.2 * theta + 0.3)
    spatial2 = 0.5 + 0.5 * math.sin(2.3 * x - 2.0 * theta + 1.4)
    spatial = spatial1 * 0.7 + spatial2 * 0.3

    # Soft flicker layers, still loop-safe
    flicker1 = 0.5 + 0.5 * math.sin(5.0 * theta + 3.0 * x + 0.7)
    flicker2 = 0.5 + 0.5 * math.sin(8.0 * theta - 5.0 * x + 2.1)
    flicker3 = 0.5 + 0.5 * math.sin(13.0 * theta + 1.5 * x + 1.6)

    # Keep movement subtle and warm
    flicker = flicker1 * 0.45 + flicker2 * 0.35 + flicker3 * 0.20

    # Main brightness stays high, flicker only nudges it
    intensity = 0.72 + 0.10 * breath + 0.08 * spatial + 0.10 * flicker

    # Warmth drift: more amber at times, more yellow at others
    warmth = 0.5 + 0.5 * math.sin(2.0 * theta + 0.9)

    # Deep orange / yellow candle palette
    r = 255 * intensity
    g = (115 + 55 * warmth) * intensity
    b = (8 + 10 * (1.0 - warmth)) * intensity

    return clamp8(r), clamp8(g), clamp8(b)


with open(OUTPUT, "wb") as f:
    for frame in range(TOTAL_FRAMES):
        u = frame / TOTAL_FRAMES
        theta = 2.0 * math.pi * u

        for i in range(NUM_LEDS):
            r, g, b = candle_pixel(i, theta)
            word = (g << 16) | (r << 8) | b
            f.write(struct.pack("<I", word))

print("Wrote", OUTPUT)