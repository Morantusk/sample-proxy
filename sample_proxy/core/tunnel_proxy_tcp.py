import socket
import threading
import uuid

from sample_proxy.core.protocol import *


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


class TcpTunnelProxy:
    def __init__(
        self,
        gateway,
        listen_host,
        listen_port,
        target_host,
        target_port,
    ):
        self.gateway = gateway
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self.tunnel = socket.socket()
        self.tunnel_id = str(
            uuid.uuid4()
        )
        self.send_lock = threading.Lock()
        self.stream_lock = threading.Lock()
        self.stream_id = -1
        self.clients = {}

    def next_stream_id(self):
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

    def tunnel_reader(self):
        while True:
            packet = recv_packet(
                self.tunnel
            )

            if not packet:
                break

            msg_type, sid, data = packet

            print(
                "proxy recv:",
                msg_type,
                sid,
                len(data),
            )

            client = self.clients.get(
                sid
            )

            if msg_type == TYPE_DATA:
                if client:
                    client.sendall(
                        data
                    )
            elif msg_type == TYPE_CLOSE:
                if client:
                    close_socket(client)
                self.clients.pop(
                    sid,
                    None,
                )

    def handle_client(self, client):
        sid = self.next_stream_id()
        self.clients[sid] = client

        print(
            "new stream:",
            sid,
        )

        open_data = (
            f"{self.tunnel_id}|{self.target_host}:{self.target_port}"
        ).encode()

        self.safe_send(
            TYPE_OPEN,
            sid,
            open_data,
        )

        try:
            while True:
                data = client.recv(
                    4096
                )

                if not data:
                    break

                print(
                    "client->tunnel",
                    sid,
                    len(data),
                )

                self.safe_send(
                    TYPE_DATA,
                    sid,
                    data,
                )
        finally:
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
        self.tunnel.connect(
            self.gateway
        )

        print(
            "tunnel connected"
        )
        print(
            "tunnel id:",
            self.tunnel_id,
        )

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
            10
        )
        server.settimeout(
            1
        )

        print(
            "proxy listen",
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
                    "client connect:",
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


def run_tcp_proxy(
    gateway,
    listen_host="127.0.0.1",
    listen_port=8000,
    target_host="127.0.0.1",
    target_port=9000,
):
    proxy = TcpTunnelProxy(
        gateway=gateway,
        listen_host=listen_host,
        listen_port=listen_port,
        target_host=target_host,
        target_port=target_port,
    )
    proxy.serve()


if __name__ == "__main__":
    run_tcp_proxy(
        gateway=(
            "127.0.0.1",
            7000,
        ),
        target_host="127.0.0.1",
        target_port=9000,
    )
