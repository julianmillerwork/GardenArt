import math
import struct

NUM_LEDS = 300
TOTAL_FRAMES = 200
OUTPUT = "warm_3000k_architectural_600x200_grb32.bin"


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def warm_light_pixel(i, theta):
    """
    Very subtle architectural warm-white animation.
    theta runs 0 .. 2*pi across the full loop.
    """

    p = i / NUM_LEDS
    x = 2.0 * math.pi * p

    # Extremely slow whole-scene breathing
    scene = 0.5 + 0.5 * math.sin(theta)

    # Very broad spatial shaping
    spatial1 = 0.5 + 0.5 * math.sin(0.45 * x + 0.8 * theta + 0.7)
    spatial2 = 0.5 + 0.5 * math.sin(1.1 * x - 0.6 * theta + 1.9)
    spatial = (spatial1 * 0.75 + spatial2 * 0.25)

    # Tiny warmth drift
    warmth = 0.5 + 0.5 * math.sin(1.4 * theta + 0.9)

    # Very small brightness movement
    intensity = 0.955 + 0.018 * scene + 0.010 * spatial

    # 3000K-style RGB mix, near maximum brightness
    r = 255 * intensity
    g = (160 + 10 * warmth) * intensity
    b = (40 - 6 * warmth) * intensity

    return clamp8(r), clamp8(g), clamp8(b)


with open(OUTPUT, "wb") as f:
    for frame in range(TOTAL_FRAMES):
        u = frame / TOTAL_FRAMES
        theta = 2.0 * math.pi * u

        for i in range(NUM_LEDS):
            r, g, b = warm_light_pixel(i, theta)

            # Packed GRB32 for Pico playback
            word = (g << 16) | (r << 8) | b
            f.write(struct.pack("<I", word))

print("Wrote", OUTPUT)