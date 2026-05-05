"""Host endpoint abstraction for the FIFO-based switch demo."""

import os
from typing import Optional

from frame import Frame


class Host:
    """Simple host that sends/receives Ethernet-like frames through a FIFO."""

    def __init__(self, name: str, mac: str, switch_interface: str, tmpdir: str) -> None:
        self.name = name
        self.mac = mac
        self._tmpdir = tmpdir
        self._read_path = os.path.join(tmpdir, name)
        self._write_path = os.path.join(tmpdir, switch_interface)
        self._read_fd: Optional[int] = None

        try:
            os.mkfifo(self._read_path)
        except FileExistsError:
            pass

        self._read_fd = os.open(self._read_path, os.O_RDONLY | os.O_NONBLOCK)

    def send(self, frame: Frame) -> None:
        """Send one frame to the FIFO attached to a switch ingress interface."""
        frame.source_mac = self.mac
        try:
            fd = os.open(self._write_path, os.O_WRONLY | os.O_NONBLOCK)
            try:
                os.write(fd, frame.encode())
            finally:
                os.close(fd)
        except (OSError, IOError):
            pass

    def receive(self) -> Optional[bytes]:
        """Read at most one frame from this host's FIFO in non-blocking mode."""
        if self._read_fd is None:
            return None
        try:
            data = os.read(self._read_fd, 65535)
            return data if data else None
        except (OSError, IOError):
            return None

    def close(self) -> None:
        if self._read_fd is not None:
            try:
                os.close(self._read_fd)
            except OSError:
                pass
            self._read_fd = None

    def run(
        self,
        timeout: float = 0.2,
        stop_event=None,
    ) -> None:
        """Continuously read frames until `stop_event` is set."""
        if self._read_fd is None:
            return

        while True:
            if stop_event is not None and stop_event.is_set():
                break
            try:
                data = os.read(self._read_fd, 65535)
                frame = Frame.decode(data) if data else None
                if data:
                    print(f"[{self.name}] received: {frame}")
            except (OSError, IOError):
                pass
