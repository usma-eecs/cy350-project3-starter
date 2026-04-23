import socket
from simpletimer import SimpleTimer
from typing import List, Tuple
from packet import SabrePacket, FLAG_ACK, FLAG_SYN, FLAG_FIN, FLAG_RST, FLAG_DATA

# never exceed 1460 bytes to avoid IP fragmentation
# 1500 - 20 byte IP header - 8 byte UDP header - 12 byte SABRE header = 1460
MTU = 1460


class SABRESender:
    def __init__(
        self,
        remote: Tuple[str, int],
        cadet_id: int = 0,
        window_size: int = 5,
        timeout: float = 1.0,
    ):
        """
        Initialize the SABRE sender.

        Attributes:
        - remote: (IP, port) tuple of the receiver
        - cadet_id: unique identifier for this sender
        - WINDOW_SIZE: number of unacknowledged packets allowed in flight
        - TIMEOUT: retransmission timeout in seconds
        - sock: UDP socket for sending/receiving packets
        - timer: SimpleTimer instance for managing retransmission timeouts
        - connected: whether the connection has been established
        - next_seq: next sequence number to use for outgoing packets
        - send_base: sequence number of the oldest unacknowledged packet
        """
        self.remote = remote
        self.cadet_id = int(cadet_id) & 0xFFFFFFFF
        self.WINDOW_SIZE = int(window_size)
        self.TIMEOUT = float(timeout)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(
            ("", 0)
        )  # bind to ephemeral port to ensure we can receive responses
        self.sock.settimeout(self.TIMEOUT)

        self.timer = SimpleTimer(self.TIMEOUT)

        self.connected = False

        # next sequence number to send (initially 0, will be updated after handshake)
        self.next_seq = 0

        # base sequence number of the current window (initially 0, will be updated as ACKs are received)
        self.send_base = 0

        print(
            f"Cadet ID: C{self.cadet_id}, Remote: {self.remote}, Window Size: {self.WINDOW_SIZE}, Timeout: {self.TIMEOUT}"
        )

    # DO NOT MODIFY THIS FUNCTION
    def _make_packets(self, start_seq: int, data: bytes) -> List[SabrePacket]:
        """
        Split data into packets with appropriate sizes and sequence numbers.
        Given a starting sequence number, create a list of SabrePacket instances with the correct flags, sequence numbers, and payloads.
        """
        packets = []
        seq = start_seq
        for i in range(0, len(data), MTU):
            chunk = data[i : i + MTU]
            pkt = SabrePacket(
                FLAG_DATA, seq=seq, ack=0, cadet_id=self.cadet_id, payload=chunk
            )
            packets.append(pkt)
            seq += 1
        return packets

    # DO NOT MODIFY THIS FUNCTION
    def _send_packet(self, pkt: SabrePacket) -> None:
        """Encode and send a packet to the receiver."""
        self.sock.sendto(pkt.encode(), self.remote)

    # DO NOT MODIFY THIS FUNCTION
    def _recv_packet(self, timeout: float = None) -> SabrePacket:
        """
        Receive a packet with a specified timeout. Returns None on timeout or decode error.

        You might have to call this function multiple times.

        Timeout can vary based if waiting for ACKs during send, so we specify it here as needed. Defaults to self.TIMEOUT if not provided.
        """

        if timeout is None:
            timeout = self.TIMEOUT
        self.sock.settimeout(timeout)

        try:
            data, _ = self.sock.recvfrom(SabrePacket.HEADER_SIZE + MTU)
        except socket.timeout:
            return None

        try:
            packet = SabrePacket.decode(data)
            return packet
        except Exception as e:
            print(f"Error decoding packet: {e}")
            return None

    def connect(self) -> None:
        """Perform a three-way handshake to establish connection with the receiver."""

        syn_seq = self.next_seq
        syn_pkt = SabrePacket(FLAG_SYN, seq=syn_seq, ack=0, cadet_id=self.cadet_id)
        attempt = 0
        print(f"INITIATE HANDSHAKE: SYN seq={syn_seq}, ")

        while attempt < 10:
            attempt += 1
            self.sock.sendto(syn_pkt.encode(), self.remote)
            self.sock.settimeout(self.TIMEOUT)
            try:
                data, _ = self.sock.recvfrom(MTU)
            except socket.timeout:
                print(f"Handshake attempt {attempt} timed out, retrying...")
                continue

            try:
                pkt = SabrePacket.decode(data)
            except Exception as e:
                print(f"Error decoding packet during handshake: {e}")
                continue

            # expect SYN+ACK with ack == syn_seq + 1
            if (pkt.flags & FLAG_SYN) and (pkt.flags & FLAG_ACK):
                expected_ack = syn_seq + 1
                if pkt.ack != expected_ack:
                    print(
                        f"Received SYN+ACK with unexpected ack value: {pkt.ack} (expected {expected_ack}), ignoring"
                    )
                    continue

                print(
                    f"Received SYN+ACK with seq={pkt.seq}, ack={pkt.ack}. Handshake successful."
                )
                # set base/next_seq to expected_ack (cumulative semantics)
                self.send_base = expected_ack
                self.next_seq = expected_ack
                # send final ACK acknowledging server's SYN
                ack_pkt = SabrePacket(
                    FLAG_ACK,
                    seq=self.next_seq,
                    ack=(pkt.seq + 1),
                    cadet_id=self.cadet_id,
                )
                self.sock.sendto(ack_pkt.encode(), self.remote)
                print(
                    f"Sent final ACK for handshake with seq={ack_pkt.seq}, ack={ack_pkt.ack}"
                )
                self.connected = True
                return
            if pkt.flags & FLAG_RST:
                raise ConnectionError("Remote reset during handshake")

        raise TimeoutError("Handshake failed (no SYN+ACK)")

    def send(self, data: bytes) -> None:
        """
        Send data reliably using the Go-Back-N sliding window protocol.

        Useful Variables:
        - send_base: sequence number of the oldest unacknowledged packet
        - next_seq: sequence number of the next packet to send
        - end_seq: sequence number after the last packet of our data stream; marks the end of our current send operation
        """

        if not self.connected:
            raise RuntimeError("Not connected. Call connect() first.")
        if not data:
            raise ValueError("What are we sending?")

        start_seq = self.next_seq
        packets = self._make_packets(start_seq, data)
        total_packets = len(packets)

        print(
            f"START SEND: {len(data)} bytes, start_seq: {self.next_seq}, total_packets: {total_packets}"
        )

        # invariants:
        # - packets[i] has seq = start_seq + i
        # - we want to finish when send_base >= start_seq + total_packets
        end_seq = start_seq + total_packets

        # local window indices are numeric sequence values
        self.timer.stop()

        while self.send_base < end_seq:
            print(
                f"Window: send_base={self.send_base}, next_seq={self.next_seq}, end_seq={end_seq}"
            )
            # send as many as window allows
            while (
                self.next_seq < self.send_base + self.WINDOW_SIZE
                and self.next_seq < end_seq
            ):
                print(f"Sending packet with seq={self.next_seq}")
                idx = self.next_seq - start_seq
                pkt = packets[idx]
                self._send_packet(pkt)
                # start timer when send_base == next_seq (first outstanding)
                if self.send_base == self.next_seq:
                    self.timer.start()
                self.next_seq += 1

            # if timer expired?
            # select timeout -> check timer expiration explicitly
            if self.timer.expired():
                print(
                    f"Timer expired. Retransmitting packets in window [{self.send_base}, {self.next_seq - 1}]"
                )
                # retransmit all unacked packets [base_seq .. next_seq-1]
                for s in range(self.send_base, self.next_seq):
                    idx = s - start_seq
                    if 0 <= idx < total_packets:
                        self._send_packet(packets[idx])
                # restart timer
                self.timer.start()

            # wait either for ACK or timer expiry
            timeout = (
                self.timer.remaining()
                if self.timer.start_time is not None
                else self.TIMEOUT
            )

            pkt = self._recv_packet(timeout)
            if pkt is None:
                print("Timeout waiting for ACK")
                continue
            # if RST -> abort
            if pkt.flags & FLAG_RST:
                raise ConnectionError("Connection reset by remote")
            # process ACK (receiver uses cumulative ack = next_expected_seq)
            if pkt.flags & FLAG_ACK:
                ack_val = pkt.ack
                # only advance if ack_val > base_seq (cumulative)
                if ack_val > self.send_base:
                    self.send_base = ack_val
                    # if no outstanding, stop timer; else restart timer
                    if self.send_base >= self.next_seq:
                        self.timer.stop()
                    else:
                        self.timer.start()
                # ignore other packet types here (could be SYN from middle or FIN)

        # all data acked; advance next_seq to end_seq so future sends continue sequence space
        self.next_seq = end_seq

    def close(self) -> None:
        """
        Perform a connection teardown with a FIN handshake.
        """

        if not self.connected:
            self.sock.close()
            return

        fin_seq = self.next_seq
        fin_pkt = SabrePacket(FLAG_FIN, seq=fin_seq, ack=0, cadet_id=self.cadet_id)
        attempt = 0
        while attempt < 10:
            attempt += 1
            self.sock.sendto(fin_pkt.encode(), self.remote)
            print(f"Sent FIN with seq={fin_seq}")

            try:
                data, _ = self.sock.recvfrom(MTU)
            except socket.timeout:
                print(f"FIN attempt {attempt} timed out, retrying...")
                continue

            try:
                pkt = SabrePacket.decode(data)
            except Exception as e:
                print(f"Error decoding packet during FIN exchange: {e}")
                continue

            # accept ACK that acknowledges our FIN (either fin_seq or fin_seq+1)
            if pkt.flags & FLAG_ACK:
                if pkt.ack in (fin_seq, fin_seq + 1):
                    print(
                        f"Received ACK for FIN with ack={pkt.ack}. Connection closed gracefully."
                    )
                    print(
                        f"Final ACK packet: seq={pkt.seq}, ack={pkt.ack}, flags={pkt.flags:#04x}, payload={pkt.payload.decode(errors='replace')}"
                    )
                    break

            if pkt.flags & FLAG_RST:
                print("Received RST during FIN exchange. Connection closed by remote.")
                break

        self.connected = False
        self.sock.close()
