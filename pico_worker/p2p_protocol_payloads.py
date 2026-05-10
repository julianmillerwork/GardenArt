from p2p_protocol_spec import *


def _u32be(value):
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError("u32 out of range")
    return bytes([
        (value >> 24) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    ])


def _read_u32be(payload, offset=0):
    return (
        (payload[offset] << 24) |
        (payload[offset + 1] << 16) |
        (payload[offset + 2] << 8) |
        payload[offset + 3]
    ) & 0xFFFFFFFF


def pack_ack(error_code=ERR_NONE):
    return bytes([error_code])


def pack_nack(error_code):
    return bytes([error_code])


def pack_set_mode(mode):
    return bytes([mode])


def pack_set_brightness(brightness):
    return bytes([brightness & 0xFF])


def pack_set_pixel(index, r, g, b, w=0):
    if index < 0 or index > 0xFFFF:
        raise ValueError("index out of range")
    return bytes([
        (index >> 8) & 0xFF,
        index & 0xFF,
        r & 0xFF,
        g & 0xFF,
        b & 0xFF,
        w & 0xFF,
    ])


def unpack_set_pixel(payload):
    return {
        "index": (payload[0] << 8) | payload[1],
        "r": payload[2],
        "g": payload[3],
        "b": payload[4],
        "w": payload[5],
    }


def pack_fill(r, g, b, w=0):
    return bytes([r & 0xFF, g & 0xFF, b & 0xFF, w & 0xFF])


def unpack_fill(payload):
    return {
        "r": payload[0],
        "g": payload[1],
        "b": payload[2],
        "w": payload[3],
    }


def pack_play(anim_id, loop, fps):
    # anim_id is a 32-bit content-derived ID.
    return _u32be(anim_id) + bytes([loop & 0xFF, fps & 0xFF])


def unpack_play(payload):
    return {
        "anim_id": _read_u32be(payload, 0),
        "loop": payload[4],
        "fps": payload[5],
    }


def pack_status(state, mode, brightness, error):
    return bytes([state, mode, brightness, error])


def unpack_status(payload):
    return {
        "state": payload[0],
        "mode": payload[1],
        "brightness": payload[2],
        "error": payload[3],
    }


# =========================================================
# UART file-transfer payloads
# =========================================================
def pack_begin_transfer(transfer_id, transfer_type, total_size):
    if total_size < 0 or total_size > 0xFFFFFFFF:
        raise ValueError("total_size out of range")

    # transfer_id_u32_be + transfer_type_u8 + total_size_u32_be
    return _u32be(transfer_id) + bytes([transfer_type & 0xFF]) + _u32be(total_size)


def unpack_begin_transfer(payload):
    return {
        "transfer_id": _read_u32be(payload, 0),
        "transfer_type": payload[4],
        "total_size": _read_u32be(payload, 5),
    }


def pack_data_chunk(transfer_id, chunk_index, data):
    # Packet LEN is one byte. DATA_CHUNK has 6 bytes of header, so max data is 249.
    if len(data) > 249:
        raise ValueError("data too large for DATA_CHUNK")
    if chunk_index < 0 or chunk_index > 0xFFFF:
        raise ValueError("chunk_index out of range")

    return _u32be(transfer_id) + bytes([
        (chunk_index >> 8) & 0xFF,
        chunk_index & 0xFF,
    ]) + data


def unpack_data_chunk(payload):
    return {
        "transfer_id": _read_u32be(payload, 0),
        "chunk_index": (payload[4] << 8) | payload[5],
        "data": payload[6:],
    }


def pack_end_transfer(transfer_id, crc32):
    return _u32be(transfer_id) + _u32be(crc32)


def unpack_end_transfer(payload):
    return {
        "transfer_id": _read_u32be(payload, 0),
        "crc32": _read_u32be(payload, 4),
    }


def pack_transfer_status(transfer_id, status, chunk_index):
    return _u32be(transfer_id) + bytes([
        status & 0xFF,
        (chunk_index >> 8) & 0xFF,
        chunk_index & 0xFF,
    ])


def unpack_transfer_status(payload):
    return {
        "transfer_id": _read_u32be(payload, 0),
        "status": payload[4],
        "chunk_index": (payload[5] << 8) | payload[6],
    }
