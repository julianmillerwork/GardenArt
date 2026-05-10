import math
import struct

NUM_LEDS = 188
TOTAL_FRAMES = 600          # 20 s at 30 FPS
FPS = 30
OUTPUT = "candle_188_yellow_dancing_subtle_centres.dlt"

NUM_CANDLES = 14
KEYFRAME_INTERVAL = 20


# =========================================================
# Tuning
# =========================================================

MASTER_BRIGHTNESS = 1.0

# Yellow/amber tint.
RGB_TINT_AMOUNT = 0.72

# Strong visible flicker.
FLICKER_DEPTH = 0.58
SHIMMER_DEPTH = 0.16

# Warm ambient floor.
AMBIENT_W = 2.0
AMBIENT_R = 3.5
AMBIENT_G = 1.8
AMBIENT_B = 0.0

# Dancing movement, but with more anchored centres.
POSITION_WOBBLE_AMOUNT = 0.0045
FLAME_LEAN_AMOUNT = 0.0040
WIDTH_BREATH_AMOUNT = 0.42


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def candle_shape(p, centre, half_width):
    d = abs(p - centre)

    if d >= half_width:
        return 0.0

    x = 1.0 - (d / half_width)

    # Concentrated candle falloff with soft edges.
    return x * x * x


def candle_flicker(theta, idx):
    """
    Visible, loop-safe candle flicker.

    All frequencies are integers, so values return cleanly to their starting
    point when theta reaches 2*pi.
    """

    # Slow rolling body movement.
    f1 = 0.5 + 0.5 * math.sin(3.0 * theta + idx * 0.91 + 0.3)
    f2 = 0.5 + 0.5 * math.sin(5.0 * theta - idx * 1.37 + 1.2)

    # Medium uneven movement.
    f3 = 0.5 + 0.5 * math.sin(9.0 * theta + idx * 0.63 + 2.4)

    # Quicker shimmer.
    f4 = 0.5 + 0.5 * math.sin(17.0 * theta - idx * 0.48 + 0.8)

    # Occasional soft dip. Squaring makes the dip rarer and less sinusoidal.
    dip = 0.5 + 0.5 * math.sin(7.0 * theta + idx * 2.11 + 1.7)
    dip = dip * dip

    # Occasional soft flare.
    flare = 0.5 + 0.5 * math.sin(11.0 * theta - idx * 1.73 + 0.4)
    flare = flare * flare * flare

    body = 0.42 * f1 + 0.30 * f2 + 0.20 * f3 + 0.08 * f4

    # Main flicker range.
    flicker = 1.0 - FLICKER_DEPTH + FLICKER_DEPTH * body

    # Dips make it feel more flame-like rather than a smooth sine wave.
    flicker -= 0.16 * dip

    # Flares add occasional liveliness.
    flicker += 0.12 * flare

    # Small shimmer.
    flicker += SHIMMER_DEPTH * (f4 - 0.5)

    # Keep within a candle-like range.
    if flicker < 0.45:
        flicker = 0.45
    if flicker > 1.18:
        flicker = 1.18

    return flicker


def candle_warmth(theta, idx):
    """
    Slow, loop-safe warmth drift.
    """
    w1 = 0.5 + 0.5 * math.sin(1.0 * theta + idx * 0.77 + 0.5)
    w2 = 0.5 + 0.5 * math.sin(3.0 * theta - idx * 0.22 + 1.1)

    return 0.75 * w1 + 0.25 * w2


def candle_position_wobble(theta, idx):
    """
    Visible but restrained loop-safe positional movement.
    This moves the whole candle body slightly.
    """
    wobble = math.sin(2.0 * theta + idx * 0.71)
    wobble += 0.65 * math.sin(5.0 * theta - idx * 0.37 + 1.4)
    wobble += 0.35 * math.sin(9.0 * theta + idx * 1.21 + 2.0)

    return wobble * POSITION_WOBBLE_AMOUNT


def candle_lean(theta, idx):
    """
    Small independent shift of the brighter candle core.

    Kept deliberately subtle so the bright centres do not travel too far.
    """
    lean = math.sin(3.0 * theta + idx * 1.41 + 0.5)
    lean += 0.38 * math.sin(8.0 * theta - idx * 0.83 + 1.9)
    lean += 0.16 * math.sin(13.0 * theta + idx * 0.51 + 0.2)

    return lean * FLAME_LEAN_AMOUNT


def candle_width_breath(theta, idx):
    """
    Strong loop-safe width breathing.

    This keeps the candle feeling alive even though the centres are more
    anchored.
    """
    breath = 0.5 + 0.5 * math.sin(4.0 * theta + idx * 1.19 + 0.6)
    shimmer = 0.5 + 0.5 * math.sin(10.0 * theta - idx * 0.52 + 1.7)

    return 1.0 - (WIDTH_BREATH_AMOUNT * 0.5) + WIDTH_BREATH_AMOUNT * (
        0.72 * breath + 0.28 * shimmer
    )


def pixel_colour(i, theta):
    p = i / NUM_LEDS

    # Warm/yellow ambient floor.
    r = AMBIENT_R
    g = AMBIENT_G
    b = AMBIENT_B
    w = AMBIENT_W

    for c in range(NUM_CANDLES):
        base_centre = (c + 0.5) / NUM_CANDLES

        centre = base_centre + candle_position_wobble(theta, c)
        flame_centre = centre + candle_lean(theta, c)

        base_half_width = 0.019 + 0.007 * (
            0.5 + 0.5 * math.sin(c * 1.13 + 0.7)
        )

        half_width = base_half_width * candle_width_breath(theta, c)

        outer = candle_shape(p, centre, half_width)

        if outer <= 0.0:
            continue

        flick = candle_flicker(theta, c)
        warmth = candle_warmth(theta, c)

        # W gives the body, RGB pushes it yellow/amber.
        w_body = 44 + 92 * flick

        # Strong yellow/amber mix.
        amber_r = 175 + 52 * warmth
        amber_g = 92 + 58 * warmth
        amber_b = 2 + 4 * (1.0 - warmth)

        r += outer * flick * amber_r * RGB_TINT_AMOUNT
        g += outer * flick * amber_g * RGB_TINT_AMOUNT
        b += outer * flick * amber_b * RGB_TINT_AMOUNT
        w += outer * w_body

        # Bright centre, shifted only slightly from the base.
        core_width = half_width * 0.36
        core = candle_shape(p, flame_centre, core_width)

        if core > 0.0:
            core_pulse = 0.78 + 0.48 * flick

            # Yellow-white core.
            r += core * (82 + 62 * warmth) * RGB_TINT_AMOUNT * core_pulse
            g += core * (52 + 48 * warmth) * RGB_TINT_AMOUNT * core_pulse
            b += core * 2.0 * RGB_TINT_AMOUNT
            w += core * (46 + 78 * core_pulse)

        # Very narrow hot/yellow centre.
        hot_width = half_width * 0.15
        hot = candle_shape(p, flame_centre, hot_width)

        if hot > 0.0:
            hot_pulse = 0.75 + 0.55 * flick

            r += hot * 48 * RGB_TINT_AMOUNT * hot_pulse
            g += hot * 34 * RGB_TINT_AMOUNT * hot_pulse
            b += hot * 1.0
            w += hot * (26 + 56 * hot_pulse)

        # Small asymmetric glow trailing opposite the lean.
        # Reduced because the centre movement has been restrained.
        trail_centre = centre - candle_lean(theta, c) * 0.45
        trail_width = half_width * 0.48
        trail = candle_shape(p, trail_centre, trail_width)

        if trail > 0.0:
            trail_strength = 0.35 + 0.35 * flick

            r += trail * 54 * RGB_TINT_AMOUNT * trail_strength
            g += trail * 28 * RGB_TINT_AMOUNT * trail_strength
            b += trail * 0.5
            w += trail * 16 * trail_strength

    r *= MASTER_BRIGHTNESS
    g *= MASTER_BRIGHTNESS
    b *= MASTER_BRIGHTNESS
    w *= MASTER_BRIGHTNESS

    return clamp8(r), clamp8(g), clamp8(b), clamp8(w)


def build_frame(frame_index):
    """
    Build a single frame.

    Important:
    Using TOTAL_FRAMES - 1 means:
        frame 0              -> theta = 0
        frame TOTAL_FRAMES-1 -> theta = 2*pi

    Therefore the first and last frames are identical.
    """
    if TOTAL_FRAMES <= 1:
        u = 0.0
    else:
        u = frame_index / (TOTAL_FRAMES - 1)

    theta = 2.0 * math.pi * u

    frame = []

    for i in range(NUM_LEDS):
        frame.append(pixel_colour(i, theta))

    return frame


def write_header(f):
    f.write(b"DLTA")
    f.write(struct.pack("<H", 1))
    f.write(struct.pack("<H", NUM_LEDS))
    f.write(struct.pack("<H", TOTAL_FRAMES))
    f.write(struct.pack("<H", FPS))


def write_keyframe(f, frame):
    f.write(b"\x00")

    for r, g, b, w in frame:
        f.write(bytes((r, g, b, w)))


def write_delta(f, prev_frame, frame):
    changes = []

    for i, (old_px, new_px) in enumerate(zip(prev_frame, frame)):
        if old_px != new_px:
            changes.append((i, new_px))

    f.write(b"\x01")
    f.write(struct.pack("<H", len(changes)))

    for index, (r, g, b, w) in changes:
        f.write(struct.pack("<H", index))
        f.write(bytes((r, g, b, w)))

    return len(changes)


with open(OUTPUT, "wb") as f:
    write_header(f)

    prev_frame = None
    keyframes = 0
    delta_frames = 0
    total_changes = 0

    first_frame = None
    last_frame = None

    for frame_index in range(TOTAL_FRAMES):
        frame = build_frame(frame_index)

        if frame_index == 0:
            first_frame = frame

        if frame_index == TOTAL_FRAMES - 1:
            last_frame = frame

        force_keyframe = (
            prev_frame is None or
            (frame_index % KEYFRAME_INTERVAL == 0)
        )

        if force_keyframe:
            write_keyframe(f, frame)
            keyframes += 1
        else:
            changes = sum(1 for a, b in zip(prev_frame, frame) if a != b)

            keyframe_size = 1 + (NUM_LEDS * 4)
            delta_size = 1 + 2 + (changes * 6)

            if delta_size >= keyframe_size:
                write_keyframe(f, frame)
                keyframes += 1
            else:
                write_delta(f, prev_frame, frame)
                delta_frames += 1
                total_changes += changes

        prev_frame = frame

print("Wrote", OUTPUT)
print("Frames:", TOTAL_FRAMES)
print("LEDs:", NUM_LEDS)
print("FPS:", FPS)
print("Duration seconds:", TOTAL_FRAMES / FPS)
print("Keyframes:", keyframes)
print("Delta frames:", delta_frames)

if delta_frames:
    print("Avg changed LEDs per delta frame:", total_changes / delta_frames)

if first_frame == last_frame:
    print("Loop check: first and last frames are identical")
else:
    print("Loop check: WARNING first and last frames differ")