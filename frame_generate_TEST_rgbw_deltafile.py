import struct

NUM_LEDS = 188
TOTAL_FRAMES = 1
FPS = 30
OUTPUT = "test_white.dlt"

# Delta settings
KEYFRAME_INTERVAL = 60
DELTA_MAX_CHANGES_RATIO = 0.85


def build_frame(frame_index):
    """
    Static alternating pattern:
    LED 0 = Red
    LED 1 = Green
    LED 2 = Blue
    LED 3 = White
    then repeat.
    """
    colours = [
        (255, 255, 255, 255),       # R
        (255, 255, 255, 255),       # G
        (255, 255, 255, 255),       # B
        (255, 255, 255, 255),       # W
    ]

    frame = []
    for i in range(NUM_LEDS):
        frame.append(colours[i % 4])

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