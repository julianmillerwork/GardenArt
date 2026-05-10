import math
import struct

NUM_LEDS = 300
TOTAL_FRAMES = 600
OUTPUT = "aurora_600x600_grb32.bin"


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def aurora_pixel(i, theta):
    """
    theta goes from 0 .. 2*pi over the full animation loop.
    This makes the whole animation naturally periodic.
    """
    p = i / NUM_LEDS
    x = 2.0 * math.pi * p

    # Broad moving field components
    wave1 = 0.5 + 0.5 * math.sin(2.2 * x + 1.0 * theta)
    wave2 = 0.5 + 0.5 * math.sin(4.9 * x - 2.0 * theta + 1.3)
    wave3 = 0.5 + 0.5 * math.sin(1.3 * x + 3.0 * theta + 2.1)

    glow = wave1 * 0.42 + wave2 * 0.34 + wave3 * 0.24
    glow = glow ** 1.8

    # Brighter curtain detail, also periodic
    curtain1 = 0.5 + 0.5 * math.sin(12.0 * x + 4.0 * theta + 0.8)
    curtain2 = 0.5 + 0.5 * math.sin(8.0 * x - 3.0 * theta + 2.4)
    curtain = (curtain1 ** 5) * 0.65 + (curtain2 ** 4) * 0.35
    curtain *= glow

    # Slow colour drift, fully loop-safe
    drift_g = 0.5 + 0.5 * math.sin(1.0 * theta + 0.2)
    drift_b = 0.5 + 0.5 * math.sin(2.0 * theta + 2.0)
    drift_p = 0.5 + 0.5 * math.sin(3.0 * theta + 4.0)

    # Whole-scene breathing, also loop-safe
    scene = 0.5 + 0.5 * math.sin(theta - 0.4)

    # Brightness floor to avoid dim tail sections
    base_g = 55 + 18 * scene
    base_b = 28 + 14 * scene
    base_r = 4 + 2 * scene

    g = base_g + glow * (145 + 95 * drift_g) + curtain * 70
    b = base_b + glow * (85 + 135 * drift_b) + curtain * 95
    r = base_r + glow * (14 + 50 * drift_p) + curtain * 22

    return clamp8(r), clamp8(g), clamp8(b)


with open(OUTPUT, "wb") as f:
    for frame in range(TOTAL_FRAMES):
        # Use endpoint=False behaviour manually:
        # frame runs 0 .. TOTAL_FRAMES-1
        # theta runs 0 .. just under 2*pi
        u = frame / TOTAL_FRAMES
        theta = 2.0 * math.pi * u

        for i in range(NUM_LEDS):
            r, g, b = aurora_pixel(i, theta)

            # Packed GRB for Pico playback
            word = (g << 16) | (r << 8) | b
            f.write(struct.pack("<I", word))

print("Wrote", OUTPUT)