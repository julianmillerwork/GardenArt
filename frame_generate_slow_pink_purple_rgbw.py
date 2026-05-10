import math
import struct

NUM_LEDS = 188

# 5 minute loop at 1 FPS, with the final frame identical to the first.
# There are 300 intervals plus the closing duplicate frame.
TOTAL_FRAMES = 301
FPS = 1

OUTPUT = "blue_purple_pink_white_full_brightness_5min_rgbw_188.dlt"

KEYFRAME_INTERVAL = 20


# =========================================================
# Tuning
# =========================================================

# Keep at 1.0 for full brightness.
MASTER_BRIGHTNESS = 1.0


# =========================================================
# Helpers
# =========================================================

def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def smoothstep(t):
    """
    Smooth interpolation curve.

    t should be 0..1.
    Returns 0..1 with soft start and soft end.
    """
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_colour(c1, c2, t):
    """
    Interpolate RGBW tuples.
    """
    t = smoothstep(t)

    return (
        lerp(c1[0], c2[0], t),
        lerp(c1[1], c2[1], t),
        lerp(c1[2], c2[2], t),
        lerp(c1[3], c2[3], t),
    )


# =========================================================
# Colour palette
# =========================================================
#
# Format is RGBW.
#
# Your delta writer writes bytes in this order:
#     r, g, b, w
#
# Your player can then map this according to PIXEL_ORDER="WRGB".
#

BLUE = (
    0,
    0,
    255,
    0,
)

PURPLE = (
    160,
    0,
    255,
    0,
)

PINK = (
    255,
    0,
    120,
    0,
)

# Full white using the W channel.
# RGB is intentionally zero here so the white phase is produced by W.
WHITE = (
    0,
    0,
    0,
    255,
)

# The last colour is BLUE again, making the cycle close cleanly.
PALETTE = [
    BLUE,
    PURPLE,
    PINK,
    WHITE,
    BLUE,
]


def base_colour(theta):
    """
    Return the global RGBW colour for the current point in the cycle.

    theta moves from 0 to 2*pi over the whole animation.
    """
    u = theta / (2.0 * math.pi)

    # Safety for tiny floating point edge cases.
    if u < 0.0:
        u = 0.0
    if u > 1.0:
        u = 1.0

    segment_count = len(PALETTE) - 1

    x = u * segment_count
    segment = int(x)

    if segment >= segment_count:
        segment = segment_count - 1
        local_t = 1.0
    else:
        local_t = x - segment

    return lerp_colour(PALETTE[segment], PALETTE[segment + 1], local_t)


def pixel_colour(i, theta):
    """
    Build one pixel colour.

    Full brightness version:
    - no shimmer
    - no spatial dimming
    - every LED receives the same full-intensity colour for each frame
    """
    r, g, b, w = base_colour(theta)

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


# =========================================================
# Delta file writer
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
# Generate file
# =========================================================

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
print("Duration seconds:", (TOTAL_FRAMES - 1) / FPS)
print("Playback frames including closing frame:", TOTAL_FRAMES)
print("Keyframes:", keyframes)
print("Delta frames:", delta_frames)

if delta_frames:
    print("Avg changed LEDs per delta frame:", total_changes / delta_frames)

if first_frame == last_frame:
    print("Loop check: first and last frames are identical")
else:
    print("Loop check: WARNING first and last frames differ")