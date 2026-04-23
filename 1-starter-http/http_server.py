import os
import sys
import time
import socket
import random
import json
from pathlib import Path
import hashlib
import base64


class HTTPServer:
    def __init__(
        self,
        server_ip="127.0.0.1",
        server_port=8090,
        frame_size: int = 64,
        timeout: float = 2.0,
    ):
        """
        Initialize the HTTP-like TCP server configuration and resources.

        Parameters
        - server_ip : str - The IP address to listen on.
        - server_port : int - The TCP port to listen on.
        - frame_size : int - Maximum bytes to read/write per send/recv.
        - timeout : float - Socket timeout (seconds) used after accepting.

        Returns: Nothing at all.
        """

        print("Initializing HTTP Server...")

        self.server_ip = server_ip
        self.server_port = server_port
        self.frame_size = frame_size
        self.timeout = timeout

        base_path = Path(__file__).parent
        resources_path = base_path / "resources.json"
        with open(resources_path, "r") as f:
            self.resources = json.load(f)

        # connection-related attributes
        self.connection = None
        self.client_address = None

        print("HTTP Server initialized. Attempting to bind to socket...")

        # create a TCP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # bind and listen
        self.sock.bind((self.server_ip, self.server_port))
        self.sock.listen(1)
        print(
            f"Socket bound to {self.server_ip}:{self.server_port} and listening for connections."
        )

        # NOTE: Do not set timeout on the listening socket, but only on the accepted connection socket

    def run(self):
        """
        Setup the server socket, loop to accept incoming connections, and handle requests.

        This function should run indefinitely until the server is manually stopped (e.g., with Ctrl+C).
        """

        while True:
            print("Listening for incoming connections...")

            self.connection, self.client_address = self.sock.accept()
            print(f"Accepted connection from {self.client_address}")
            self.connection.settimeout(self.timeout)

            requestBytes = b""
            data = b""
            while True:
                try:
                    data = self.connection.recv(self.frame_size)
                    requestBytes += data

                    # Assuming end of request if received data is less than frame size
                    if len(data) < self.frame_size:
                        break

                except socket.timeout:
                    print("Socket timed out while receiving data.")
                    break
                except Exception as e:
                    print(f"An error occurred while receiving data: {e}")
                    break

            request = requestBytes.decode()

            print(f"==== REQUEST ====\n{request.strip()}\n==== END REQUEST ====")

            method, resource, requestHeaders = self.parse_request(request)
            print(f"Received request from {self.client_address}: {method} {resource}")
            if method != "GET":
                response = self.build_405()
            elif not resource in self.resources:
                response = self.build_404()
            else:
                response = self.handle_GET(resource, requestHeaders)
            print(f"==== RESPONSE ===\n{response.strip()}\n==== END RESPONSE ====")
            # print(f"RESPONSE: {response.splitlines()[0]}")
            self.send_response(response)
            print(f"Sent response to {self.client_address}")

            try:
                self.connection.shutdown(socket.SHUT_WR)
                print(f"Shutting down connection: {self.client_address}")
            except Exception as e:
                print(f"An error occurred while shutting down the connection: {e}")

    def parse_request(self, request: str):
        """
        Parse the HTTP request to extract the protocol, method, resource, headers, body.

        Returns:
        - method: The HTTP method (e.g., GET, POST).
        - resource: The requested resource (e.g., /about).
        - headers: A dictionary of HTTP headers.
        """
        method, resource, headers = None, None, {}
        try:
            request = request
            lines = request.splitlines()
            if not lines:
                return None, None, {}
            request_line = lines[0]
            parts = request_line.split()
            if len(parts) < 2:
                print(f"Invalid HTTP request line: {request_line}")
                return None, None, {}
            method = parts[0]
            resource = parts[1]

            for line in lines[1:]:
                if line == "":
                    break  # End of headers
                header_parts = line.split(":", 1)
                if len(header_parts) == 2:
                    header_name = header_parts[0].strip()
                    header_value = header_parts[1].strip()
                    headers[header_name] = header_value

            return method, resource, headers
        except Exception as e:
            print(f"Error parsing request: {e}")
            return None, None, {}

    def handle_GET(self, resource: str, requestHeaders: dict = {}) -> str:
        """
        Build an HTTP response for the specified resource.

        Returns: A valid HTTP response string
        """
        if resource not in self.resources:
            return self.build_404()

        if_none_match = requestHeaders.get("If-None-Match")
        if if_none_match:
            data = self.resources[resource]["data"]
            etag = self.calculate_etag(data)
            if if_none_match == etag:
                return self.build_response("304 Not Modified")

        if_modified_since = requestHeaders.get("If-Modified-Since")
        if if_modified_since:
            last_modified = self.resources[resource]["last_modified"]
            if if_modified_since >= last_modified:
                return self.build_response("304 Not Modified")

        responseStatus = "200 OK"
        responseBody = self.resources[resource]["data"]
        etag = self.calculate_etag(responseBody)
        headers = {
            "Last-Modified": self.resources[resource]["last_modified"],
            "Content-Type": self.resources[resource]["content_type"],
            "ETag": etag,
        }
        return self.build_response(responseStatus, responseBody, headers)

    def handle_POST(
        self, resource: str, requestHeaders: dict = {}, requestBody: str = ""
    ) -> str:
        """
        Handle a POST request for the specified resource.

        Returns: A valid HTTP response string
        """

        # TODO: implement POST handling logic, i.e. update resource data based on incoming request body

        return (
            "HTTP/1.1 501 Not Implemented\r\n"
            + "Connection: close\r\n"
            + "Content-Type: text/plain\r\n"
            + "Content-Length: 19\r\n"
            + "\r\n"
            + "501 Not Implemented"
        )

    def build_response(
        self, responseStatus: str, responseBody: str = "", headers: dict = {}
    ) -> str:
        """
        Build an HTTP response with the specified status code, status message, body, and content type.

        Returns: HTTP response string
        """

        headers["Connection"] = "close"

        if "Content-Type" not in headers:
            headers["Content-Type"] = "text/plain"
        if len(responseBody) > 0:
            headers["Content-Length"] = str(len(responseBody))

        response = f"HTTP/1.1 {responseStatus}\r\n"
        for header, value in headers.items():
            response += f"{header}: {value}\r\n"
        response += "\r\n"  # End of headers
        response += responseBody

        return response

    def build_304(self) -> str:
        """
        Build a 304 Not Modified HTTP response.

        Returns: HTTP response string
        """
        return "HTTP/1.1 304 Not Modified\r\n\r\n"

    def build_404(self) -> str:
        """
        Build a 404 Not Found HTTP response.

        Returns: HTTP response string
        """
        response = (
            "HTTP/1.1 404 Not Found\r\n"
            + "Connection: close\r\n"
            + "Content-Type: text/plain\r\n"
            + "Content-Length: 13\r\n"
            + "\r\n"
            + "404 Not Found"
        )
        return response

    def build_405(self) -> str:
        """
        Build a 405 Method Not Allowed HTTP response.

        Returns: HTTP response string
        """
        response = (
            "HTTP/1.1 405 Method Not Allowed\r\n"
            + "Connection: close\r\n"
            + "Content-Type: text/plain\r\n"
            + "Content-Length: 22\r\n"
            + "\r\n"
            + "405 Method Not Allowed"
        )
        return response

    def calculate_etag(self, content: str) -> str:
        """
        Calculate an ETag for the given content.
        """
        digest = hashlib.sha256(content.encode()).digest()
        return base64.b64encode(digest).decode()

    def send_response(self, response: str) -> None:
        """
        Send the response in chunks of size `frame_size` until the entire response is sent.
        """
        responseBytes = response.encode()
        total_sent = 0
        while total_sent < len(responseBytes):
            try:
                self.send_chunk(
                    responseBytes[total_sent : total_sent + self.frame_size]
                )
                total_sent += self.frame_size
            except Exception as e:
                print(f"Error sending response: {e}")
                break

    def send_chunk(self, chunk: bytes) -> None:
        """
        Send a single chunk of data through the connection socket.
        """
        if len(chunk) > self.frame_size:
            raise ValueError(
                f"Chunk size {len(chunk)} exceeds frame size {self.frame_size}"
            )
        self.connection.sendall(chunk)
        time.sleep(random.uniform(0.02, 0.1))  # Simulate network delay

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            print("Connection closed.")
        self.sock.close()


if __name__ == "__main__":
    if os.name != "posix":
        print(
            "This program should be run on Linux or WSL or docker. You may remove this check at your own risk."
        )
        sys.exit(1)

    try:
        server = HTTPServer(frame_size=64, timeout=2.0)
        server.run()
    except KeyboardInterrupt:
        print("Shutting down server...")
    except Exception as e:
        print(f"Error: {e}")
        print(
            f"An error occurred. Add some try/except blocks to find out what went wrong and handle the errors gracefully."
        )
        print("Shutting down server...")
    finally:
        server.close()
        print("Server shutdown complete.")
