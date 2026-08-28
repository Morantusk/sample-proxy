import socket
import threading
import uuid

from sample_proxy.core.protocol import *
from sample_proxy.core.socks5 import (
    connect_through_socks5,
    handle_socks5,
    send_socks5_reply,
)


def close_socket(sock):
    try:
        sock.shutdown(
            socket.SHUT_RDWR
        )
    except Exception:
        pass

    try:
        sock.close()
    except Exception:
        pass


def relay_socket(left, right):
    try:
        while True:
            data = left.recv(
                4096
            )

            if not data:
                break

            right.sendall(
                data
            )
    finally:
        close_socket(left)
        close_socket(right)


class TunnelNode:
    def __init__(
        self,
        socks_listen=None,
        tunnel_listen=None,
        connect_socks=None,
        connect_target=None,
        forwards=None,
        allow_targets=None,
    ):
        self.socks_listen = socks_listen
        self.tunnel_listen = tunnel_listen
        self.connect_socks = connect_socks
        self.connect_target = connect_target
        self.forwards = forwards or []
        self.allow_targets = allow_targets or set()
        self.node_id = str(
            uuid.uuid4()
        )
        self.send_lock = threading.Lock()
        self.local_stream_lock = threading.Lock()
        self.local_stream_id = -1 if connect_socks else 0
        self.active_tunnel = None
        self.active_tunnel_lock = threading.Lock()
        self.local_clients = {}
        self.remote_sockets = {}

    def next_local_stream(self):
        with self.local_stream_lock:
            self.local_stream_id += 2
            return self.local_stream_id

    def get_tunnel(self):
        with self.active_tunnel_lock:
            return self.active_tunnel

    def set_tunnel(self, tunnel):
        with self.active_tunnel_lock:
            self.active_tunnel = tunnel

    def clear_tunnel(self, tunnel):
        with self.active_tunnel_lock:
            if self.active_tunnel is tunnel:
                self.active_tunnel = None

    def safe_send(self, msg_type, sid, data=b""):
        tunnel = self.get_tunnel()
        if tunnel is None:
            raise ConnectionError(
                "no active tunnel"
            )

        with self.send_lock:
            send_packet(
                tunnel,
                msg_type,
                sid,
                data,
            )

    def encode_open_target(self, host, port):
        return (
            f"{self.node_id}|{host}:{port}"
        ).encode()

    def parse_open_target(self, data):
        text = data.decode()
        if "|" in text:
            _, target = text.split(
                "|",
                1,
            )
        else:
            target = text

        host, port = target.rsplit(
            ":",
            1,
        )
        return host, int(port)

    def tunnel_reader(self, tunnel):
        self.set_tunnel(
            tunnel
        )

        print(
            "tunnel connected"
        )

        try:
            while True:
                packet = recv_packet(
                    tunnel
                )

                if not packet:
                    break

                msg_type, sid, data = packet

                print(
                    "tunnel recv",
                    msg_type,
                    sid,
                    len(data),
                )

                if msg_type == TYPE_OPEN:
                    self.handle_remote_open(
                        sid,
                        data,
                    )
                elif msg_type == TYPE_DATA:
                    remote = self.remote_sockets.get(
                        sid
                    )
                    if remote:
                        remote.sendall(
                            data
                        )
                        continue

                    client = self.local_clients.get(
                        sid
                    )
                    if client:
                        client.sendall(
                            data
                        )
                elif msg_type == TYPE_CLOSE:
                    remote = self.remote_sockets.pop(
                        sid,
                        None,
                    )
                    if remote:
                        close_socket(remote)

                    client = self.local_clients.pop(
                        sid,
                        None,
                    )
                    if client:
                        close_socket(client)
        except Exception as e:
            print(
                "tunnel error",
                e,
            )
        finally:
            self.clear_tunnel(
                tunnel
            )
            close_socket(
                tunnel
            )
            print(
                "tunnel closed"
            )

    def handle_remote_open(self, sid, data):
        try:
            host, port = self.parse_open_target(
                data
            )

            if self.allow_targets and (host, port) not in self.allow_targets:
                raise PermissionError(
                    f"target not allowed: {host}:{port}"
                )

            remote = socket.socket()
            remote.settimeout(
                10
            )
            remote.connect(
                (
                    host,
                    port,
                )
            )
            remote.settimeout(
                None
            )

            self.remote_sockets[sid] = remote

            print(
                "target connected",
                sid,
                host,
                port,
            )

            threading.Thread(
                target=self.remote_reader,
                args=(
                    sid,
                    remote,
                ),
                daemon=True,
            ).start()
        except Exception as e:
            print(
                "target connect failed",
                sid,
                e,
            )
            try:
                self.safe_send(
                    TYPE_CLOSE,
                    sid,
                    str(e).encode(),
                )
            except Exception:
                pass

    def remote_reader(self, sid, remote):
        try:
            while True:
                data = remote.recv(
                    4096
                )

                if not data:
                    break

                self.safe_send(
                    TYPE_DATA,
                    sid,
                    data,
                )
        except Exception as e:
            print(
                "target reader error",
                sid,
                e,
            )
        finally:
            self.remote_sockets.pop(
                sid,
                None,
            )
            close_socket(
                remote
            )
            try:
                self.safe_send(
                    TYPE_CLOSE,
                    sid,
                )
            except Exception:
                pass

    def open_tunnel_stream(self, client, target_host, target_port):
        sid = self.next_local_stream()
        self.local_clients[sid] = client

        try:
            self.safe_send(
                TYPE_OPEN,
                sid,
                self.encode_open_target(
                    target_host,
                    target_port,
                ),
            )

            while True:
                data = client.recv(
                    4096
                )

                if not data:
                    break

                self.safe_send(
                    TYPE_DATA,
                    sid,
                    data,
                )
        except Exception as e:
            print(
                "local stream error",
                sid,
                e,
            )
        finally:
            self.local_clients.pop(
                sid,
                None,
            )
            try:
                self.safe_send(
                    TYPE_CLOSE,
                    sid,
                )
            except Exception:
                pass
            close_socket(
                client
            )

    def handle_public_socks_client(self, client):
        target = None

        try:
            target = handle_socks5(
                client
            )

            if not target:
                return

            host, port = target

            if self.tunnel_listen and (host, port) == self.tunnel_listen:
                tunnel = socket.socket()
                tunnel.connect(
                    self.tunnel_listen
                )
                send_socks5_reply(
                    client,
                    True,
                )

                threading.Thread(
                    target=relay_socket,
                    args=(
                        tunnel,
                        client,
                    ),
                    daemon=True,
                ).start()
                relay_socket(
                    client,
                    tunnel,
                )
                return

            try:
                send_socks5_reply(
                    client,
                    True,
                )
                self.open_tunnel_stream(
                    client,
                    target[0],
                    target[1],
                )
            except Exception as e:
                print(
                    "public socks stream error",
                    target,
                    e,
                )
                close_socket(
                    client
                )
        except Exception as e:
            print(
                "public socks error",
                target,
                e,
            )
            close_socket(
                client
            )

    def serve_public_socks(self):
        if self.socks_listen is None:
            return

        server = socket.socket()
        server.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )
        server.bind(
            self.socks_listen
        )
        server.listen(
            100
        )
        server.settimeout(
            1
        )

        print(
            "socks listen",
            f"{self.socks_listen[0]}:{self.socks_listen[1]}",
        )

        try:
            while True:
                try:
                    client, _ = server.accept()
                except socket.timeout:
                    continue

                threading.Thread(
                    target=self.handle_public_socks_client,
                    args=(client,),
                    daemon=True,
                ).start()
        finally:
            close_socket(
                server
            )

    def serve_tunnel(self):
        if self.tunnel_listen is None:
            return

        server = socket.socket()
        server.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )
        server.bind(
            self.tunnel_listen
        )
        server.listen(
            10
        )
        server.settimeout(
            1
        )

        print(
            "tunnel listen",
            f"{self.tunnel_listen[0]}:{self.tunnel_listen[1]}",
        )

        try:
            while True:
                try:
                    tunnel, _ = server.accept()
                except socket.timeout:
                    continue

                threading.Thread(
                    target=self.tunnel_reader,
                    args=(tunnel,),
                    daemon=True,
                ).start()
        finally:
            close_socket(
                server
            )

    def connect_peer(self):
        if self.connect_socks is None:
            return

        if self.connect_target is None:
            raise ValueError(
                "connect_target is required when connect_socks is set"
            )

        tunnel = socket.socket()
        tunnel.connect(
            self.connect_socks
        )
        connect_through_socks5(
            tunnel,
            self.connect_target[0],
            self.connect_target[1],
        )

        threading.Thread(
            target=self.tunnel_reader,
            args=(tunnel,),
            daemon=True,
        ).start()

    def serve_forward(self, listen_host, listen_port, target_host, target_port):
        server = socket.socket()
        server.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )
        server.bind(
            (
                listen_host,
                listen_port,
            )
        )
        server.listen(
            100
        )
        server.settimeout(
            1
        )

        print(
            "forward listen",
            f"{listen_host}:{listen_port}",
            "->",
            f"{target_host}:{target_port}",
        )

        try:
            while True:
                try:
                    client, _ = server.accept()
                except socket.timeout:
                    continue

                threading.Thread(
                    target=self.open_tunnel_stream,
                    args=(
                        client,
                        target_host,
                        target_port,
                    ),
                    daemon=True,
                ).start()
        finally:
            close_socket(
                server
            )

    def serve(self):
        if self.tunnel_listen:
            threading.Thread(
                target=self.serve_tunnel,
                daemon=True,
            ).start()

        if self.socks_listen:
            threading.Thread(
                target=self.serve_public_socks,
                daemon=True,
            ).start()

        for mapping in self.forwards:
            threading.Thread(
                target=self.serve_forward,
                args=mapping,
                daemon=True,
            ).start()

        self.connect_peer()

        print(
            "node started"
        )

        try:
            while True:
                threading.Event().wait(
                    1
                )
        except KeyboardInterrupt:
            print(
                "node shutting down"
            )


def run_node(
    socks_listen=None,
    tunnel_listen=None,
    connect_socks=None,
    connect_target=None,
    forwards=None,
    allow_targets=None,
):
    node = TunnelNode(
        socks_listen=socks_listen,
        tunnel_listen=tunnel_listen,
        connect_socks=connect_socks,
        connect_target=connect_target,
        forwards=forwards,
        allow_targets=allow_targets,
    )
    node.serve()
