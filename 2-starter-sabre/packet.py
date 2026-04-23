import struct
from typing import Union

# SABRE packet flags
FLAG_DATA = 0x00
FLAG_ACK = 0x01
FLAG_SYN = 0x02
FLAG_FIN = 0x04
FLAG_RST = 0x08


class SabrePacket:
    # TYPE_SABRE is the fixed first byte of the header to identify this as a SABRE packet
    TYPE_SABRE = 0xC5
    HEADER_FORMAT = "!BBHHHI"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    # maximum payload size to avoid IP fragmentation
    MAX_PAYLOAD = 1460

    def __init__(self, flags, seq, ack, cadet_id, payload=b""):
        """
        Initialize a SABRE packet.

        Attributes:
        - flags: 1-bit packet flags (DATA, ACK, SYN, FIN, RST)
        - seq: sequence number
        - ack: acknowledgment number
        - cadet_id: C-number to identify the sender
        - payload: packet payload
        """

        self.flags = flags
        self.length = len(payload)
        self.seq = seq
        self.ack = ack
        self.cadet_id = int(cadet_id)
        self.payload = payload

        if flags not in (
            FLAG_DATA,
            FLAG_ACK,
            FLAG_SYN,
            FLAG_FIN,
            FLAG_RST,
            FLAG_SYN | FLAG_ACK,
            FLAG_FIN | FLAG_ACK,
        ):
            raise ValueError(f"Invalid packet flags: {flags:#04x}")

        if len(payload) > SabrePacket.MAX_PAYLOAD:
            raise ValueError(
                f"Payload too large: {len(payload)} bytes (max {SabrePacket.MAX_PAYLOAD})"
            )

        if seq < 0 or seq > 0xFFFF or ack < 0 or ack > 0xFFFF:
            raise ValueError(f"Sequence or Acknowledgment number out of range.")

    def encode(self):
        payload = self.payload or b""
        encoded_length = self.length if self.length is not None else len(payload)
        header = struct.pack(
            SabrePacket.HEADER_FORMAT,
            SabrePacket.TYPE_SABRE,
            self.flags,
            encoded_length & 0xFFFF,
            self.seq & 0xFFFF,
            self.ack & 0xFFFF,
            self.cadet_id & 0xFFFFFFFF,
        )
        return header + payload

    @staticmethod
    def decode(data):
        """Decode raw bytes into a SabrePacket instance."""

        if len(data) < SabrePacket.HEADER_SIZE:
            raise ValueError("Packet too short to contain SABRE header")

        header = data[: SabrePacket.HEADER_SIZE]
        payload = data[SabrePacket.HEADER_SIZE :]

        pkt_type, flags, length, seq, ack, cadet_id = struct.unpack(
            SabrePacket.HEADER_FORMAT, header
        )

        if pkt_type != SabrePacket.TYPE_SABRE:
            raise ValueError("Invalid packet type, definitely not a SABRE packet")

        if len(payload) > length:
            payload = payload[:length]

        return SabrePacket(flags, seq, ack, cadet_id, payload)
