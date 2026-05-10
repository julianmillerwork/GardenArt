import time
import os
import ubinascii

from p2p_protocol_spec import *
from p2p_protocol_codec import PacketParser
from p2p_protocol_payloads import unpack_status, unpack_transfer_status
from p2p_protocol_requests import (
    req_ping,
    req_get_status,
    req_set_mode,
    req_set_brightness,
    req_set_pixel,
    req_fill,
    req_show,
    req_clear,
    req_play,
    req_stop,
    req_begin_transfer,
    req_data_chunk,
    req_end_transfer,
)
from p2p_custom_uart_wrapper import (
    uart_send_bytes,
    uart_read_byte_nonblocking,
    uart_any,
    uart_flush,
)


class ProtocolTimeout(Exception):
    pass


class ProtocolError(Exception):
    def __init__(self, message, error_code=None, response=None):
        super().__init__(message)
        self.error_code = error_code
        self.response = response


class ProtocolMaster:
    def __init__(self):
        self.parser = PacketParser()
        self.seq = 0

    # =====================================================
    # Sequence handling
    # =====================================================
    def next_seq(self):
        self.seq = (self.seq + 1) & 0xFF
        if self.seq == 0:
            self.seq = 1
        return self.seq

    # =====================================================
    # Low-level TX/RX
    # =====================================================
    def send_packet(self, packet):
        uart_send_bytes(packet)
        uart_flush()

    def poll_packet(self):
        while uart_any():
            b = uart_read_byte_nonblocking()
            if b is None:
                return None

            pkt = self.parser.feed(b)
            if pkt is None:
                continue

            return pkt

        return None

    def wait_for_response(self, seq, expected_cmds=None, timeout_ms=500):
        if isinstance(expected_cmds, int):
            expected_cmds = (expected_cmds,)
        elif expected_cmds is not None:
            expected_cmds = tuple(expected_cmds)

        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)

        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            pkt = self.poll_packet()
            if pkt is None:
                time.sleep_ms(1)
                continue

            if not pkt["ok"]:
                continue

            if pkt["seq"] != seq:
                continue

            if expected_cmds is not None and pkt["cmd"] not in expected_cmds:
                raise ProtocolError(
                    "Unexpected response {} for seq {}".format(pkt["cmd_name"], seq),
                    response=pkt,
                )

            return pkt

        raise ProtocolTimeout("Timed out waiting for response to seq {}".format(seq))

    def transact(self, request_packet, seq, expected_cmds=None, timeout_ms=500, retries=2):
        last_exc = None

        for _ in range(retries + 1):
            self.send_packet(request_packet)
            try:
                return self.wait_for_response(
                    seq,
                    expected_cmds=expected_cmds,
                    timeout_ms=timeout_ms,
                )
            except ProtocolTimeout as e:
                last_exc = e

        raise last_exc

    # =====================================================
    # Response handling
    # =====================================================
    def require_ack(self, pkt):
        if pkt["cmd"] == CMD_ACK:
            return True

        if pkt["cmd"] == CMD_NACK:
            error_code = pkt["payload"][0] if pkt["payload"] else None
            raise ProtocolError("Received NACK", error_code=error_code, response=pkt)

        if pkt["cmd"] == CMD_ERROR:
            error_code = pkt["payload"][0] if pkt["payload"] else None
            raise ProtocolError("Received ERROR", error_code=error_code, response=pkt)

        raise ProtocolError("Expected ACK, got {}".format(pkt["cmd_name"]), response=pkt)

    def require_transfer_status(self, pkt, transfer_id, allowed_statuses):
        if isinstance(allowed_statuses, int):
            allowed_statuses = (allowed_statuses,)

        if pkt["cmd"] == CMD_NACK:
            error_code = pkt["payload"][0] if pkt["payload"] else None
            raise ProtocolError("Transfer NACK", error_code=error_code, response=pkt)

        if pkt["cmd"] == CMD_ACK:
            return {"transfer_id": transfer_id, "status": TRANSFER_OK, "chunk_index": 0}

        if pkt["cmd"] != CMD_TRANSFER_STATUS:
            raise ProtocolError("Expected TRANSFER_STATUS, got {}".format(pkt["cmd_name"]), response=pkt)

        status = unpack_transfer_status(pkt["payload"])
        if status["transfer_id"] != transfer_id:
            raise ProtocolError("TRANSFER_STATUS for wrong transfer_id", response=pkt)

        if status["status"] not in allowed_statuses:
            raise ProtocolError(
                "Unexpected transfer status {}".format(status["status"]),
                response=pkt,
            )

        return status

    # =====================================================
    # High-level commands
    # =====================================================
    def ping(self, data=b"hi", timeout_ms=500):
        seq = self.next_seq()
        req = req_ping(seq, data)
        rsp = self.transact(req, seq, expected_cmds=CMD_PONG, timeout_ms=timeout_ms)
        return rsp["payload"]

    def get_status(self, timeout_ms=500):
        seq = self.next_seq()
        req = req_get_status(seq)
        rsp = self.transact(req, seq, expected_cmds=CMD_STATUS, timeout_ms=timeout_ms)
        return unpack_status(rsp["payload"])

    def set_mode(self, mode, timeout_ms=500):
        seq = self.next_seq()
        req = req_set_mode(seq, mode)
        rsp = self.transact(req, seq, expected_cmds=(CMD_ACK, CMD_NACK, CMD_ERROR), timeout_ms=timeout_ms)
        self.require_ack(rsp)
        return True

    def set_brightness(self, brightness, timeout_ms=500):
        seq = self.next_seq()
        req = req_set_brightness(seq, brightness)
        rsp = self.transact(req, seq, expected_cmds=(CMD_ACK, CMD_NACK, CMD_ERROR), timeout_ms=timeout_ms)
        self.require_ack(rsp)
        return True

    def set_pixel(self, index, r, g, b, w=0, timeout_ms=500):
        seq = self.next_seq()
        req = req_set_pixel(seq, index, r, g, b, w)
        rsp = self.transact(req, seq, expected_cmds=(CMD_ACK, CMD_NACK, CMD_ERROR), timeout_ms=timeout_ms)
        self.require_ack(rsp)
        return True

    def fill(self, r, g, b, w=0, timeout_ms=500):
        seq = self.next_seq()
        req = req_fill(seq, r, g, b, w)
        rsp = self.transact(req, seq, expected_cmds=(CMD_ACK, CMD_NACK, CMD_ERROR), timeout_ms=timeout_ms)
        self.require_ack(rsp)
        return True

    def show(self, timeout_ms=500):
        seq = self.next_seq()
        req = req_show(seq)
        rsp = self.transact(req, seq, expected_cmds=(CMD_ACK, CMD_NACK, CMD_ERROR), timeout_ms=timeout_ms)
        self.require_ack(rsp)
        return True

    def clear(self, timeout_ms=500):
        seq = self.next_seq()
        req = req_clear(seq)
        rsp = self.transact(req, seq, expected_cmds=(CMD_ACK, CMD_NACK, CMD_ERROR), timeout_ms=timeout_ms)
        self.require_ack(rsp)
        return True

    def play(self, anim_id, loop=1, fps=30, timeout_ms=500):
        seq = self.next_seq()
        req = req_play(seq, anim_id, loop, fps)
        rsp = self.transact(req, seq, expected_cmds=(CMD_ACK, CMD_NACK, CMD_ERROR), timeout_ms=timeout_ms)
        self.require_ack(rsp)
        return True

    def stop(self, timeout_ms=500):
        seq = self.next_seq()
        req = req_stop(seq)
        rsp = self.transact(req, seq, expected_cmds=(CMD_ACK, CMD_NACK, CMD_ERROR), timeout_ms=timeout_ms)
        self.require_ack(rsp)
        return True

    # =====================================================
    # File transfer commands
    # =====================================================
    def begin_transfer(self, transfer_id, transfer_type, total_size, timeout_ms=5000):
        seq = self.next_seq()
        req = req_begin_transfer(seq, transfer_id, transfer_type, total_size)

        rsp = self.transact(
            req,
            seq,
            expected_cmds=(CMD_ACK, CMD_NACK, CMD_ERROR),
            timeout_ms=timeout_ms,
            retries=3,
        )

        self.require_ack(rsp)
        return True

    def data_chunk(self, transfer_id, chunk_index, data, timeout_ms=2000):
        seq = self.next_seq()
        req = req_data_chunk(seq, transfer_id, chunk_index, data)

        rsp = self.transact(
            req,
            seq,
            expected_cmds=(CMD_TRANSFER_STATUS, CMD_ACK, CMD_NACK, CMD_ERROR),
            timeout_ms=timeout_ms,
            retries=3,
        )

        if rsp["cmd"] == CMD_TRANSFER_STATUS:
            return unpack_transfer_status(rsp["payload"])

        self.require_ack(rsp)

        return {
            "transfer_id": transfer_id,
            "status": TRANSFER_OK,
            "chunk_index": chunk_index,
        }

    def end_transfer(self, transfer_id, expected_crc, timeout_ms=5000):
        seq = self.next_seq()
        req = req_end_transfer(seq, transfer_id, expected_crc)

        rsp = self.transact(
            req,
            seq,
            expected_cmds=(CMD_TRANSFER_STATUS, CMD_ACK, CMD_NACK, CMD_ERROR),
            timeout_ms=timeout_ms,
            retries=3,
        )

        if rsp["cmd"] == CMD_TRANSFER_STATUS:
            return unpack_transfer_status(rsp["payload"])

        self.require_ack(rsp)

        return {
            "transfer_id": transfer_id,
            "status": TRANSFER_OK,
            "chunk_index": 0,
        }

    def file_crc32(self, filename, block_size=512):
        crc = 0
        with open(filename, "rb") as f:
            while True:
                block = f.read(block_size)
                if not block:
                    break
                crc = ubinascii.crc32(block, crc) & 0xFFFFFFFF
        return crc & 0xFFFFFFFF

    def animation_id_for_file(self, filename):
        # Four-byte content-derived ID. This is also the transfer_id and the
        # CRC used by END_TRANSFER, so the worker stores files by their content ID.
        return self.file_crc32(filename)

    def send_file(
        self,
        filename,
        transfer_id=1,
        transfer_type=TRANSFER_TYPE_ANIMATION,
        chunk_size=249,
        progress=True,
        progress_every=10,
        inter_chunk_delay_ms=20,
        retry_delay_ms=50,
        max_chunk_retries=10,
    ):
        if chunk_size > 249:
            raise ValueError("chunk_size must be <= 249")

        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")

        size = os.stat(filename)[6]
        crc = self.file_crc32(filename)

        print(
            "BEGIN_TRANSFER id={:08x} size={} crc={:08x}".format(
                transfer_id & 0xFFFFFFFF,
                size,
                crc,
            )
        )

        self.begin_transfer(
            transfer_id,
            transfer_type,
            size,
            timeout_ms=5000,
        )

        chunk_index = 0
        sent = 0

        with open(filename, "rb") as f:
            while sent < size:
                data = f.read(chunk_size)
                if not data:
                    break

                retry_count = 0

                while True:
                    try:
                        status = self.data_chunk(
                            transfer_id,
                            chunk_index,
                            data,
                            timeout_ms=3000,
                        )

                    except ProtocolTimeout:
                        retry_count += 1
                        print(
                            "Timeout on chunk {} retry {}/{}".format(
                                chunk_index,
                                retry_count,
                                max_chunk_retries,
                            )
                        )

                        if retry_count > max_chunk_retries:
                            raise

                        time.sleep_ms(retry_delay_ms)
                        continue

                    if status["status"] == TRANSFER_NEED_RETRY:
                        retry_count += 1
                        requested = status.get("chunk_index", chunk_index)
                        print(
                            "Retry requested for chunk {} retry {}/{}".format(
                                requested,
                                retry_count,
                                max_chunk_retries,
                            )
                        )

                        if retry_count > max_chunk_retries:
                            raise ProtocolError(
                                "Too many retries during DATA_CHUNK",
                                error_code=TRANSFER_NEED_RETRY,
                            )

                        # Rewind to the requested chunk. This is safe because all
                        # chunks except the final chunk have the fixed chunk_size.
                        f.seek(requested * chunk_size)
                        chunk_index = requested
                        sent = requested * chunk_size
                        time.sleep_ms(retry_delay_ms)
                        data = f.read(chunk_size)
                        continue

                    if status["status"] not in (TRANSFER_IN_PROGRESS, TRANSFER_OK):
                        raise ProtocolError(
                            "Transfer failed during DATA_CHUNK",
                            error_code=status["status"],
                        )

                    break

                sent += len(data)
                chunk_index = (chunk_index + 1) & 0xFFFF

                if inter_chunk_delay_ms:
                    time.sleep_ms(inter_chunk_delay_ms)

                if progress and (chunk_index % progress_every == 0 or sent == size):
                    print(
                        "Sent {} / {} bytes ({:.1f}%)".format(
                            sent,
                            size,
                            (sent * 100.0) / size,
                        )
                    )

        status = self.end_transfer(
            transfer_id,
            crc,
            timeout_ms=5000,
        )

        if status["status"] != TRANSFER_OK:
            raise ProtocolError(
                "Transfer failed at END_TRANSFER",
                error_code=status["status"],
            )

        print("Transfer complete")
        return True
