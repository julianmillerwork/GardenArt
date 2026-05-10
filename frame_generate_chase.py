import math
import struct

NUM_LEDS = 188
TOTAL_FRAMES = 300
FPS = 30
OUTPUT = "blue_purple_chase_188.dlt"

KEYFRAME_INTERVAL = 20


def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def chase_pixel(i, theta):
    p = i / NUM_LEDS
    x = 2.0 * math.pi * p

    wave1 = 0.5 + 0.5 * math.sin(8.0 * x - 4.0 * theta)
    wave2 = 0.5 + 0.5 * math.sin(5.0 * x - 2.0 * theta + 1.3)
    wave3 = 0.5 + 0.5 * math.sin(13.0 * x - 6.0 * theta + 2.4)

    base = 0.20 + 0.35 * wave2
    chase = wave1 ** 4
    sparkle = wave3 ** 10
    colour_drift = 0.5 + 0.5 * math.sin(theta + 0.8)

    r = 20 + 40 * base + 90 * chase + 70 * sparkle + 30 * colour_drift
    g = 5 + 10 * base + 15 * chase + 10 * sparkle
    b = 45 + 90 * base + 150 * chase + 110 * sparkle + 30 * (1.0 - colour_drift)

    offset = (0.5 + 0.5 * math.sin(7.0 * x + 3.0 * theta + 0.7)) ** 3
    r += 40 * offset
    b += 55 * offset

    w = 0

    return clamp8(r), clamp8(g), clamp8(b), clamp8(w)


def build_frame(frame_index):
    """
    Build a single frame.

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
        frame.append(chase_pixel(i, theta))

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