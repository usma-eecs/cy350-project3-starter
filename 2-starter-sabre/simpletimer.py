import time


class SimpleTimer:
    """Single-shot timer used for the sender's base packet."""

    def __init__(self, timeout_sec: float):
        self.timeout_sec = timeout_sec
        self.start_time = None

    def start(self) -> None:
        """Start or restart the timer."""
        self.start_time = time.monotonic()

    def stop(self) -> None:
        """Stop the timer."""
        self.start_time = None

    def expired(self) -> bool:
        """Return True if the timer has timed out."""
        if self.start_time is None:
            return False
        return (time.monotonic() - self.start_time) >= self.timeout_sec

    def remaining(self) -> float:
        """Return the remaining time until timeout, or 0 if expired."""
        if self.start_time is None:
            return self.timeout_sec
        elapsed = time.monotonic() - self.start_time
        return max(0.0, self.timeout_sec - elapsed)
