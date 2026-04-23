import json
import random
import socket
import time
from datetime import datetime
from pathlib import Path

from transport import IPHeader, HTTPDatagram


class Client:
    def __init__(
        self,
        client_ip="127.0.0.1",
        server_ip="127.128.0.1",
        gateway="127.0.0.254",
        server_port=8080,
        frame_size=1024,
        timeout=2,
    ):
        self.client_ip = client_ip
        self.client_port = random.randint(1024, 65535)
        self.server_ip = server_ip
        self.server_port = server_port
        self.gateway = gateway

        self.client_socket = socket.socket(
            socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW
        )
        self.client_socket.bind((self.client_ip, 0))
        self.client_socket.settimeout(timeout)

        self.frame_size = frame_size
        self.window_size = 4
        self.timeout = timeout
        self.base = 0
        self.seq_num = 0
        self.ack_num = 0

    def initiate_handshake(self):
        syn_datagram = HTTPDatagram(
            source_ip=self.client_ip,
            dest_ip=self.server_ip,
            source_port=self.client_port,
            dest_port=self.server_port,
            seq_num=self.seq_num,
            ack_num=self.ack_num,
            flags=2,
            window_size=self.window_size,
            next_hop=self.gateway,
            data="SYN",
        )
        self.client_socket.sendto(syn_datagram.to_bytes(), (self.gateway, 0))
        self.seq_num += 1

        while True:
            try:
                frame = self.client_socket.recv(self.frame_size)
            except socket.timeout:
                return False

            datagram_fields = HTTPDatagram.from_bytes(frame)
            if (
                datagram_fields.flags == 18
                and datagram_fields.next_hop == self.client_ip
            ):
                self.ack_num = datagram_fields.seq_num + 1
                ack_datagram = HTTPDatagram(
                    source_ip=self.client_ip,
                    dest_ip=self.server_ip,
                    source_port=self.client_port,
                    dest_port=self.server_port,
                    seq_num=self.seq_num,
                    ack_num=self.ack_num,
                    flags=16,
                    window_size=self.window_size,
                    next_hop=self.gateway,
                    data="ACK",
                )
                self.client_socket.sendto(ack_datagram.to_bytes(), (self.gateway, 0))
                return True

    def build_request(self, resource, timestamp=None):
        request = f"GET {resource} HTTP/1.1\r\nHost: {self.server_ip}\r\n"
        if timestamp:
            request += f"If-Modified-Since: {timestamp}\r\n"
        request += "\r\n"
        return request

    def send_request_segments(self, request):
        request_bytes = request.encode()
        max_data_length = self.frame_size - 60
        request_data_segments = [
            request_bytes[i : i + max_data_length]
            for i in range(0, len(request_bytes), max_data_length)
        ]

        self.base = self.seq_num
        offset = self.seq_num

        while self.base < len(request_data_segments) + offset:
            for segment in request_data_segments[
                self.base - offset : self.base - offset + self.window_size
            ]:
                new_datagram = HTTPDatagram(
                    source_ip=self.client_ip,
                    dest_ip=self.server_ip,
                    source_port=self.client_port,
                    dest_port=self.server_port,
                    seq_num=self.seq_num,
                    ack_num=self.ack_num,
                    flags=24,
                    window_size=self.window_size,
                    next_hop=self.gateway,
                    data=segment.decode(),
                )
                self.client_socket.sendto(new_datagram.to_bytes(), (self.gateway, 0))
                self.seq_num += 1

            try:
                current_time = time.time()
                ack_received = False
                while time.time() - current_time < self.timeout:
                    frame_bytes = self.client_socket.recv(self.frame_size)
                    datagram_fields = HTTPDatagram.from_bytes(frame_bytes)

                    if (
                        datagram_fields.next_hop == self.client_ip
                        and datagram_fields.source_ip == self.server_ip
                        and datagram_fields.flags == 16
                    ):
                        self.base = datagram_fields.ack_num
                        self.seq_num = self.base
                        ack_received = True
                        break
                if not ack_received:
                    self.seq_num = self.base
            except socket.timeout:
                self.seq_num = self.base

    def process_response_segments(self):
        self.client_socket.settimeout(0.25)
        response = ""
        flags = 24
        datagram_fields = None

        while flags not in [17, 25]:
            current_time = time.time()

            while time.time() - current_time < 2 and flags not in [17, 25]:
                try:
                    response_datagram_bytes = self.client_socket.recv(self.frame_size)
                    ip_header = IPHeader.from_bytes(response_datagram_bytes)
                    if ip_header.dest_ip == self.client_ip:
                        datagram_fields = HTTPDatagram.from_bytes(
                            response_datagram_bytes
                        )
                        if (
                            datagram_fields.next_hop == self.client_ip
                            and datagram_fields.dest_port == self.client_port
                            and datagram_fields.flags in [17, 24, 25]
                            and datagram_fields.seq_num == self.ack_num
                        ):
                            self.ack_num += 1
                            response += datagram_fields.data
                            flags = datagram_fields.flags
                except socket.timeout:
                    continue

            if datagram_fields is None:
                continue

            ack = HTTPDatagram(
                source_ip=self.client_ip,
                dest_ip=datagram_fields.source_ip,
                source_port=self.client_port,
                dest_port=datagram_fields.source_port,
                seq_num=self.seq_num,
                ack_num=self.ack_num,
                flags=16,
                window_size=self.window_size,
                next_hop=self.gateway,
                data="ACK",
            )
            self.client_socket.sendto(ack.to_bytes(), (self.gateway, 0))

        return response

    def close_socket(self):
        self.client_socket.close()

    def request_resource(self, resource, timestamp=None):
        connection = self.initiate_handshake()
        if connection:
            request = self.build_request(resource, timestamp)
            self.send_request_segments(request)
            response = self.process_response_segments()
        else:
            response = "Failed to connect to the server."
        self.close_socket()
        return response


class Server:
    def __init__(
        self,
        server_ip="127.128.0.1",
        gateway="127.128.0.254",
        server_port=8080,
        frame_size=1024,
        timeout=2,
    ):
        self.server_ip = server_ip
        self.server_port = server_port
        self.gateway = gateway

        self.server_socket = socket.socket(
            socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW
        )
        self.server_socket.bind((self.server_ip, 0))

        self.frame_size = frame_size
        self.window_size = 4
        self.timeout = timeout
        self.base = 0
        self.seq_num = 0
        self.ack_num = 0

        base_path = Path(__file__).parent
        resources_path = base_path / "resources.json"
        with open(resources_path, "r") as file_handle:
            self.resources = json.load(file_handle)

    def accept_handshake(self, keep_running):
        syn = False
        while not syn:
            frame = self.server_socket.recv(self.frame_size)
            if IPHeader.from_bytes(frame).dest_ip != "224.0.0.5":
                datagram_fields = HTTPDatagram.from_bytes(frame)

                if (
                    datagram_fields.flags == 2
                    and datagram_fields.next_hop == self.server_ip
                ):
                    syn = True
                    self.ack_num = datagram_fields.seq_num + 1

        self.server_socket.settimeout(self.timeout)
        syn_ack_datagram = HTTPDatagram(
            source_ip=self.server_ip,
            dest_ip=datagram_fields.source_ip,
            source_port=self.server_port,
            dest_port=datagram_fields.source_port,
            seq_num=self.seq_num,
            ack_num=self.ack_num,
            flags=18,
            window_size=self.window_size,
            next_hop=self.gateway,
            data="SYN-ACK",
        )
        self.server_socket.sendto(syn_ack_datagram.to_bytes(), (self.gateway, 0))
        self.seq_num += 1

        while keep_running():
            try:
                frame = self.server_socket.recv(self.frame_size)
            except socket.timeout:
                self.reset_connection()
                return False

            if IPHeader.from_bytes(frame).dest_ip != "224.0.0.5":
                datagram_fields = HTTPDatagram.from_bytes(frame)
                if (
                    datagram_fields.flags == 16
                    and datagram_fields.ack_num == self.seq_num
                    and datagram_fields.next_hop == self.server_ip
                ):
                    return True

    def receive_request_segments(self):
        self.server_socket.settimeout(0.25)
        request = ""
        datagram = None

        while request[-4:] != "\r\n\r\n":
            current_time = time.time()
            while time.time() - current_time < 2:
                try:
                    frame_bytes = self.server_socket.recv(self.frame_size)
                    frame = IPHeader.from_bytes(frame_bytes)
                    if frame.dest_ip == self.server_ip:
                        datagram = HTTPDatagram.from_bytes(frame_bytes)
                        if (
                            datagram.next_hop == self.server_ip
                            and datagram.dest_port == self.server_port
                            and datagram.flags == 24
                            and datagram.seq_num == self.ack_num
                        ):
                            self.ack_num += 1
                            request += datagram.data
                except socket.timeout:
                    continue

            if datagram is None:
                continue

            ack = HTTPDatagram(
                source_ip=self.server_ip,
                dest_ip=datagram.source_ip,
                source_port=self.server_port,
                dest_port=datagram.source_port,
                seq_num=self.seq_num,
                ack_num=self.ack_num,
                flags=16,
                window_size=self.window_size,
                next_hop=self.gateway,
                data="ACK",
            )
            self.server_socket.sendto(ack.to_bytes(), (self.gateway, 0))

        return request, datagram.source_port, datagram.source_ip

    def process_request(self, request, dest_port, dest_ip):
        self.server_socket.settimeout(self.timeout)

        request_lines = request.split("\r\n")
        first_line = request_lines[0].split()
        method = first_line[0]
        resource = first_line[1]
        flags = 17

        if method != "GET":
            response = "HTTP/1.1 400 Bad Request\r\n\r\nInvalid Request"
        elif resource not in self.resources:
            response = "HTTP/1.1 404 Not Found\r\n\r\nResource Not Found"
        else:
            resource_info = self.resources[resource]
            body = resource_info["data"]
            response = f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n\r\n{body}"
            flags = 24

        response_bytes = response.encode()
        max_data_length = self.frame_size - 60
        response_data_segments = [
            response_bytes[i : i + max_data_length]
            for i in range(0, len(response_bytes), max_data_length)
        ]

        self.base = self.seq_num
        offset = self.seq_num

        while self.base < len(response_data_segments) + offset:
            for segment in response_data_segments[
                self.base - offset : self.base - offset + self.window_size
            ]:
                segment_flags = flags
                if (
                    self.seq_num == len(response_data_segments) + offset - 1
                    and flags != 17
                ):
                    segment_flags = 25
                datagram = HTTPDatagram(
                    source_ip=self.server_ip,
                    dest_ip=dest_ip,
                    source_port=self.server_port,
                    dest_port=dest_port,
                    seq_num=self.seq_num,
                    ack_num=self.ack_num,
                    flags=segment_flags,
                    window_size=self.window_size,
                    next_hop=self.gateway,
                    data=segment.decode(),
                )

                self.server_socket.sendto(datagram.to_bytes(), (self.gateway, 0))
                self.seq_num += 1

            try:
                current_time = time.time()
                ack_received = False
                while time.time() - current_time < self.timeout:
                    ack_bytes = self.server_socket.recv(self.frame_size)
                    ack = HTTPDatagram.from_bytes(ack_bytes)
                    if (
                        ack.next_hop == self.server_ip
                        and ack.source_ip == dest_ip
                        and ack.flags == 16
                    ):
                        self.base = ack.ack_num
                        self.seq_num = self.base
                        ack_received = True
                        break
                if not ack_received:
                    self.seq_num = self.base
            except socket.timeout:
                self.seq_num = self.base

    def reset_connection(self):
        self.base = 0
        self.seq_num = 0
        self.ack_num = 0
        self.server_socket.settimeout(None)

    def close_server(self):
        self.server_socket.close()

    def run(self, print_with_time, keep_running, request_list=None):
        print_with_time(f"Web Server: STARTED")
        connected = self.accept_handshake(keep_running)
        if connected:
            print_with_time(f"Web Server: CLIENT CONNECTED")
            request, port, ip = self.receive_request_segments()
            if request_list is not None:
                request_list.append(request)
            self.process_request(request, port, ip)
        self.reset_connection()
        print_with_time(f"Web Server: END")
