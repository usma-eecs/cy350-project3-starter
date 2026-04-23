import logging
import select
import socket
import time
from collections import defaultdict

from transport import IPHeader, LSADatagram, HTTPDatagram

from pprint import pprint
import ipaddress

# This is how long the router will wait for LSAs to propagate before calculating the forwarding table and starting to forward datagrams.
LSA_WAIT_TIME = 3  # seconds


class Graph:
    def __init__(self):
        self.nodes = {}

    def add_node(self, node):
        if node not in self.nodes:
            self.nodes[node] = []

    def add_edge(self, from_node, to_node, cost, interface):
        self.add_node(from_node)
        self.add_node(to_node)
        self.nodes[from_node].append((to_node, cost, interface))


class Router:
    interface_sockets: dict[str, socket.socket]

    def __init__(
        self, router_id: str, router_interfaces: dict, direct_connections: dict
    ):
        self.router_id = router_id
        self.router_interfaces = router_interfaces
        self.direct_connections = direct_connections
        self.lsa_seq_num = 0
        self.interface_sockets = {}

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s.%(msecs)03d %(message)s",
            handlers=[logging.FileHandler("trace.log", mode="w")],
            datefmt="%H:%M:%S",
        )

        for interface, (source, _) in self.router_interfaces.items():
            try:
                int_socket = socket.socket(
                    socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW
                )
                int_socket.bind((source, 0))
                int_socket.setblocking(False)
                self.interface_sockets[interface] = int_socket
            except Exception as error:
                logging.error(f"Error creating socket for {interface}: {error}")

        receive_socket = socket.socket(
            socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW
        )
        receive_socket.bind(("0.0.0.0", 0))
        receive_socket.setblocking(False)
        self.interface_sockets["rec"] = receive_socket

        self.router_lsa_num = {}
        self.last_lsa_time = time.time()
        self.forwarding_table = {}
        self.lsdb = {}

        self.initialize_lsdb()

    def update_lsdb(self, adv_rtr: str, lsa: str):
        """
        Updates the LSDB with the information from a received LSA.
        """

        lines = [tuple(line.split(",")) for line in lsa.split("\r\n")]
        self.lsdb[adv_rtr] = [
            (neighbor.strip(), int(cost.strip()), interface.strip())
            for neighbor, cost, interface in lines
        ]

    def send_initial_lsa(self):
        for interface, (source, dest) in self.router_interfaces.items():
            int_socket = self.interface_sockets[interface]
            formatted_lsa_data = [
                f"{neighbor}, {cost}, {interface_name}"
                for neighbor, cost, interface_name in self.lsdb[self.router_id]
            ]
            new_datagram = LSADatagram(
                source_ip=source,
                dest_ip="224.0.0.5",
                adv_rtr=self.router_id,
                lsa_seq_num=self.lsa_seq_num,
                lsa_data="\r\n".join(formatted_lsa_data),
            )
            int_socket.sendto(new_datagram.to_bytes(), (dest, 0))
        logging.info(f"{self.router_id}: sent the initial LSA: {new_datagram}")

    def forward_lsa(self, lsa_datagram: LSADatagram, lsa_int: str):
        time.sleep(0.5)
        for interface in self.router_interfaces:
            if interface != lsa_int and lsa_datagram.adv_rtr != self.router_id:
                source, dest = self.router_interfaces[interface]
                int_socket = self.interface_sockets[interface]
                new_datagram = LSADatagram(
                    source_ip=source,
                    dest_ip="224.0.0.5",
                    adv_rtr=lsa_datagram.adv_rtr,
                    lsa_seq_num=lsa_datagram.lsa_seq_num,
                    lsa_data=lsa_datagram.lsa_data,
                )
                try:
                    int_socket.sendto(new_datagram.to_bytes(), (dest, 0))
                    logging.info(
                        f"{self.router_id}: LSA forwarded to {dest}: {new_datagram}"
                    )
                except Exception as error:
                    logging.error(f"Error forwarding LSA: {error}")

    def longest_prefix_match(self, ip_address: str) -> str | None:
        best_match = None
        best_prefix = -1

        for candidate in self.forwarding_table.keys():
            if not "/" in candidate:
                continue
            subnet = ipaddress.IPv4Network(candidate, strict=False)
            if (
                ipaddress.IPv4Address(ip_address) in subnet
                and subnet.prefixlen > best_prefix
            ):
                best_match = candidate
                best_prefix = subnet.prefixlen

        return best_match

    def listen_for_lsas(self):
        while time.time() - self.last_lsa_time < LSA_WAIT_TIME:
            ready_sockets, _, _ = select.select(
                list(self.interface_sockets.values()), [], [], 0.1
            )
            socket_to_interface = {
                sock: interface for interface, sock in self.interface_sockets.items()
            }

            for ready_socket in ready_sockets:
                interface = socket_to_interface[ready_socket]
                try:
                    new_datagram_bytes, address = ready_socket.recvfrom(1024)
                    new_datagram = IPHeader.from_bytes(new_datagram_bytes)
                    if new_datagram.dest_ip == "224.0.0.5":
                        if address[0] in [
                            connection[1]
                            for connection in self.router_interfaces.values()
                        ]:
                            self.process_link_state_advertisement(
                                new_datagram_bytes, interface
                            )
                except Exception as e:
                    print(f"Error receiving on {interface}: {e}")
                    continue

    def listen_for_forwarding_traffic(self, keep_running):
        while keep_running():
            ready_sockets, _, _ = select.select(
                list(self.interface_sockets.values()), [], [], 0.1
            )

            for ready_socket in ready_sockets:
                try:
                    new_datagram_bytes, _ = ready_socket.recvfrom(1024)
                    self.forward_datagram(new_datagram_bytes)
                except Exception as e:
                    print(f"Error forwarding datagram: {e}")
                    continue

    def run(self, print_with_time, keep_running):

        logging.info(self)

        print_with_time(f"{self.router_id}: Listening for LSAs.")
        logging.info(f"{self.router_id} Listening for LSAs.")
        self.listen_for_lsas()

        print_with_time(
            f"{self.router_id}: No new LSAs received for {LSA_WAIT_TIME} seconds. Calculating forwarding table."
        )
        logging.info(f"{self.router_id} Calculating forwarding table.")
        self.run_route_alg()

        from pprint import pformat

        logging.info(f"\n{self.router_id} LSDB:\n{pformat(self.lsdb)}\n")
        logging.info(
            f"\n{self.router_id} Forwarding Table:\n{pformat(self.forwarding_table)}\n"
        )

        print_with_time(
            f"{self.router_id}: Forwarding table calculated. Now forwarding datagrams."
        )
        logging.info(f"{self.router_id} Forwarding datagrams.")
        self.listen_for_forwarding_traffic(keep_running)

        print_with_time(f"{self.router_id}: Shutting down router.")
        logging.info(f"{self.router_id} Shutting down router.")
        self.shutdown()

    def shutdown(self):
        for interface in self.interface_sockets.keys():
            try:
                self.interface_sockets[interface].close()
            except Exception as error:
                logging.error(f"Error closing socket for {interface}: {error}")

    def __str__(self):
        return f"{self.router_id}: Direct Connections: {list(self.direct_connections.keys())}"

    ### START YOUR WORK HERE; DO NOT MODIFY ANYTHING ABOVE THIS LINE ###

    def initialize_lsdb(self):
        """
        Initializes the Link-State Database (LSDB) with the router's direct connections.

        The LSDB is a data structure that holds information about the router's directly connected networks
        and the cost of reaching them.

        Returns:
            None
        """

        ### INSERT CODE HERE ###
        # Store the destination, cost, and interface for each direct connection of the router in the LSDB
        pass

    def process_link_state_advertisement(self, lsa: bytes, interface: str):
        """
        Processes a received Link-State Advertisement (LSA) and updates the LSDB. If the LSA contains new information,
        the router broadcasts the LSA to its other interfaces.

        Args:
            lsa (bytes): The received LSA in byte form.
            interface (str): The interface on which the LSA was received.

        Returns:
            None

        Raises:
            None
        """
        ### INSERT CODE HERE ###
        ## Convert the lsa packet from bytes to a LSADatagram class object

        ## If the LSA is new and not from the router itself:
        # Reset the LSA timer (Router will assume all LSAs have been received if timer expires - greater than 5 seconds since new LSA received)
        # Update the LSA sequence number for the advertising router
        # Update the LSDB with the LSA data
        # Forward the LSA to all other interfaces, except the interface it was received on
        pass

    def forward_datagram(self, dgram: bytes):
        """
        Forwards an HTTP datagram to the appropriate next hop based on the forwarding table.

        Args:
            dgram (bytes): The datagram received as raw bytes.

        Returns:
            None

        Logs:
            Logs the process of forwarding the datagram to the appropriate next hop.

        Raises:
            Exception: Logs any errors during the forwarding process.
        """
        ### INSERT CODE HERE ###
        ## Convert the datagram bytes to an HTTPDatagram object

        ## If the next hop for the datagram associated with one of the router interfaces:
        # Convert the destination IP address to binary for longest prefix matching
        # Perform longest prefix match against known networks (those in the forwarding table with a CIDR)
        # Forward the datagram to the correct interface
        pass

    def run_route_alg(self):
        """
        Runs Dijkstra's shortest path algorithm to calculate the shortest paths to all nodes
        in the network and updates the forwarding table based on the LSDB.

        Returns:
            None
        """
        ### INSERT CODE HERE ###
        ## Create the graph by adding an edge (the node, neighbor, cost, and interface) for each entry in the LSDB.

        ## Initialization for Djikstra's algorithm
        # Create a set of visited nodes that has the start node only (initially)
        # Set the distance to all known nodes to infinity, except for:
        #       - the start node, which is initialized to 0
        #       - the nodes directly connected to the start node should have distance equal to their cost
        # Additionally, store the full path from the start node to each node. Initially, the path to each node
        #       is an empty list since no path has been calculated yet.

        ## Dijkstra's algorithm

        # While not all nodes have been processed (i.e., while N_prime does not include all nodes in the graph)

        # Find the node 'w' not in N_prime that has the smallest distance (D[w]) from the source node
        # This is the next node to process

        # Add node 'w' to the set of processed nodes N_prime (i.e., its shortest path has been found)

        # For all neighbors of node 'w'

        # Only consider neighbors that have not been processed yet (i.e., not in N_prime)

        # Calculate the potential new distance to this neighbor through node 'w'

        # If this new distance is shorter than the current known distance to 'neighbor'

        # Update the shortest known distance to 'neighbor'

        # Update the path to 'neighbor', by appending the (neighbor, interface) tuple
        # to the path that leads to 'w'

        ## Construct the forwarding table for each node in the graph.
        # For each node, store:
        # 1. The outgoing interface used to reach the node, which is found by accessing the first hop in 'paths[node]' (if a path exists).
        # 2. The shortest known distance to that node from the source, stored in 'D[node]'.
        # If there is no path to the node, the interface is set to None.
        # The resulting forwarding table maps each node to a tuple: (interface, shortest distance).
        pass
