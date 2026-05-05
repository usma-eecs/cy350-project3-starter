"""Simple Layer-2 switch simulation.

This module provides a single-threaded Switch class that learns source MAC
addresses, decides forwarding interfaces, and sends raw Ethernet-like frames
across named pipes (FIFOs) so multiple switch objects can communicate.

Interface schema (list of tuples):
[
    ("near_interface_0", "far_interface_0"),
    ("near_interface_1", "far_interface_1"),
    ...
]
"""

import os
import select
from typing import Dict, Optional, Set

from frame import Frame


class Switch:
    """A minimal link-layer switch with MAC learning and frame forwarding via named pipes."""

    BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"

    def __init__(
        self, name: str, connections: list[tuple[str, str]], tmpdir: str
    ) -> None:
        """
        Initialize the switch with a name, a list of (near_interface, far_interface) tuples, and a temporary directory for UNIX pipes that act as interfaces.

        Attributes:
        - name: A string identifier for the switch (e.g., "s1").
        - connections: A list of tuples where each tuple contains:
            - near_interface: The name of the switch's interface (e.g., "s1_1").
            - far_interface: The name of the connected interface on the other switch or host (e.g., "s2_1").
        - tmpdir: The directory where the named pipes (FIFOs) for interfaces will be created.
        """

        self.name = name
        self.tmpdir = tmpdir
        self.interfaces: Set[str] = set()  # Set of interface names
        self.fd_to_interface: Dict[int, str] = {}  # file descriptor -> interface name
        self.destinations: Dict[
            str, str
        ] = {}  # interface name -> destination file descriptor
        self.mac_table: Dict[str, str] = {}  # learned MAC -> interface_name

        for near_interface, far_interface in connections:
            read_path = os.path.join(self.tmpdir, near_interface)

            try:
                os.mkfifo(read_path)
            except FileExistsError:
                pass

            fd = os.open(read_path, os.O_RDONLY | os.O_NONBLOCK)
            self.interfaces.add(near_interface)
            self.fd_to_interface[fd] = near_interface
            self.destinations[near_interface] = far_interface

    def send_frame(self, frame: bytes, near_interface: str) -> None:
        """Send a raw frame through one interface to the connected destination named pipe."""
        if near_interface not in self.destinations:
            return
        far_interface = self.destinations[near_interface]
        write_path = os.path.join(self.tmpdir, far_interface)
        try:
            fd = os.open(write_path, os.O_WRONLY | os.O_NONBLOCK)
            try:
                os.write(fd, frame)
            except OSError as e:
                print(
                    f"Error sending frame from {near_interface} to {far_interface}: {e}"
                )
            finally:
                os.close(fd)
        except (OSError, IOError):
            pass

    def run(
        self,
        timeout: float = 0.2,
        stop_event=None,
    ) -> None:
        """Run the main receive/forward loop without threading.

        This method merges process_once logic:
        - Poll all interface named pipes using select
        - Receive frames and forward them
        - iterations=None runs forever
        - iterations=N runs exactly N receive cycles
        """
        fds = list(self.fd_to_interface.keys())
        if not self.interfaces:
            return

        while True:
            if stop_event is not None and stop_event.is_set():
                break
            ready, _, _ = select.select(fds, [], [], timeout)
            for fd in ready:
                try:
                    frame = os.read(fd, 65535)
                except OSError:
                    continue

                if frame:
                    ingress_interface_name = self.fd_to_interface[fd]
                    self.forward_frame(frame, ingress_interface_name)

    def close(self) -> None:
        """Close all interface named pipes."""
        for fd in self.fd_to_interface.keys():
            try:
                os.close(fd)
            except OSError:
                pass

    def forward_frame(self, frame: bytes, ingress_interface_name: str) -> None:
        """Parse, learn MAC, decide output interfaces, and forward a received frame."""

        # TODO: Implement MAC learning and forwarding logic here

        pass
