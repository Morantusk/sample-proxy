import hmac
import socket
import threading
import time
import uuid

from sample_proxy.core.protocol import *
from sample_proxy.core.socket_utils import close_socket
from sample_proxy.core.socks5 import connect_through_socks5


PING_INTERVAL = 30


class TunnelSession:
    def __init__(
        self,
        allow_targets=None,
        local_stream_starts_odd=False,
        token=None,
    ):
        self.allow_targets = allow_targets or set()
        self.token = token
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

    def socket_name(self, sock):
        try:
            local = sock.getsockname()
            remote = sock.getpeername()
            return f"local={local[0]}:{local[1]} remote={remote[0]}:{remote[1]}"
        except Exception:
            return "local=? remote=?"

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

        self.send_to_tunnel(
            tunnel,
            msg_type,
            sid,
            data,
        )

    def send_to_tunnel(self, tunnel, msg_type, sid, data=b""):
        with self.send_lock:
            send_packet(
                tunnel,
                msg_type,
                sid,
                data,
            )

    def authenticate_incoming(self, tunnel):
        if not self.token:
            print(
                "auth disabled"
            )
            return True

        packet = recv_packet(
            tunnel
        )

        if not packet:
            print(
                "auth failed: peer closed before auth"
            )
            return False

        msg_type, sid, data = packet

        if msg_type != TYPE_AUTH:
            print(
                "auth failed: first packet is not AUTH",
                msg_type,
                sid,
            )
            self.send_to_tunnel(
                tunnel,
                TYPE_AUTH_FAIL,
                0,
            )
            return False

        ok = hmac.compare_digest(
            data.decode(errors="ignore"),
            self.token,
        )

        if not ok:
            print(
                "auth failed: token mismatch"
            )
            self.send_to_tunnel(
                tunnel,
                TYPE_AUTH_FAIL,
                0,
            )
            return False

        self.send_to_tunnel(
            tunnel,
            TYPE_AUTH_OK,
            0,
        )
        print(
            "auth ok"
        )
        return True

    def authenticate_outgoing(self, tunnel):
        if not self.token:
            print(
                "auth disabled"
            )
            return

        self.send_to_tunnel(
            tunnel,
            TYPE_AUTH,
            0,
            self.token.encode(),
        )

        packet = recv_packet(
            tunnel
        )

        if not packet:
            raise ConnectionError(
                "peer closed before auth response"
            )

        msg_type, _, data = packet

        if msg_type != TYPE_AUTH_OK:
            detail = data.decode(errors="ignore") if data else ""
            raise PermissionError(
                f"auth rejected: {detail}"
            )

        print(
            "auth ok"
        )

    def start_ping_loop(self, tunnel):
        threading.Thread(
            target=self.ping_loop,
            args=(tunnel,),
            daemon=True,
        ).start()

    def ping_loop(self, tunnel):
        while self.get_tunnel() is tunnel:
            time.sleep(
                PING_INTERVAL
            )

            if self.get_tunnel() is not tunnel:
                break

            try:
                self.send_to_tunnel(
                    tunnel,
                    TYPE_PING,
                    0,
                )
                print(
                    "ping sent"
                )
            except Exception as e:
                print(
                    "ping failed",
                    e,
                )
                close_socket(
                    tunnel
                )
                break

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

    def tunnel_reader(self, tunnel, authenticated=False):
        if not authenticated and not self.authenticate_incoming(tunnel):
            close_socket(
                tunnel
            )
            return

        self.set_tunnel(
            tunnel
        )

        print(
            "tunnel connected",
            self.socket_name(tunnel),
        )
        self.start_ping_loop(
            tunnel
        )

        try:
            while True:
                packet = recv_packet(
                    tunnel
                )

                if not packet:
                    print(
                        "tunnel peer closed",
                        self.socket_name(tunnel),
                    )
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
                elif msg_type == TYPE_PING:
                    self.send_to_tunnel(
                        tunnel,
                        TYPE_PONG,
                        0,
                    )
                    print(
                        "pong sent"
                    )
                elif msg_type == TYPE_PONG:
                    print(
                        "pong recv"
                    )
        except Exception as e:
            print(
                "tunnel error",
                self.socket_name(tunnel),
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
                "tunnel closed",
                self.socket_name(tunnel),
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

        if not self.token:
            raise ValueError(
                "token is required when connect_socks is set; use --token-file or SAMPLE_PROXY_TOKEN"
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
        print(
            "socks connect ok",
            self.socket_name(tunnel),
        )
        self.authenticate_outgoing(
            tunnel
        )

        self.tunnel_reader(
            tunnel,
            authenticated=True,
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
            except ValueError as e:
                print(
                    "connect peer config error",
                    e,
                )
                return
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
