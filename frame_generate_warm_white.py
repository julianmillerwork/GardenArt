import math
import struct

NUM_LEDS = 300
TOTAL_FRAMES = 200
OUTPUT = "warm_3000k_subtle_600x200_grb32.bin"


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def warm_light_pixel(i, theta):
    """
    Very subtle warm-white animation.
    theta runs 0 .. 2*pi across the full loop.
    """

    p = i / NUM_LEDS
    x = 2.0 * math.pi * p

    # Very slow whole-scene brightness breathing
    scene_breath = 0.5 + 0.5 * math.sin(theta)

    # Gentle strip-wide unevenness so it doesn't feel flat
    spatial1 = 0.5 + 0.5 * math.sin(0.8 * x + 1.0 * theta + 0.4)
    spatial2 = 0.5 + 0.5 * math.sin(2.1 * x - 2.0 * theta + 1.3)
    spatial = (spatial1 * 0.7 + spatial2 * 0.3)

    # Tiny shimmer like warm incandescent / candle filament movement
    shimmer1 = 0.5 + 0.5 * math.sin(3.7 * theta + 3.0 * x + 0.9)
    shimmer2 = 0.5 + 0.5 * math.sin(5.1 * theta - 5.0 * x + 2.2)
    shimmer = (shimmer1 * 0.6 + shimmer2 * 0.4)

    # Overall intensity kept high, with only subtle movement
    intensity = 0.90 + 0.06 * scene_breath + 0.03 * spatial + 0.01 * shimmer

    # Tiny warmth drift:
    # slightly more amber at some points in the cycle,
    # slightly cleaner warm white at others
    warmth = 0.5 + 0.5 * math.sin(2.0 * theta + 1.1)

    # Base 3000K-ish warm white at high brightness
    # Tuned for RGB LEDs, not physically exact CCT
    r = 255 * intensity
    g = (168 + 18 * warmth) * intensity
    b = (58 - 10 * warmth) * intensity

    return clamp8(r), clamp8(g), clamp8(b)


with open(OUTPUT, "wb") as f:
    for frame in range(TOTAL_FRAMES):
        u = frame / TOTAL_FRAMES
        theta = 2.0 * math.pi * u

        for i in range(NUM_LEDS):
            r, g, b = warm_light_pixel(i, theta)

            # Packed GRB32 for your Pico playback code
            word = (g << 16) | (r << 8) | b
            f.write(struct.pack("<I", word))

print("Wrote", OUTPUT)