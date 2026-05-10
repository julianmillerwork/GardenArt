import math
import struct

NUM_LEDS = 188
TOTAL_FRAMES = 600
FPS = 30
OUTPUT = "rainbow_rgbw_70x600_188.dlt"

# Delta tuning
KEYFRAME_INTERVAL = 30
DELTA_MAX_CHANGES_RATIO = 0.8


# =========================================================
# Helpers
# =========================================================

def clamp8(v):
    if v < 0: return 0
    if v > 255: return 255
    return int(v)


def hsv_to_rgb(h, s, v):
    """
    h: 0..1
    s: 0..1
    v: 0..1
    """
    h = h % 1.0
    i = int(h * 6)
    f = (h * 6) - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)

    i = i % 6

    if i == 0: r, g, b = v, t, p
    elif i == 1: r, g, b = q, v, p
    elif i == 2: r, g, b = p, v, t
    elif i == 3: r, g, b = p, q, v
    elif i == 4: r, g, b = t, p, v
    elif i == 5: r, g, b = v, p, q

    return r, g, b


# =========================================================
# Frame builder
# =========================================================

def build_frame(frame_index):
    frame = []

    # Smooth looping phase
    loop_u = frame_index / TOTAL_FRAMES

    for i in range(NUM_LEDS):
        p = i / NUM_LEDS

        # Moving rainbow
        hue = (p + loop_u) % 1.0

        r, g, b = hsv_to_rgb(hue, 1.0, 1.0)

        # Scale RGB slightly down to make room for white
        r *= 0.85
        g *= 0.85
        b *= 0.85

        # White shimmer layer
        shimmer = 0.5 + 0.5 * math.sin(2 * math.pi * (p * 3 + loop_u * 4))
        w = shimmer ** 3   # sharper peaks

        # Balance white vs colour
        w *= 0.6

        # Convert to 0–255
        r = clamp8(r * 255)
        g = clamp8(g * 255)
        b = clamp8(b * 255)
        w = clamp8(w * 255)

        frame.append((r, g, b, w))

    return frame


# =========================================================
# DLT writing
# =========================================================

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


# =========================================================
# Main
# =========================================================

with open(OUTPUT, "wb") as f:
    write_header(f)

    prev_frame = None
    keyframes = 0
    delta_frames = 0
    total_changes = 0

    for frame_index in range(TOTAL_FRAMES):
        frame = build_frame(frame_index)

        force_keyframe = (
            prev_frame is None or
            (frame_index % KEYFRAME_INTERVAL == 0)
        )

        if force_keyframe:
            write_keyframe(f, frame)
            keyframes += 1
        else:
            changes = sum(1 for a, b in zip(prev_frame, frame) if a != b)

            if changes > int(NUM_LEDS * DELTA_MAX_CHANGES_RATIO):
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
print("Keyframes:", keyframes)
print("Delta frames:", delta_frames)
if delta_frames:
    print("Avg changed LEDs per delta frame:", total_changes / delta_frames)