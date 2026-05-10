import math
import struct

NUM_LEDS = 300
TOTAL_FRAMES = 600
FPS = 30
OUTPUT = "aurora_300x600_grb32.dltl"

# Delta settings
KEYFRAME_INTERVAL = 20
DELTA_MAX_CHANGES_RATIO = 0.85

# Block / compression settings
BLOCK_FRAMES = 20
LZ_WINDOW = 4096
MIN_MATCH = 3
MAX_MATCH = 10
HASH_SIZE = 4096          # must be power of 2
MAX_CANDIDATES = 6        # how many prior candidates to try per position


def hash3(data, pos):
    return ((data[pos] * 257) ^ (data[pos + 1] * 17) ^ data[pos + 2]) & (HASH_SIZE - 1)


def ltl_compress_block(raw_block):
    """
    Tiny LZ-style compressor with fast hash-based match finding.

    Output tokens:
      Literal:
        0LLLLLLL
        then (L+1) literal bytes

      Match:
        1LLLOOOO
        [offset_lo]
        length = ((token >> 4) & 0x07) + 3
        offset = (((token & 0x0F) << 8) | offset_lo) + 1
    """
    data = raw_block
    n = len(data)
    out = bytearray()
    literals = bytearray()

    # For each hash bucket, store the most recent position.
    # prev[pos] links to the previous position with same hash.
    head = [-1] * HASH_SIZE
    prev = [-1] * n

    def flush_literals():
        nonlocal literals
        lit_len = len(literals)
        idx = 0
        while idx < lit_len:
            chunk = min(128, lit_len - idx)
            out.append(chunk - 1)
            out.extend(literals[idx:idx + chunk])
            idx += chunk
        literals = bytearray()

    def add_position(pos):
        if pos + MIN_MATCH > n:
            return
        h = hash3(data, pos)
        prev[pos] = head[h]
        head[h] = pos

    pos = 0
    while pos < n:
        best_len = 0
        best_off = 0

        # Only try to match if enough bytes remain
        if pos + MIN_MATCH <= n:
            h = hash3(data, pos)
            cand = head[h]
            tried = 0

            while cand != -1 and tried < MAX_CANDIDATES:
                off = pos - cand

                if off > LZ_WINDOW:
                    break

                # Quick reject
                if data[cand] == data[pos] and data[cand + 1] == data[pos + 1] and data[cand + 2] == data[pos + 2]:
                    match_len = 3
                    max_len = min(MAX_MATCH, n - pos)

                    while match_len < max_len and data[cand + match_len] == data[pos + match_len]:
                        match_len += 1

                    if match_len > best_len:
                        best_len = match_len
                        best_off = off
                        if best_len == MAX_MATCH:
                            break

                cand = prev[cand]
                tried += 1

        if best_len >= MIN_MATCH:
            if literals:
                flush_literals()

            token = 0x80 | ((best_len - 3) << 4) | (((best_off - 1) >> 8) & 0x0F)
            out.append(token)
            out.append((best_off - 1) & 0xFF)

            # Add covered positions to the hash chains so future matches can reference them
            end = pos + best_len
            while pos < end:
                add_position(pos)
                pos += 1
        else:
            literals.append(data[pos])
            add_position(pos)
            pos += 1

            if len(literals) >= 128:
                flush_literals()

    if literals:
        flush_literals()

    return bytes(out)

def clamp8(v):
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(v)


def wrap_dist(a, b):
    """
    Circular distance on a 0..1 loop.
    """
    d = abs(a - b)
    if d > 0.5:
        d = 1.0 - d
    return d


def smooth_pulse(loop_u, centre_u, half_width_u):
    """
    Loop-safe pulse envelope.
    loop_u       : current phase 0..1
    centre_u     : pulse centre 0..1
    half_width_u : half-width of pulse in loop units

    Returns 0..1
    """
    d = wrap_dist(loop_u, centre_u)
    if d >= half_width_u:
        return 0.0

    x = 1.0 - (d / half_width_u)
    return x * x * (3.0 - 2.0 * x)


def spatial_burst_profile(p, centre_p, half_width_p):
    """
    Spatial burst envelope across the strip.
    p            : LED position 0..1
    centre_p     : burst centre 0..1
    half_width_p : burst half-width 0..1
    """
    d = abs(p - centre_p)
    if d >= half_width_p:
        return 0.0

    x = 1.0 - (d / half_width_p)
    return x * x * x


def aurora_background(i, theta):
    """
    Loop-safe aurora background.
    """
    p = i / NUM_LEDS
    x = 2.0 * math.pi * p

    wave1 = 0.5 + 0.5 * math.sin(2.2 * x + 1.0 * theta)
    wave2 = 0.5 + 0.5 * math.sin(4.9 * x - 2.0 * theta + 1.3)
    wave3 = 0.5 + 0.5 * math.sin(1.3 * x + 5.0 * theta + 2.1)

    glow = wave1 * 0.42 + wave2 * 0.34 + wave3 * 0.24
    glow = glow ** 1.8

    curtain1 = 0.5 + 0.5 * math.sin(12.0 * x + 3.0 * theta + 0.8)
    curtain2 = 0.5 + 0.5 * math.sin(8.0 * x - 5.0 * theta + 2.4)
    curtain = (curtain1 ** 5) * 0.65 + (curtain2 ** 4) * 0.35
    curtain *= glow

    drift_g = 0.5 + 0.5 * math.sin(1.0 * theta + 0.2)
    drift_b = 0.5 + 0.5 * math.sin(2.0 * theta + 2.0)
    drift_p = 0.5 + 0.5 * math.sin(3.0 * theta + 4.0)

    scene = 0.5 + 0.5 * math.sin(theta - 0.4)

    base_g = 55 + 18 * scene
    base_b = 28 + 14 * scene
    base_r = 4 + 2 * scene

    g = base_g + glow * (145 + 95 * drift_g) + curtain * 70
    b = base_b + glow * (85 + 135 * drift_b) + curtain * 95
    r = base_r + glow * (14 + 50 * drift_p) + curtain * 22

    return r, g, b, glow


# -------------------------------------------------
# Discrete flash burst events
# -------------------------------------------------
BURSTS = [
    {"centre_u": 0.06, "half_u": 0.020, "centre_p": 0.18, "half_p": 0.070, "strength": 1.00, "pinkness": 2.00, "blue_boost": 0.80},
    {"centre_u": 0.12, "half_u": 0.030, "centre_p": 0.72, "half_p": 0.090, "strength": 0.85, "pinkness": 1.90, "blue_boost": 1.00},
    {"centre_u": 0.21, "half_u": 0.018, "centre_p": 0.40, "half_p": 0.060, "strength": 1.15, "pinkness": 2.10, "blue_boost": 0.75},
    {"centre_u": 0.29, "half_u": 0.025, "centre_p": 0.82, "half_p": 0.075, "strength": 0.95, "pinkness": 2.00, "blue_boost": 0.95},
    {"centre_u": 0.36, "half_u": 0.022, "centre_p": 0.10, "half_p": 0.065, "strength": 1.10, "pinkness": 2.20, "blue_boost": 0.70},
    {"centre_u": 0.44, "half_u": 0.028, "centre_p": 0.56, "half_p": 0.085, "strength": 0.90, "pinkness": 1.95, "blue_boost": 1.05},
    {"centre_u": 0.53, "half_u": 0.020, "centre_p": 0.30, "half_p": 0.060, "strength": 1.20, "pinkness": 2.15, "blue_boost": 0.85},
    {"centre_u": 0.61, "half_u": 0.032, "centre_p": 0.88, "half_p": 0.095, "strength": 0.85, "pinkness": 1.85, "blue_boost": 1.10},
    {"centre_u": 0.69, "half_u": 0.019, "centre_p": 0.47, "half_p": 0.055, "strength": 1.25, "pinkness": 2.25, "blue_boost": 0.75},
    {"centre_u": 0.77, "half_u": 0.026, "centre_p": 0.20, "half_p": 0.080, "strength": 0.90, "pinkness": 2.00, "blue_boost": 0.95},
    {"centre_u": 0.86, "half_u": 0.021, "centre_p": 0.66, "half_p": 0.065, "strength": 1.10, "pinkness": 2.05, "blue_boost": 0.90},
    {"centre_u": 0.94, "half_u": 0.024, "centre_p": 0.93, "half_p": 0.075, "strength": 1.00, "pinkness": 2.10, "blue_boost": 0.80},
]


def add_discrete_bursts(p, loop_u, glow):
    """
    Returns additional (r, g, b) from explicit burst events.
    """
    add_r = 0.0
    add_g = 0.0
    add_b = 0.0

    glow_bias = 0.55 + 0.45 * glow

    for burst in BURSTS:
        t_env = smooth_pulse(loop_u, burst["centre_u"], burst["half_u"])
        if t_env <= 0.0:
            continue

        s_env = spatial_burst_profile(p, burst["centre_p"], burst["half_p"])
        if s_env <= 0.0:
            continue

        env = t_env * s_env * glow_bias * burst["strength"]

        add_r += env * 190.0 * burst["pinkness"]
        add_g += env * 42.0
        add_b += env * 145.0 * burst["blue_boost"]

        core = env * env
        add_r += core * 70.0 * burst["pinkness"]
        add_g += core * 10.0
        add_b += core * 55.0 * burst["blue_boost"]

    return add_r, add_g, add_b


def build_frame(frame_index):
    loop_u = frame_index / TOTAL_FRAMES
    theta = 2.0 * math.pi * loop_u

    frame = []
    for i in range(NUM_LEDS):
        p = i / NUM_LEDS

        r, g, b, glow = aurora_background(i, theta)
        br, bg, bb = add_discrete_bursts(p, loop_u, glow)

        r += br
        g += bg
        b += bb

        r = clamp8(r)
        g = clamp8(g)
        b = clamp8(b)

        frame.append((r, g, b, 0))

    return frame


def encode_keyframe(frame):
    out = bytearray()
    out.append(0x00)
    for r, g, b, w in frame:
        out.extend((r, g, b, w))
    return bytes(out)


def encode_delta(prev_frame, frame):
    changes = []

    for i, (old_px, new_px) in enumerate(zip(prev_frame, frame)):
        if old_px != new_px:
            changes.append((i, new_px))

    out = bytearray()
    out.append(0x01)
    out.extend(struct.pack("<H", len(changes)))

    for index, (r, g, b, w) in changes:
        out.extend(struct.pack("<H", index))
        out.extend((r, g, b, w))

    return bytes(out), len(changes)


def lz_find_match(data, pos):
    """
    Find best backward match in previous window.

    Token format target:
      Literal token:
        0LLLLLLL
        length = 1..128

      Match token:
        1LLLOOOO  [offset_lo]
        length = 3..10
        offset = 1..4096
    """
    start = max(0, pos - LZ_WINDOW)
    best_len = 0
    best_off = 0

    max_len = min(MAX_MATCH, len(data) - pos)
    if max_len < MIN_MATCH:
        return 0, 0

    # Naive search. Fine for moderate block sizes and offline generation.
    for cand in range(start, pos):
        if data[cand] != data[pos]:
            continue

        match_len = 1
        while (
            match_len < max_len
            and data[cand + match_len] == data[pos + match_len]
        ):
            match_len += 1

        if match_len >= MIN_MATCH and match_len > best_len:
            best_len = match_len
            best_off = pos - cand

            if best_len == max_len:
                break

    return best_len, best_off


def write_header(f, block_count):
    """
    DLTL header:
      4 bytes magic      b"DLTL"
      2 bytes version
      2 bytes leds
      2 bytes total_frames
      2 bytes fps
      2 bytes block_frames
      2 bytes block_count

    Followed by block_count index entries:
      4 bytes offset
      4 bytes comp_size
      4 bytes uncomp_size
      2 bytes first_frame
      2 bytes frame_count
    """
    f.write(b"DLTL")
    f.write(struct.pack(
        "<HHHHHH",
        1,
        NUM_LEDS,
        TOTAL_FRAMES,
        FPS,
        BLOCK_FRAMES,
        block_count,
    ))


def flush_block(blocks, first_frame_index, frame_count, raw_block):
    if frame_count == 0:
        return

    uncomp = bytes(raw_block)
    comp = ltl_compress_block(uncomp)

    blocks.append({
        "first_frame": first_frame_index,
        "frame_count": frame_count,
        "uncomp_size": len(uncomp),
        "comp_size": len(comp),
        "payload": comp,
    })


# -------------------------------------------------
# Build compressed blocks
# -------------------------------------------------
blocks = []

prev_frame = None
block_prev_frame = None
block_raw = bytearray()
block_first_frame_index = 0
block_frame_count = 0

keyframes = 0
delta_frames = 0
total_changes = 0

for frame_index in range(TOTAL_FRAMES):
    if block_frame_count == 0:
        block_first_frame_index = frame_index
        block_prev_frame = None

    frame = build_frame(frame_index)

    force_keyframe = (
        prev_frame is None or
        block_prev_frame is None or
        (frame_index % KEYFRAME_INTERVAL == 0)
    )

    if force_keyframe:
        block_raw.extend(encode_keyframe(frame))
        keyframes += 1
    else:
        changes = sum(1 for a, b in zip(block_prev_frame, frame) if a != b)

        if changes > int(NUM_LEDS * DELTA_MAX_CHANGES_RATIO):
            block_raw.extend(encode_keyframe(frame))
            keyframes += 1
        else:
            record, count = encode_delta(block_prev_frame, frame)
            block_raw.extend(record)
            delta_frames += 1
            total_changes += count

    prev_frame = frame
    block_prev_frame = frame
    block_frame_count += 1

    if block_frame_count >= BLOCK_FRAMES:
        flush_block(blocks, block_first_frame_index, block_frame_count, block_raw)
        block_raw = bytearray()
        block_frame_count = 0
        block_prev_frame = None

flush_block(blocks, block_first_frame_index, block_frame_count, block_raw)

# -------------------------------------------------
# Write final container
# -------------------------------------------------
with open(OUTPUT, "wb") as f:
    write_header(f, len(blocks))

    index_start = f.tell()
    index_entry_size = 16
    f.write(b"\x00" * (len(blocks) * index_entry_size))

    index = []
    for block in blocks:
        offset = f.tell()
        f.write(block["payload"])
        index.append((
            offset,
            block["comp_size"],
            block["uncomp_size"],
            block["first_frame"],
            block["frame_count"],
        ))

    f.seek(index_start)
    for offset, comp_size, uncomp_size, first_frame, frame_count in index:
        f.write(struct.pack(
            "<IIIHH",
            offset,
            comp_size,
            uncomp_size,
            first_frame,
            frame_count,
        ))

raw_estimate = sum(block["uncomp_size"] for block in blocks)
compressed_size = sum(block["comp_size"] for block in blocks)
container_overhead = 4 + 12 + len(blocks) * 16
final_size = compressed_size + container_overhead

print("Wrote", OUTPUT)
print("Frames:", TOTAL_FRAMES)
print("LEDs:", NUM_LEDS)
print("FPS:", FPS)
print("Block frames:", BLOCK_FRAMES)
print("Blocks:", len(blocks))
print("Keyframes:", keyframes)
print("Delta frames:", delta_frames)
if delta_frames:
    print("Avg changed LEDs per delta frame:", total_changes / delta_frames)
print("Raw delta-stream bytes:", raw_estimate)
print("Compressed payload bytes:", compressed_size)
print("Container overhead bytes:", container_overhead)
print("Final file bytes:", final_size)
if raw_estimate:
    print("Compression ratio:", final_size / raw_estimate)
    print("Space saving:", 100.0 * (1.0 - final_size / raw_estimate), "%")