import argparse
import os
import signal
import sys
import tempfile
import threading
import time

from host import Host
from switch import Switch
from frame import Frame


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demo/test script for the FIFO-based switch implementation"
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmpdir:
        s1 = Switch(
            "s1", [("s1_1", "host_a"), ("s1_2", "s2_2"), ("s1_3", "host_d")], tmpdir
        )
        s2 = Switch(
            "s2", [("s2_1", "host_b"), ("s2_2", "s1_2"), ("s2_3", "host_c")], tmpdir
        )
        host_a = Host("host_a", "12:34:56:aa:aa:aa", "s1_1", tmpdir)
        host_b = Host("host_b", "12:34:56:bb:bb:bb", "s2_1", tmpdir)
        host_c = Host("host_c", "12:34:56:cc:cc:cc", "s2_3", tmpdir)
        host_d = Host("host_d", "12:34:56:dd:dd:dd", "s1_3", tmpdir)

        stop_event = threading.Event()
        threads = []
        for target in [s1, s2, host_a, host_b, host_c, host_d]:
            thread = threading.Thread(
                target=target.run,
                kwargs={"stop_event": stop_event},
                daemon=True,
            )
            threads.append(thread)

        try:
            for thread in threads:
                thread.start()

            print("Simulation ready.")
            print()

            print("Test 1: Host A sends to Host B")

            frame = Frame(host_b.mac, payload="Hello from A")
            host_a.send(frame)
            print(f"s1 MAC table: {s1.mac_table}")
            print(f"s2 MAC table: {s2.mac_table}")
            print()
            time.sleep(0.5)

            # TODO: add more tests here to demonstrate the switch's learning and forwarding behavior; be thorough!

            print("Simulation complete.")
        finally:
            stop_event.set()
            time.sleep(0.5)
            for thread in threads:
                thread.join(timeout=0.1)
            for target in [s1, s2, host_a, host_b, host_c, host_d]:
                target.close()


def _handle_sigint(signum, frame):
    print()
    print("Interrupted. Exiting gracefully.")
    sys.exit(0)


if __name__ == "__main__":
    # if os is not linux, warn and exit
    if os.name != "posix":
        print("This program will only run on UNIX-like systems (Linux, WSL, Docker)")
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_sigint)
    main()
