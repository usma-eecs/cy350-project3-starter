import argparse
import os
import random
import signal
import sys

from corpus import Corpus
from sender import SABRESender


def main():

    # download and extract e-books from Project Gutenberg
    # this is the data that you will send to the server as payload
    # the corpus is stored in `gutenberg.zip` and extracted to the `gutenberg` directory
    corpus = Corpus()
    if not corpus.ready:
        print("Failed to download and extract corpus. Exiting.")
        sys.exit(1)

    corpus_files = corpus.list_files()

    # argparser reads and processes command line arguments
    argparser = argparse.ArgumentParser(description="SABRE File Sender")
    argparser.add_argument("--host", help="Server IP address", default="127.0.0.1")
    argparser.add_argument("--port", type=int, help="Server port", default=5060)
    argparser.add_argument(
        "--filename",
        type=str,
        help="Pick a file from the 'gutenberg' directory",
    )
    argparser.add_argument(
        "--window", type=int, default=5, help="Window size (packets)"
    )
    argparser.add_argument(
        "--timeout", type=float, default=1.0, help="Timeout (seconds)"
    )
    argparser.add_argument(
        "--max-payload", type=int, default=1460, help="Maximum payload size (bytes)"
    )
    args = argparser.parse_args()

    args.filename = args.filename or random.choice(corpus_files)

    print(f"Sending file: {args.filename} ({corpus.read_file(args.filename)[:50]}...)")

    # read the file to send from the corpus
    bytes_to_send = corpus.read_file(args.filename)

    try:
        # initialize the SABRE sender
        client = SABRESender(
            remote=(args.host, args.port),
            cadet_id=random.randint(1, 99999999),
            window_size=args.window,
            timeout=args.timeout,
        )

        # perform a 3-way handshake to establish connection with the server
        client.connect()

        # send the file data reliably using Selective Repeat protocol
        client.send(bytes_to_send)

        # perform connection teardown with a FIN sequence; this includes the server's final response which contains the flag if you successfully sent the file
        client.close()

    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)


def _handle_sigint(signum, frame):
    print()
    print("Interrupted. Exiting gracefully.")
    sys.exit(0)


if __name__ == "__main__":
    # if os is not linux, warn and exit
    if os.name != "posix":
        print("This program should be run on Linux or WSL or docker.")
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_sigint)
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
