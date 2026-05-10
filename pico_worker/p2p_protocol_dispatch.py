from p2p_protocol_spec import *
from p2p_protocol_payloads import *
from p2p_protocol_responses import *


class ProtocolContext:
    def __init__(self, device, transfer_manager=None):
        self.device = device
        self.transfer_manager = transfer_manager


def handle_ping(ctx, seq, payload):
    return rsp_pong(seq, payload)


def handle_get_status(ctx, seq, payload):
    d = ctx.device
    return rsp_status(seq, d.state, d.mode, d.brightness, d.error)


def handle_set_mode(ctx, seq, payload):
    mode = payload[0]
    if mode not in (MODE_IDLE, MODE_STATIC, MODE_ANIMATION, MODE_STREAM, MODE_DIAGNOSTIC):
        return rsp_nack(seq, ERR_INVALID_ARG)

    ctx.device.set_mode(mode)
    return rsp_ack(seq)


def handle_set_brightness(ctx, seq, payload):
    ctx.device.set_brightness(payload[0])
    return rsp_ack(seq)


def handle_set_pixel(ctx, seq, payload):
    p = unpack_set_pixel(payload)
    try:
        ctx.device.set_pixel(p["index"], p["r"], p["g"], p["b"], p["w"])
    except ValueError:
        return rsp_nack(seq, ERR_OUT_OF_RANGE)
    return rsp_ack(seq)


def handle_fill(ctx, seq, payload):
    p = unpack_fill(payload)
    ctx.device.fill(p["r"], p["g"], p["b"], p["w"])
    return rsp_ack(seq)


def handle_show(ctx, seq, payload):
    ctx.device.show()
    return rsp_ack(seq)


def handle_clear(ctx, seq, payload):
    ctx.device.clear()
    return rsp_ack(seq)


def handle_play(ctx, seq, payload):
    p = unpack_play(payload)

    # For animation IDs derived from file contents, the worker must tell the
    # master immediately whether it already has the file. The master can then
    # decide whether to stream the file.
    if hasattr(ctx.device, "has_animation"):
        if not ctx.device.has_animation(p["anim_id"]):
            return rsp_nack(seq, ERR_FILE_MISSING)

    ok = ctx.device.play(p["anim_id"], p["loop"], p["fps"])
    if not ok:
        return rsp_nack(seq, ERR_INVALID_ARG)
    return rsp_ack(seq)


def handle_stop(ctx, seq, payload):
    ctx.device.stop()
    return rsp_ack(seq)


# =========================================================
# UART file transfer
# =========================================================
def handle_begin_transfer(ctx, seq, payload):
    print("HANDLE BEGIN_TRANSFER seq={} len={}".format(seq, len(payload)))

    if not hasattr(ctx, "transfer_manager") or ctx.transfer_manager is None:
        print("BEGIN_TRANSFER: no transfer_manager on ctx")
        return rsp_nack(seq, ERR_NOT_READY)

    try:
        p = unpack_begin_transfer(payload)

        print(
            "BEGIN_TRANSFER parsed id={} type={} size={}".format(
                p["transfer_id"],
                p["transfer_type"],
                p["total_size"],
            )
        )

        ok = ctx.transfer_manager.begin(
            p["transfer_id"],
            p["transfer_type"],
            p["total_size"],
        )

        if not ok:
            print("BEGIN_TRANSFER rejected error={}".format(ctx.transfer_manager.error))
            return rsp_nack(seq, ctx.transfer_manager.error or ERR_TRANSFER_FAILED)

        print("BEGIN_TRANSFER accepted")
        return rsp_ack(seq)

    except Exception as e:
        print("BEGIN_TRANSFER exception:", repr(e))
        return rsp_nack(seq, ERR_TRANSFER_FAILED)


def handle_data_chunk(ctx, seq, payload):
    print("HANDLE DATA_CHUNK seq={} len={}".format(seq, len(payload)))

    if not hasattr(ctx, "transfer_manager") or ctx.transfer_manager is None:
        print("DATA_CHUNK: no transfer_manager on ctx")
        return rsp_nack(seq, ERR_NOT_READY)

    try:
        p = unpack_data_chunk(payload)

        print(
            "DATA_CHUNK parsed id={} chunk={} bytes={}".format(
                p["transfer_id"],
                p["chunk_index"],
                len(p["data"]),
            )
        )

        status = ctx.transfer_manager.add_chunk(
            p["transfer_id"],
            p["chunk_index"],
            p["data"],
        )

        expected_next = ctx.transfer_manager.expected_chunk_index

        print(
            "DATA_CHUNK status={} expected_next={}".format(
                status,
                expected_next,
            )
        )

        return rsp_transfer_status(
            seq,
            p["transfer_id"],
            status,
            expected_next,
        )

    except Exception as e:
        print("DATA_CHUNK exception:", repr(e))
        return rsp_nack(seq, ERR_TRANSFER_FAILED)

def handle_end_transfer(ctx, seq, payload):
    if not hasattr(ctx, "transfer_manager") or ctx.transfer_manager is None:
        return rsp_nack(seq, ERR_NOT_READY)

    try:
        p = unpack_end_transfer(payload)
        transfer_id = p["transfer_id"]
        expected_crc = p["crc32"]

        status = ctx.transfer_manager.end(transfer_id, expected_crc)

        return rsp_transfer_status(
            seq,
            transfer_id,
            status,
            ctx.transfer_manager.expected_chunk_index,
        )

    except Exception as e:
        print("END_TRANSFER error:", repr(e))
        return rsp_nack(seq, ERR_TRANSFER_FAILED)

def dispatch_packet(ctx, pkt):
    cmd = pkt["cmd"]
    seq = pkt["seq"]
    payload = pkt["payload"]

    fn = DISPATCH.get(cmd)
    if fn is None:
        return rsp_nack(seq, ERR_UNKNOWN_CMD)

    return fn(ctx, seq, payload)


DISPATCH = {
    CMD_PING: handle_ping,
    CMD_GET_STATUS: handle_get_status,
    CMD_SET_MODE: handle_set_mode,
    CMD_SET_BRIGHTNESS: handle_set_brightness,
    CMD_SET_PIXEL: handle_set_pixel,
    CMD_FILL: handle_fill,
    CMD_SHOW: handle_show,
    CMD_CLEAR: handle_clear,
    CMD_PLAY: handle_play,
    CMD_STOP: handle_stop,

    CMD_BEGIN_TRANSFER: handle_begin_transfer,
    CMD_DATA_CHUNK: handle_data_chunk,
    CMD_END_TRANSFER: handle_end_transfer,
}

