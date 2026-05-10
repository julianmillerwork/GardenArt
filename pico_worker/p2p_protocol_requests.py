from p2p_protocol_spec import *
from p2p_protocol_codec import build_packet
from p2p_protocol_payloads import *

def req_ping(seq, data=b""):
    return build_packet(CMD_PING, seq, data)

def req_get_status(seq):
    return build_packet(CMD_GET_STATUS, seq, b"")

def req_set_mode(seq, mode):
    return build_packet(CMD_SET_MODE, seq, pack_set_mode(mode))

def req_set_brightness(seq, brightness):
    return build_packet(CMD_SET_BRIGHTNESS, seq, pack_set_brightness(brightness))

def req_set_pixel(seq, index, r, g, b, w=0):
    return build_packet(CMD_SET_PIXEL, seq, pack_set_pixel(index, r, g, b, w))

def req_fill(seq, r, g, b, w=0):
    return build_packet(CMD_FILL, seq, pack_fill(r, g, b, w))

def req_show(seq):
    return build_packet(CMD_SHOW, seq, b"")

def req_clear(seq):
    return build_packet(CMD_CLEAR, seq, b"")

def req_play(seq, anim_id, loop=1, fps=30):
    return build_packet(CMD_PLAY, seq, pack_play(anim_id, loop, fps))

def req_stop(seq):
    return build_packet(CMD_STOP, seq, b"")

def req_begin_transfer(seq, transfer_id, transfer_type, total_size):
    return build_packet(
        CMD_BEGIN_TRANSFER,
        seq,
        pack_begin_transfer(transfer_id, transfer_type, total_size)
    )

def req_data_chunk(seq, transfer_id, chunk_index, data):
    return build_packet(
        CMD_DATA_CHUNK,
        seq,
        pack_data_chunk(transfer_id, chunk_index, data)
    )

def req_end_transfer(seq, transfer_id, expected_crc):
    return build_packet(
        CMD_END_TRANSFER,
        seq,
        pack_end_transfer(transfer_id, expected_crc)
    )