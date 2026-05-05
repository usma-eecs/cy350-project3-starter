"""Shared Ethernet-like frame helpers used by hosts and switches."""

import struct
from typing import Self


HEADER_FORMAT = "!6s6sH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


class Frame:
    """Represents a parsed Ethernet-like frame with header fields and payload."""

    def __init__(
        self,
        destination_mac: str,
        source_mac: str = "00:00:00:00:00:00",
        ethertype: int = 0x0800,
        payload: str | bytes = "",
    ) -> None:
        self.destination_mac = destination_mac
        self.source_mac = source_mac
        self.ethertype = ethertype
        self.payload = payload.encode() if isinstance(payload, str) else payload

    @staticmethod
    def _mac_bytes_to_str(raw_mac: bytes) -> str:
        return ":".join(f"{byte:02x}" for byte in raw_mac)

    @staticmethod
    def mac_str_to_bytes(mac_address: str) -> bytes:
        parts = mac_address.split(":")
        if len(parts) != 6:
            raise ValueError(f"Invalid MAC address: {mac_address}")
        return bytes(int(part, 16) for part in parts)

    def encode(self) -> bytes:
        """Build an Ethernet-like frame with a fixed 14-byte header."""
        return (
            struct.pack(
                HEADER_FORMAT,
                Frame.mac_str_to_bytes(self.destination_mac),
                Frame.mac_str_to_bytes(self.source_mac),
                self.ethertype,
            )
            + self.payload
        )

    def decode(frame: bytes) -> Self | None:
        """Parse destination/source MAC and ethertype from a raw frame.

        Returns None when the frame is too short.
        """
        if len(frame) < HEADER_SIZE:
            return None

        destination_raw, source_raw, ethertype = struct.unpack(
            HEADER_FORMAT, frame[:HEADER_SIZE]
        )
        payload = frame[HEADER_SIZE:]
        return Frame(
            destination_mac=Frame._mac_bytes_to_str(destination_raw),
            source_mac=Frame._mac_bytes_to_str(source_raw),
            ethertype=ethertype,
            payload=payload,
        )

    def __str__(self) -> str:
        payload_preview = self.payload[:50] + (
            b"..." if len(self.payload) > 50 else b""
        )
        return f"Frame(dest={self.destination_mac}, src={self.source_mac}, payload='{payload_preview.decode()}')"
