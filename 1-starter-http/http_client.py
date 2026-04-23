import os
import sys
import time
import socket
import random
import json
from pathlib import Path
import hashlib
import base64
import argparse


class HTTPClient:
    def __init__(
        self,
        server_ip="127.0.0.1",
        server_port=8090,
        frame_size: int = 64,
        timeout: float = 2.0,
    ):
        """
        Initialize the HTTP client configuration and resources.

        Parameters
        - server_ip : str - The IP address of the server to connect to.
        - server_port : int - The TCP port of the server to connect to.
        - frame_size : int - Maximum bytes to read/write per send/recv.
        - timeout : float - Socket timeout (seconds) used after accepting.

        Returns: Nothing at all.
        """

        print("Initializing HTTP Client...")

        self.server_ip = server_ip
        self.server_port = server_port
        self.frame_size = frame_size
        self.timeout = timeout

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.server_ip, self.server_port))
        print(f"Connected to server at {self.server_ip}:{self.server_port}")

    def build_request(self, method: str, path: str, headers: dict = None):
        """
        Build an HTTP request message.

        Parameters
        - method : str - HTTP method (e.g., "GET", "POST").
        - path : str - The path of the resource (e.g., "/index.html").
        - headers : dict - Optional dictionary of HTTP headers.
        - body : bytes - Optional body of the request (for POST).

        Returns: The full HTTP request as bytes.
        """
        if headers is None:
            headers = {}

        request_line = f"{method} {path} HTTP/1.1\r\n"
        header_lines = "".join(f"{key}: {value}\r\n" for key, value in headers.items())
        blank_line = "\r\n"

        return (request_line + header_lines + blank_line).encode()

    def send_request(self, request: bytes):
        """
        Send the HTTP request to the server.

        Parameters
        - request : bytes - The full HTTP request message to send.

        Returns: Nothing at all.
        """
        self.sock.sendall(request)
        print(f"Sent request:\n{request.decode()}")

    def receive_response(self):
        """
        Receive the HTTP response from the server.

        Parameters: None.

        Returns: The full HTTP response as bytes.
        """
        response = b""
        print(f"Receiving response:\n===============================")
        while True:
            try:
                chunk = self.sock.recv(self.frame_size)
                if not chunk:
                    break
                response += chunk
                print(chunk.decode(), end="", flush=True)
            except socket.timeout:
                print("\nSocket timed out while waiting for response.")
                break

        print(f"\n===============================\n")

        return response

    def process_response(self, response: bytes):
        """
        Process the HTTP response and print the status code and body.

        Parameters
        - response : bytes - The full HTTP response message.

        Returns: Nothing at all.
        """
        try:
            header_part, body_part = response.split(b"\r\n\r\n", 1)
            headers = header_part.decode().split("\r\n")
            status_line = headers[0]
            protocol, status_code, status_message = status_line.split(" ", 2)
            headers_dict = {}
            for header in headers[1:]:
                key, value = header.split(":", 1)
                headers_dict[key.strip()] = value.strip()
            return {
                "protocol": protocol,
                "status_code": int(status_code),
                "status_message": status_message,
                "headers": headers_dict,
                "body": body_part,
            }

        except Exception as e:
            print(f"Error processing response: {e}")


if __name__ == "__main__":
    if os.name != "posix":
        print(
            "This program should be run on Linux or WSL or docker. You may remove this check at your own risk."
        )
        sys.exit(1)

    client = None

    try:
        parser = argparse.ArgumentParser(description="Simple HTTP client")
        parser.add_argument(
            "resource", help="Resource path to request (e.g., / or /about)"
        )
        args = parser.parse_args()

        resource = (
            args.resource if args.resource.startswith("/") else f"/{args.resource}"
        )
        client = HTTPClient()
        request = client.build_request("GET", resource)
        client.send_request(request)
        response_bytes = client.receive_response()
        response = client.process_response(response_bytes)

        print(
            f"Response Status: {response['status_code']} {response['status_message']}"
        )
        print(f"Response Headers: {response['headers']}")

    except KeyboardInterrupt:
        print("Shutting down client...")
    except Exception as e:
        print(f"Error: {e}")
        print("Shutting down client...")
    finally:
        if client:
            client.sock.close()
            print("Client shutdown complete.")
