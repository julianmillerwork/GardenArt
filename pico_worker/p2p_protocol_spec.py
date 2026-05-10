from micropython import const

# =========================================================
# Packet format
#
# +--------+------+-----+------+----------+----------+
# |  SOF   | CMD  | SEQ | LEN  | PAYLOAD  | CHECKSUM |
# +--------+------+-----+------+----------+----------+
#    1B      1B    1B    1B      0..255B      1B
#
# SOF      = Start of frame marker (0xAA)
# CMD      = Command ID
# SEQ      = Sequence number for request/response matching
# LEN      = Payload length in bytes
# PAYLOAD  = Command-specific arguments
# CHECKSUM = XOR of CMD, SEQ, LEN and all payload bytes
# =========================================================
SOF = const(0xAA)

# =========================================================
# Command IDs
# =========================================================
CMD_ACK             = const(0x01)
CMD_NACK            = const(0x02)
CMD_PING            = const(0x03)
CMD_PONG            = const(0x04)
CMD_GET_STATUS      = const(0x05)
CMD_STATUS          = const(0x06)
CMD_RESET           = const(0x07)

CMD_SET_MODE        = const(0x10)
CMD_SET_BRIGHTNESS  = const(0x11)
CMD_SET_PIXEL       = const(0x12)
CMD_FILL            = const(0x13)
CMD_SHOW            = const(0x14)
CMD_CLEAR           = const(0x15)
CMD_PLAY            = const(0x16)
CMD_STOP            = const(0x17)
CMD_PAUSE           = const(0x18)
CMD_RESUME          = const(0x19)

CMD_BEGIN_TRANSFER  = const(0x20)
CMD_DATA_CHUNK      = const(0x21)
CMD_END_TRANSFER    = const(0x22)
CMD_TRANSFER_STATUS = const(0x23)

CMD_SET_CONFIG      = const(0x30)
CMD_GET_CONFIG      = const(0x31)
CMD_CONFIG          = const(0x32)
CMD_ERROR           = const(0x33)

# =========================================================
# Errors
# =========================================================
ERR_NONE            = const(0x00)
ERR_UNKNOWN_CMD     = const(0x01)
ERR_BAD_LENGTH      = const(0x02)
ERR_BAD_CHECKSUM    = const(0x03)
ERR_INVALID_ARG     = const(0x04)
ERR_BUSY            = const(0x05)
ERR_OUT_OF_RANGE    = const(0x06)
ERR_NOT_READY       = const(0x07)
ERR_TRANSFER_FAILED = const(0x08)
ERR_NO_MEMORY       = const(0x09)
ERR_BAD_SEQUENCE    = const(0x0A)
ERR_BAD_CRC         = const(0x0B)
ERR_FILE_MISSING    = const(0x0C)

# =========================================================
# Modes / states / transfer statuses
# =========================================================
MODE_IDLE       = const(0)
MODE_STATIC     = const(1)
MODE_ANIMATION  = const(2)
MODE_STREAM     = const(3)
MODE_DIAGNOSTIC = const(4)

STATE_IDLE      = const(0)
STATE_BUSY      = const(1)
STATE_PLAYING   = const(2)
STATE_PAUSED    = const(3)
STATE_ERROR     = const(4)

TRANSFER_OK          = const(0)
TRANSFER_NEED_RETRY  = const(1)
TRANSFER_BAD_CRC     = const(2)
TRANSFER_ABORTED     = const(3)
TRANSFER_IN_PROGRESS = const(4)

TRANSFER_TYPE_ANIMATION = const(1)
TRANSFER_TYPE_GENERIC   = const(2)

# Upper bound enforced by the worker before allocating the RAM staging buffer.
# A Pico/Pico W cannot stage an 800KB animation in RAM; increase only if your board can.
MAX_RAM_TRANSFER_BYTES = const(180 * 1024)

# =========================================================
# Command metadata
# min_len, max_len are payload sizes only
# response is the expected response command, or tuple of valid responses
# fixed_len=True means payload must be exactly min_len
# =========================================================
COMMANDS = {
    CMD_ACK:             {"name": "ACK",             "min_len": 1, "max_len": 1,   "fixed_len": True,  "response": None},
    CMD_NACK:            {"name": "NACK",            "min_len": 1, "max_len": 1,   "fixed_len": True,  "response": None},
    CMD_PING:            {"name": "PING",            "min_len": 0, "max_len": 255, "fixed_len": False, "response": CMD_PONG},
    CMD_PONG:            {"name": "PONG",            "min_len": 0, "max_len": 255, "fixed_len": False, "response": None},
    CMD_GET_STATUS:      {"name": "GET_STATUS",      "min_len": 0, "max_len": 0,   "fixed_len": True,  "response": CMD_STATUS},
    CMD_STATUS:          {"name": "STATUS",          "min_len": 4, "max_len": 4,   "fixed_len": True,  "response": None},
    CMD_RESET:           {"name": "RESET",           "min_len": 0, "max_len": 1,   "fixed_len": False, "response": (CMD_ACK, CMD_NACK)},

    CMD_SET_MODE:        {"name": "SET_MODE",        "min_len": 1, "max_len": 1,   "fixed_len": True,  "response": (CMD_ACK, CMD_NACK)},
    CMD_SET_BRIGHTNESS:  {"name": "SET_BRIGHTNESS",  "min_len": 1, "max_len": 1,   "fixed_len": True,  "response": (CMD_ACK, CMD_NACK)},
    CMD_SET_PIXEL:       {"name": "SET_PIXEL",       "min_len": 6, "max_len": 6,   "fixed_len": True,  "response": (CMD_ACK, CMD_NACK)},
    CMD_FILL:            {"name": "FILL",            "min_len": 4, "max_len": 4,   "fixed_len": True,  "response": (CMD_ACK, CMD_NACK)},
    CMD_SHOW:            {"name": "SHOW",            "min_len": 0, "max_len": 0,   "fixed_len": True,  "response": (CMD_ACK, CMD_NACK)},
    CMD_CLEAR:           {"name": "CLEAR",           "min_len": 0, "max_len": 0,   "fixed_len": True,  "response": (CMD_ACK, CMD_NACK)},
    CMD_PLAY:            {"name": "PLAY",            "min_len": 6, "max_len": 6,   "fixed_len": True,  "response": (CMD_ACK, CMD_NACK)},
    CMD_STOP:            {"name": "STOP",            "min_len": 0, "max_len": 0,   "fixed_len": True,  "response": (CMD_ACK, CMD_NACK)},
    CMD_PAUSE:           {"name": "PAUSE",           "min_len": 0, "max_len": 0,   "fixed_len": True,  "response": (CMD_ACK, CMD_NACK)},
    CMD_RESUME:          {"name": "RESUME",          "min_len": 0, "max_len": 0,   "fixed_len": True,  "response": (CMD_ACK, CMD_NACK)},

    CMD_BEGIN_TRANSFER:  {"name": "BEGIN_TRANSFER",  "min_len": 9, "max_len": 9,   "fixed_len": True,  "response": (CMD_ACK, CMD_NACK)},
    CMD_DATA_CHUNK:      {"name": "DATA_CHUNK",      "min_len": 6, "max_len": 255, "fixed_len": False, "response": (CMD_ACK, CMD_NACK, CMD_TRANSFER_STATUS)},
    # END_TRANSFER payload: transfer_id_u32_be + expected_crc32_be
    CMD_END_TRANSFER:    {"name": "END_TRANSFER",    "min_len": 8, "max_len": 8,   "fixed_len": True,  "response": (CMD_TRANSFER_STATUS, CMD_ACK, CMD_NACK)},
    CMD_TRANSFER_STATUS: {"name": "TRANSFER_STATUS", "min_len": 7, "max_len": 7,   "fixed_len": True,  "response": None},

    CMD_SET_CONFIG:      {"name": "SET_CONFIG",      "min_len": 2, "max_len": 255, "fixed_len": False, "response": (CMD_ACK, CMD_NACK)},
    CMD_GET_CONFIG:      {"name": "GET_CONFIG",      "min_len": 1, "max_len": 1,   "fixed_len": True,  "response": CMD_CONFIG},
    CMD_CONFIG:          {"name": "CONFIG",          "min_len": 2, "max_len": 255, "fixed_len": False, "response": None},
    CMD_ERROR:           {"name": "ERROR",           "min_len": 1, "max_len": 2,   "fixed_len": False, "response": None},
}

# =========================================================
# Helpers
# =========================================================
def cmd_name(cmd):
    meta = COMMANDS.get(cmd)
    return "UNKNOWN" if meta is None else meta["name"]

def is_known_command(cmd):
    return cmd in COMMANDS

def validate_payload_length(cmd, payload_len):
    meta = COMMANDS.get(cmd)
    if meta is None:
        return False, ERR_UNKNOWN_CMD

    min_len = meta["min_len"]
    max_len = meta["max_len"]
    fixed_len = meta["fixed_len"]

    if fixed_len:
        if payload_len != min_len:
            return False, ERR_BAD_LENGTH
        return True, ERR_NONE

    if payload_len < min_len or payload_len > max_len:
        return False, ERR_BAD_LENGTH

    return True, ERR_NONE

def expected_response(cmd):
    meta = COMMANDS.get(cmd)
    return None if meta is None else meta["response"]
