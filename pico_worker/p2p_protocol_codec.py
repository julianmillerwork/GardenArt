# p2p_protocol_codec.py
from p2p_protocol_spec import *

def xor_checksum(cmd, seq, payload):
    c = cmd ^ seq ^ len(payload)
    for b in payload:
        c ^= b
    return c & 0xFF


# ==================build_packet===========================
# Encodes:
# SOF | CMD | SEQ | LEN | PAYLOAD | CHECKSUM
# =========================================================
def build_packet(cmd, seq, payload=b""):
    ok, err = validate_payload_length(cmd, len(payload))
    if not ok:
        raise ValueError("invalid payload length for command {}".format(cmd_name(cmd)))

    chk = xor_checksum(cmd, seq, payload)
    return bytes([SOF, cmd, seq, len(payload)]) + payload + bytes([chk])

# ==================PacketParser===========================
# Parses:
# SOF | CMD | SEQ | LEN | PAYLOAD | CHECKSUM
# =========================================================
class PacketParser:
    WAIT_SOF = 0
    READ_HDR = 1
    READ_PAYLOAD = 2
    READ_CHECKSUM = 3

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = self.WAIT_SOF
        self.hdr = bytearray()
        self.payload = bytearray()
        self.cmd = 0
        self.seq = 0
        self.length = 0

    def feed(self, b):
        if self.state == self.WAIT_SOF:
            if b == SOF:
                self.hdr = bytearray()
                self.payload = bytearray()
                self.state = self.READ_HDR
            return None

        elif self.state == self.READ_HDR:
            self.hdr.append(b)
            if len(self.hdr) == 3:
                self.cmd = self.hdr[0]
                self.seq = self.hdr[1]
                self.length = self.hdr[2]
                self.state = self.READ_CHECKSUM if self.length == 0 else self.READ_PAYLOAD
            return None

        elif self.state == self.READ_PAYLOAD:
            self.payload.append(b)
            if len(self.payload) >= self.length:
                self.state = self.READ_CHECKSUM
            return None

        elif self.state == self.READ_CHECKSUM:
            calc = xor_checksum(self.cmd, self.seq, self.payload)
            rx_chk = b

            if rx_chk != calc:
                self.reset()
                return {
                    "ok": False,
                    "error": ERR_BAD_CHECKSUM,
                    "cmd": self.cmd,
                    "seq": self.seq,
                }

            ok, err = validate_payload_length(self.cmd, len(self.payload))
            if not ok:
                self.reset()
                return {
                    "ok": False,
                    "error": err,
                    "cmd": self.cmd,
                    "seq": self.seq,
                }

            pkt = {
                "ok": True,
                "cmd": self.cmd,
                "cmd_name": cmd_name(self.cmd),
                "seq": self.seq,
                "payload": bytes(self.payload),
            }
            self.reset()
            return pkt