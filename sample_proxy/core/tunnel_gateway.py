import socket
import threading

from sample_proxy.core.protocol import *


active_tunnel = None
active_tunnel_lock = threading.Lock()
send_lock = threading.Lock()
reverse_lock = threading.Lock()
reverse_stream_id = 0
reverse_clients = {}


def next_reverse_stream_id():
    global reverse_stream_id

    with reverse_lock:
        reverse_stream_id += 2
        return reverse_stream_id


def safe_send(tunnel, msg_type, sid, data=b""):
    with send_lock:
        try:
            send_packet(
                tunnel,
                msg_type,
                sid,
                data,
            )
        except Exception as e:
            print(
                "send tunnel error",
                e,
            )


def parse_target(data):
    text = data.decode()
    if "|" in text:
        tunnel_id, target = text.split("|", 1)
    else:
        tunnel_id = None
        target = text

    host, port = target.rsplit(":", 1)
    return tunnel_id, host, int(port)


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


def remote_reader(tunnel, sid, remote, streams):
    try:
        while True:
            data = remote.recv(
                4096
            )

            if not data:
                break

            print(
                "remote->tunnel",
                sid,
                len(data),
            )

            safe_send(
                tunnel,
                TYPE_DATA,
                sid,
                data,
            )
    except (
        ConnectionResetError,
        ConnectionAbortedError,
    ):
        print(
            "remote closed",
            sid,
        )
    except Exception as e:
        print(
            "remote reader error",
            sid,
            e,
        )
    finally:
        streams.pop(
            sid,
            None,
        )
        close_socket(remote)
        safe_send(
            tunnel,
            TYPE_CLOSE,
            sid,
        )


def handle_proxy_open(tunnel, sid, data, streams):
    try:
        tunnel_id, host, port = parse_target(data)

        print(
            "connect target",
            tunnel_id,
            host,
            port,
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

        streams[sid] = remote

        print(
            "stream created",
            sid,
        )

        threading.Thread(
            target=remote_reader,
            args=(
                tunnel,
                sid,
                remote,
                streams,
            ),
            daemon=True,
        ).start()
    except Exception as e:
        print(
            "connect target failed",
            e,
        )
        safe_send(
            tunnel,
            TYPE_CLOSE,
            sid,
            str(e).encode(),
        )


def handle_tunnel(tunnel):
    streams = {}

    with active_tunnel_lock:
        global active_tunnel
        active_tunnel = tunnel

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
                "gateway recv",
                msg_type,
                sid,
                len(data),
            )

            if msg_type == TYPE_OPEN:
                handle_proxy_open(
                    tunnel,
                    sid,
                    data,
                    streams,
                )
            elif msg_type == TYPE_DATA:
                if sid % 2 == 0:
                    client = reverse_clients.get(
                        sid
                    )
                    if client:
                        client.sendall(
                            data
                        )
                else:
                    remote = streams.get(
                        sid
                    )
                    if remote:
                        remote.sendall(
                            data
                        )
            elif msg_type == TYPE_CLOSE:
                if sid % 2 == 0:
                    client = reverse_clients.pop(
                        sid,
                        None,
                    )
                    if client:
                        close_socket(client)
                else:
                    remote = streams.pop(
                        sid,
                        None,
                    )
                    if remote:
                        close_socket(remote)
    except Exception as e:
        print(
            "tunnel error",
            e,
        )
    finally:
        print(
            "cleanup tunnel"
        )

        with active_tunnel_lock:
            if active_tunnel is tunnel:
                active_tunnel = None

        for remote in list(streams.values()):
            close_socket(remote)
        streams.clear()


def reverse_client_reader(client, sid):
    try:
        while True:
            data = client.recv(
                4096
            )

            if not data:
                break

            with active_tunnel_lock:
                tunnel = active_tunnel

            if tunnel is None:
                break

            safe_send(
                tunnel,
                TYPE_DATA,
                sid,
                data,
            )
    except Exception as e:
        print(
            "reverse client error",
            sid,
            e,
        )
    finally:
        reverse_clients.pop(
            sid,
            None,
        )

        with active_tunnel_lock:
            tunnel = active_tunnel

        if tunnel:
            safe_send(
                tunnel,
                TYPE_CLOSE,
                sid,
            )

        close_socket(client)


def handle_reverse_client(client, target_host, target_port):
    with active_tunnel_lock:
        tunnel = active_tunnel

    if tunnel is None:
        print(
            "reverse rejected: no active tunnel"
        )
        close_socket(client)
        return

    sid = next_reverse_stream_id()
    reverse_clients[sid] = client

    open_data = (
        f"{target_host}:{target_port}"
    ).encode()

    print(
        "reverse open",
        sid,
        target_host,
        target_port,
    )

    safe_send(
        tunnel,
        TYPE_OPEN,
        sid,
        open_data,
    )

    reverse_client_reader(
        client,
        sid,
    )


def run_reverse_listener(listen_host, listen_port, target_host, target_port):
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
        "reverse listen",
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
                target=handle_reverse_client,
                args=(
                    client,
                    target_host,
                    target_port,
                ),
                daemon=True,
            ).start()
    finally:
        close_socket(server)


def run_gateway(host="0.0.0.0", port=7000, reverse_listens=None):
    reverse_listens = reverse_listens or []

    for mapping in reverse_listens:
        threading.Thread(
            target=run_reverse_listener,
            args=mapping,
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
            host,
            port,
        )
    )
    server.listen(
        10
    )
    server.settimeout(
        1
    )

    print(
        "gateway listen",
        port,
    )

    try:
        while True:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue

            threading.Thread(
                target=handle_tunnel,
                args=(conn,),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        print(
            "gateway shutting down"
        )
    finally:
        close_socket(server)


if __name__ == "__main__":
    run_gateway()
