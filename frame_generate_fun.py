import math
import struct

NUM_LEDS = 300
TOTAL_FRAMES = 600
OUTPUT = "pink_orange_blocks_600x600_grb32.bin"


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def smoothstep(x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return x * x * (3.0 - 2.0 * x)


def soft_block_wave(phase, blocks, softness=0.22):
    u = (phase * blocks) % 1.0
    centre_dist = abs(u - 0.5) * 2.0

    x = 1.0 - centre_dist
    edge0 = 0.5 - softness
    edge1 = 0.5 + softness

    if x <= edge0:
        return 0.0
    if x >= edge1:
        return 1.0
    return smoothstep((x - edge0) / (edge1 - edge0))


def block_pattern(i, theta):
    p = i / NUM_LEDS

    # Motion
    SPEED_SCALE = 0.6

    travel1 = (p - theta / (2.0 * math.pi) * 3.2 * SPEED_SCALE) % 1.0
    travel2 = (p + theta / (2.0 * math.pi) * 2.0 * SPEED_SCALE + 0.17) % 1.0
    travel3 = (p - theta / (2.0 * math.pi) * 5.0 * SPEED_SCALE + 0.41) % 1.0
    
    block1 = soft_block_wave(travel1, 8, softness=0.18)
    block2 = soft_block_wave(travel2, 5, softness=0.28)
    accent = soft_block_wave(travel3, 14, softness=0.12)

    pulse1 = 0.5 + 0.5 * math.sin(3.0 * theta)
    pulse2 = 0.5 + 0.5 * math.sin(5.0 * theta + 1.4)

    colour_mix = 0.5 + 0.5 * math.sin((2.0 * math.pi * p * 6.0) - 2.0 * theta)

    # -------------------------------------------------
    # 🎨 NEW COLOUR TUNING
    # -------------------------------------------------

    # Pink (magenta leaning)
    pink_r = 180 * block1 + 120 * block2 + 90 * accent
    pink_g = 20  * block1 + 10  * block2
    pink_b = 140 * block1 + 80  * block2 + 60 * accent

    # Yellow → orange (warmer, richer)
    yellow_r = 220 * block2 + 150 * accent + 120 * block1
    yellow_g = 160 * block2 + 110 * accent + 80 * block1
    yellow_b = 8   * block2 + 5   * accent  # almost no blue

    pink_weight = (1.0 - colour_mix) * (0.75 + 0.25 * pulse1)
    yellow_weight = colour_mix * (0.75 + 0.25 * pulse2)

    r = 10 + pink_r * pink_weight + yellow_r * yellow_weight
    g = 2  + pink_g * pink_weight + yellow_g * yellow_weight
    b = 10 + pink_b * pink_weight + yellow_b * yellow_weight

    # Soft underglow
    under = 0.5 + 0.5 * math.sin((2.0 * math.pi * p * 2.0) + theta)
    r += 30 * under
    g += 10 * under * yellow_weight
    b += 25 * under

    # Edge shimmer
    shimmer = (0.5 + 0.5 * math.sin((2.0 * math.pi * p * 18.0) - 7.0 * theta)) ** 6
    edge_energy = 0.35 * block1 + 0.25 * block2 + 0.40 * accent

    r += 80 * shimmer * edge_energy
    g += 35 * shimmer * yellow_weight * edge_energy
    b += 65 * shimmer * edge_energy

    return clamp8(r), clamp8(g), clamp8(b)


with open(OUTPUT, "wb") as f:
    for frame in range(TOTAL_FRAMES):
        u = frame / TOTAL_FRAMES
        theta = 2.0 * math.pi * u

        for i in range(NUM_LEDS):
            r, g, b = block_pattern(i, theta)
            word = (g << 16) | (r << 8) | b
            f.write(struct.pack("<I", word))

print("Wrote", OUTPUT)