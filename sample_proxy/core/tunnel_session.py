import socket
import threading
import time
import uuid

from sample_proxy.core.protocol import *
from sample_proxy.core.socket_utils import close_socket
from sample_proxy.core.socks5 import connect_through_socks5


class TunnelSession:
    def __init__(self, allow_targets=None, local_stream_starts_odd=False):
        self.allow_targets = allow_targets or set()
        self.node_id = str(
            uuid.uuid4()
        )
        self.send_lock = threading.Lock()
        self.local_stream_lock = threading.Lock()
        self.local_stream_id = -1 if local_stream_starts_odd else 0
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

    def has_tunnel(self):
        return self.get_tunnel() is not None

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
                    self.handle_data(
                        sid,
                        data,
                    )
                elif msg_type == TYPE_CLOSE:
                    self.close_stream(
                        sid
                    )
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

    def handle_data(self, sid, data):
        remote = self.remote_sockets.get(
            sid
        )
        if remote:
            remote.sendall(
                data
            )
            return

        client = self.local_clients.get(
            sid
        )
        if client:
            client.sendall(
                data
            )

    def close_stream(self, sid):
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

    def open_stream(self, client, target_host, target_port):
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

    def connect_peer_once(self, connect_socks, connect_target):
        if connect_socks is None:
            return

        if connect_target is None:
            raise ValueError(
                "connect_target is required when connect_socks is set"
            )

        tunnel = socket.socket()
        tunnel.connect(
            connect_socks
        )
        connect_through_socks5(
            tunnel,
            connect_target[0],
            connect_target[1],
        )

        self.tunnel_reader(
            tunnel
        )

    def connect_peer_loop(self, connect_socks, connect_target, retry_interval=3):
        if connect_socks is None:
            return

        while True:
            try:
                print(
                    "connect peer socks",
                    f"{connect_socks[0]}:{connect_socks[1]}",
                    "target",
                    f"{connect_target[0]}:{connect_target[1]}",
                )
                self.connect_peer_once(
                    connect_socks,
                    connect_target,
                )
            except Exception as e:
                print(
                    "connect peer failed",
                    e,
                )

            print(
                "reconnect peer after",
                retry_interval,
                "seconds",
            )
            time.sleep(
                retry_interval
            )
