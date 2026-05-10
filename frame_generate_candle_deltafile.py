import math
import struct

NUM_LEDS = 188
TOTAL_FRAMES = 600          # 20 s at 30 FPS
FPS = 30
OUTPUT = "candle_188.dlt"

NUM_CANDLES = 14
KEYFRAME_INTERVAL = 20


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

    # Soft but concentrated candle falloff.
    return x * x * x


def candle_flicker(theta, idx):
    """
    Slower, gentler, loop-safe candle flicker.

    All frequencies are integers, so the values return cleanly to the
    starting point when theta reaches 2*pi.
    """
    f1 = 0.5 + 0.5 * math.sin(4.0 * theta + idx * 0.91 + 0.3)
    f2 = 0.5 + 0.5 * math.sin(7.0 * theta - idx * 1.37 + 1.2)
    f3 = 0.5 + 0.5 * math.sin(10.0 * theta + idx * 0.63 + 2.4)

    # Small gentle shimmer, still loop-safe.
    shimmer = 0.5 + 0.5 * math.sin(15.0 * theta - idx * 0.48 + 0.8)

    base = 0.46 * f1 + 0.34 * f2 + 0.20 * f3

    # Compress the range so the candles do not jump too hard.
    flicker = 0.82 + 0.18 * base

    # Tiny shimmer only.
    flicker += 0.035 * (shimmer - 0.5)

    return flicker


def candle_warmth(theta, idx):
    """
    Slow, loop-safe colour-temperature drift.
    """
    w1 = 0.5 + 0.5 * math.sin(1.0 * theta + idx * 0.77 + 0.5)
    w2 = 0.5 + 0.5 * math.sin(3.0 * theta - idx * 0.22 + 1.1)

    return 0.80 * w1 + 0.20 * w2


def candle_position_wobble(theta, idx):
    """
    Very subtle loop-safe positional movement.

    This is intentionally tiny. It prevents the candles from looking totally
    static, without causing visible jumps.
    """
    wobble = math.sin(2.0 * theta + idx * 0.71)
    wobble += 0.45 * math.sin(5.0 * theta - idx * 0.37 + 1.4)

    return wobble * 0.0018


def pixel_colour(i, theta):
    p = i / NUM_LEDS

    # Gentle warm ambient base.
    r = 5.0
    g = 2.5
    b = 0.4
    w = 0.0

    for c in range(NUM_CANDLES):
        base_centre = (c + 0.5) / NUM_CANDLES
        centre = base_centre + candle_position_wobble(theta, c)

        half_width = 0.018 + 0.006 * (
            0.5 + 0.5 * math.sin(c * 1.13 + 0.7)
        )

        shape = candle_shape(p, centre, half_width)

        if shape <= 0.0:
            continue

        flick = candle_flicker(theta, c)
        warmth = candle_warmth(theta, c)

        # Gentler intensity range.
        intensity = 0.55 + 0.50 * flick

        # Warm yellow/orange candle body.
        cr = 190 + 38 * intensity
        cg = 76 + 58 * warmth
        cb = 3 + 5 * (1.0 - warmth)

        r += shape * intensity * cr
        g += shape * intensity * cg
        b += shape * intensity * cb

        # Soft use of W channel for the warm glowing core.
        w += shape * intensity * (10 + 20 * warmth)

        # Yellow-white centre of each candle.
        core_width = half_width * 0.30
        core = candle_shape(p, centre, core_width)

        if core > 0.0:
            r += core * (30 + 16 * flick)
            g += core * (22 + 14 * warmth)
            b += core * 3
            w += core * (18 + 22 * flick)

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