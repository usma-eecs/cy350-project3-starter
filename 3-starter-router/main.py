import threading
import time

from application import Client, Server
from network import Router

ROUTER_INTERFACE_DATA = {
    "1.1.1.1": (
        {
            "Gi0/1": ("127.0.0.254", "127.0.0.1"),
            "Gi0/2": ("127.248.0.1", "127.248.0.2"),
            "Gi0/3": ("127.248.4.1", "127.248.4.2"),
        },
        {
            "127.0.0.0/24": (0, "Gi0/1"),
            "2.2.2.2": (3, "Gi0/2"),
            "3.3.3.3": (9, "Gi0/3"),
        },
    ),
    "2.2.2.2": (
        {
            "Gi0/1": ("127.248.0.2", "127.248.0.1"),
            "Gi0/2": ("127.30.0.254", "127.30.0.1"),
            "Gi0/3": ("127.248.12.1", "127.248.12.2"),
            "Gi0/4": ("127.248.8.1", "127.248.8.2"),
        },
        {
            "127.30.0.0/24": (0, "Gi0/2"),
            "1.1.1.1": (3, "Gi0/1"),
            "3.3.3.3": (5, "Gi0/4"),
            "4.4.4.4": (12, "Gi0/3"),
        },
    ),
    "3.3.3.3": (
        {
            "Gi0/1": ("127.248.4.2", "127.248.4.1"),
            "Gi0/2": ("127.248.8.2", "127.248.8.1"),
            "Gi0/3": ("127.248.16.1", "127.248.16.2"),
            "Gi0/4": ("127.10.0.254", "127.10.0.1"),
        },
        {
            "127.10.0.0/24": (0, "Gi0/4"),
            "1.1.1.1": (9, "Gi0/1"),
            "2.2.2.2": (5, "Gi0/2"),
            "5.5.5.5": (10, "Gi0/3"),
        },
    ),
    "4.4.4.4": (
        {
            "Gi0/1": ("127.248.12.2", "127.248.12.1"),
            "Gi0/2": ("127.40.0.254", "127.40.0.1"),
            "Gi0/3": ("127.248.24.1", "127.248.24.2"),
            "Gi0/4": ("127.248.20.1", "127.248.20.2"),
        },
        {
            "127.40.0.0/24": (0, "Gi0/2"),
            "2.2.2.2": (12, "Gi0/1"),
            "5.5.5.5": (4, "Gi0/4"),
            "6.6.6.6": (10, "Gi0/3"),
        },
    ),
    "5.5.5.5": (
        {
            "Gi0/1": ("127.248.16.2", "127.248.16.1"),
            "Gi0/2": ("127.248.20.2", "127.248.20.1"),
            "Gi0/3": ("127.248.28.1", "127.248.28.2"),
        },
        {
            "127.20.0.0/24": (0, "Gi0/4"),
            "3.3.3.3": (10, "Gi0/1"),
            "4.4.4.4": (4, "Gi0/2"),
            "6.6.6.6": (5, "Gi0/3"),
        },
    ),
    "6.6.6.6": (
        {
            "Gi0/1": ("127.248.24.2", "127.248.24.1"),
            "Gi0/2": ("127.248.28.2", "127.248.28.1"),
            "Gi0/3": ("127.128.0.254", "127.128.0.1"),
        },
        {
            "127.128.0.0/24": (0, "Gi0/3"),
            "4.4.4.4": (10, "Gi0/1"),
            "5.5.5.5": (5, "Gi0/2"),
        },
    ),
}

START_TIME = time.time()
KEEP_RUNNING = True


def print_with_time(message):
    print(f"[{time.time() - START_TIME:06.3f}] {message}")


def keep_running():
    return KEEP_RUNNING


router_threads = []
server_thread = None


def main():
    routers = []

    for router_id, (interfaces, direct_connections) in ROUTER_INTERFACE_DATA.items():
        routers.append(Router(router_id, interfaces, direct_connections))

    web_server = Server()
    server_thread = threading.Thread(
        target=web_server.run, args=(print_with_time, keep_running)
    )
    web_client = None

    print_with_time(f"Starting network simulation with {len(routers)} routers.")

    for router in routers:
        print_with_time(router)
        router_thread = threading.Thread(
            target=router.run, args=(print_with_time, keep_running)
        )
        router_threads.append(router_thread)
        router_thread.start()

    server_thread.start()

    print_with_time("Sending initial LSAs from all routers.")
    for router in routers:
        router.send_initial_lsa()

    wait_time = 10  # seconds
    print_with_time(
        f"Waiting for {wait_time} seconds to allow LSAs to propagate and routing tables to stabilize."
    )
    time.sleep(wait_time)

    print_with_time("Starting HTTP client to request resource from web server.")
    web_client = Client()
    response = web_client.request_resource("/testimonials")

    print_with_time(f"Received response ({len(response)} bytes) from web server.")

    print(f"=== RESPONSE ===\n{response}\n=== END RESPONSE ===")

    print_with_time("Transmission complete. Shutting down network simulation.")

    time.sleep(1)  # Allow any final messages to be printed before shutting down

    global KEEP_RUNNING
    KEEP_RUNNING = False

    for thread in router_threads:
        thread.join(2.5)

    print_with_time("All router are now down. Shutting down web server.")
    web_server.close_server()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_with_time("Simulation interrupted by user. Shutting down gracefully.")
        KEEP_RUNNING = False
        for thread in router_threads:
            thread.join(2.5)
        if server_thread is not None:
            server_thread.join(2.5)
        print_with_time("All threads have been shut down. Exiting.")
