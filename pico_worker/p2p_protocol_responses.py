# p2p_protocol_responses.py
from p2p_protocol_spec import *
from p2p_protocol_codec import build_packet
from p2p_protocol_payloads import *

def rsp_ack(seq):
    return build_packet(CMD_ACK, seq, pack_ack(ERR_NONE))

def rsp_nack(seq, error_code):
    return build_packet(CMD_NACK, seq, pack_nack(error_code))

def rsp_pong(seq, data=b""):
    return build_packet(CMD_PONG, seq, data)

def rsp_status(seq, state, mode, brightness, error):
    return build_packet(CMD_STATUS, seq, pack_status(state, mode, brightness, error))

def rsp_transfer_status(seq, transfer_id, status, chunk_index):
    return build_packet(
        CMD_TRANSFER_STATUS,
        seq,
        pack_transfer_status(transfer_id, status, chunk_index)
    )

def rsp_error(seq, error_code, context_cmd=None):
    if context_cmd is None:
        payload = bytes([error_code])
    else:
        payload = bytes([error_code, context_cmd])
    return build_packet(CMD_ERROR, seq, payload)