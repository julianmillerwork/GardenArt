import math
import struct

NUM_LEDS = 300
TOTAL_FRAMES = 600
OUTPUT = "aurora_600x600_grb32.bin"

# Number of frames at the end that will blend back into the start
LOOP_BLEND_FRAMES = 80


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def lerp(a, b, t):
    return a * (1.0 - t) + b * t


def smoothstep(x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return x * x * (3.0 - 2.0 * x)


def aurora_pixel(i, t):
    p = i / NUM_LEDS

    wave1 = 0.5 + 0.5 * math.sin((p * 2.2 * math.pi) + t * 0.7)
    wave2 = 0.5 + 0.5 * math.sin((p * 5.1 * math.pi) - t * 0.4 + 1.2)
    wave3 = 0.5 + 0.5 * math.sin((p * 1.4 * math.pi) + t * 0.25 + 2.6)

    glow = wave1 * 0.45 + wave2 * 0.35 + wave3 * 0.20
    glow = glow ** 1.8

    curtain = 0.5 + 0.5 * math.sin((p * 13.0 * math.pi) + t * 1.8)
    curtain = curtain ** 6
    curtain *= glow

    drift_g = 0.5 + 0.5 * math.sin(t * 0.30)
    drift_b = 0.5 + 0.5 * math.sin(t * 0.23 + 2.1)
    drift_p = 0.5 + 0.5 * math.sin(t * 0.27 + 4.2)

    # Brightness floor so it never gets too dim
    base_g = 50
    base_b = 28
    base_r = 4

    g = base_g + glow * (150 + 85 * drift_g) + curtain * 60
    b = base_b + glow * (80 + 135 * drift_b) + curtain * 90
    r = base_r + glow * (14 + 55 * drift_p) + curtain * 20

    return clamp8(r), clamp8(g), clamp8(b)


# ---------------------------------------------------------
# First generate all frames in memory on desktop
# ---------------------------------------------------------
frames = []

for frame in range(TOTAL_FRAMES):
    t = frame / 18.0

    frame_data = []
    for i in range(NUM_LEDS):
        frame_data.append(aurora_pixel(i, t))
    frames.append(frame_data)

# ---------------------------------------------------------
# Blend end of animation into start
# ---------------------------------------------------------
if LOOP_BLEND_FRAMES > 0:
    start_blend = TOTAL_FRAMES - LOOP_BLEND_FRAMES

    for f in range(start_blend, TOTAL_FRAMES):
        # 0 at start of blend region, 1 at very end
        x = (f - start_blend) / (LOOP_BLEND_FRAMES - 1)
        x = smoothstep(x)

        # Blend current end frame toward corresponding start frame
        target_frame = f - start_blend

        blended = []
        for i in range(NUM_LEDS):
            r1, g1, b1 = frames[f][i]
            r2, g2, b2 = frames[target_frame][i]

            r = clamp8(round(lerp(r1, r2, x)))
            g = clamp8(round(lerp(g1, g2, x)))
            b = clamp8(round(lerp(b1, b2, x)))

            blended.append((r, g, b))

        frames[f] = blended

# ---------------------------------------------------------
# Write packed GRB32 file
# ---------------------------------------------------------
with open(OUTPUT, "wb") as f:
    for frame_data in frames:
        for r, g, b in frame_data:
            word = (g << 16) | (r << 8) | b
            f.write(struct.pack("<I", word))

print("Wrote", OUTPUT)