import socket
import threading
import uuid

from sample_proxy.core.protocol import *
from sample_proxy.core.socks5 import handle_socks5


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


def parse_target(data):
    host, port = data.decode().rsplit(
        ":",
        1,
    )
    return host, int(port)


class SocksTunnelProxy:
    def __init__(self, gateway, listen_host, listen_port, allow_targets=None):
        self.gateway = gateway
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.allow_targets = allow_targets or set()
        self.tunnel = socket.socket()
        self.tunnel_id = str(
            uuid.uuid4()
        )
        self.send_lock = threading.Lock()
        self.stream_lock = threading.Lock()
        self.stream_id = -1
        self.clients = {}
        self.reverse_remotes = {}

    def next_stream(self):
        with self.stream_lock:
            self.stream_id += 2
            return self.stream_id

    def safe_send(self, msg_type, sid, data=b""):
        with self.send_lock:
            send_packet(
                self.tunnel,
                msg_type,
                sid,
                data,
            )

    def connect(self):
        self.tunnel.connect(
            self.gateway
        )

        print(
            "tunnel connected"
        )
        print(
            "tunnel id",
            self.tunnel_id,
        )

    def tunnel_reader(self):
        while True:
            packet = recv_packet(
                self.tunnel
            )

            if not packet:
                break

            msg_type, sid, data = packet

            print(
                "proxy recv",
                msg_type,
                sid,
                len(data),
            )

            if msg_type == TYPE_OPEN:
                self.handle_reverse_open(
                    sid,
                    data,
                )
            elif msg_type == TYPE_DATA:
                if sid % 2 == 0:
                    remote = self.reverse_remotes.get(
                        sid
                    )
                    if remote:
                        remote.sendall(
                            data
                        )
                else:
                    client = self.clients.get(
                        sid
                    )
                    if client:
                        client.sendall(
                            data
                        )
            elif msg_type == TYPE_CLOSE:
                if sid % 2 == 0:
                    remote = self.reverse_remotes.pop(
                        sid,
                        None,
                    )
                    if remote:
                        close_socket(remote)
                else:
                    client = self.clients.pop(
                        sid,
                        None,
                    )
                    if client:
                        close_socket(client)

    def handle_reverse_open(self, sid, data):
        try:
            host, port = parse_target(data)

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

            self.reverse_remotes[sid] = remote

            print(
                "reverse connected",
                sid,
                host,
                port,
            )

            threading.Thread(
                target=self.reverse_remote_reader,
                args=(
                    sid,
                    remote,
                ),
                daemon=True,
            ).start()
        except Exception as e:
            print(
                "reverse connect failed",
                sid,
                e,
            )
            self.safe_send(
                TYPE_CLOSE,
                sid,
                str(e).encode(),
            )

    def reverse_remote_reader(self, sid, remote):
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
                "reverse remote error",
                sid,
                e,
            )
        finally:
            self.reverse_remotes.pop(
                sid,
                None,
            )
            close_socket(remote)
            self.safe_send(
                TYPE_CLOSE,
                sid,
            )

    def handle_client(self, client):
        sid = self.next_stream()
        self.clients[sid] = client

        try:
            target = handle_socks5(
                client
            )

            if not target:
                return

            host, port = target

            client.sendall(
                b"\x05\x00\x00\x01"
                b"\x00\x00\x00\x00"
                b"\x00\x00"
            )

            open_data = (
                f"{self.tunnel_id}|{host}:{port}"
            ).encode()

            self.safe_send(
                TYPE_OPEN,
                sid,
                open_data,
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
                "client error",
                e,
            )
        finally:
            print(
                "close client stream",
                sid,
            )

            if sid in self.clients:
                self.safe_send(
                    TYPE_CLOSE,
                    sid,
                )
                self.clients.pop(
                    sid,
                    None,
                )

            close_socket(client)

    def serve(self):
        self.connect()

        threading.Thread(
            target=self.tunnel_reader,
            daemon=True,
        ).start()

        server = socket.socket()
        server.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )
        server.bind(
            (
                self.listen_host,
                self.listen_port,
            )
        )
        server.listen(
            100
        )
        server.settimeout(
            1
        )

        print(
            "SOCKS5 listen",
            self.listen_host,
            self.listen_port,
        )

        try:
            while True:
                try:
                    client, addr = server.accept()
                except socket.timeout:
                    continue

                print(
                    "client",
                    addr,
                )

                threading.Thread(
                    target=self.handle_client,
                    args=(client,),
                    daemon=True,
                ).start()
        except KeyboardInterrupt:
            print(
                "proxy shutting down"
            )
        finally:
            close_socket(server)
            close_socket(self.tunnel)


def run_socks_proxy(
    gateway,
    listen_host="127.0.0.1",
    listen_port=1080,
    allow_targets=None,
):
    proxy = SocksTunnelProxy(
        gateway=gateway,
        listen_host=listen_host,
        listen_port=listen_port,
        allow_targets=allow_targets,
    )
    proxy.serve()


if __name__ == "__main__":
    run_socks_proxy(
        gateway=(
            "127.0.0.1",
            7000,
        )
    )
