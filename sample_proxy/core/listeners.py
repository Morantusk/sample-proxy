import socket
import threading

from sample_proxy.core.socket_utils import close_socket, relay_socket
from sample_proxy.core.socks5 import handle_socks5, send_socks5_reply


def serve_public_socks(session, socks_listen, tunnel_listen=None):
    if socks_listen is None:
        return

    server = socket.socket()
    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )
    server.bind(
        socks_listen
    )
    server.listen(
        100
    )
    server.settimeout(
        1
    )

    print(
        "socks listen",
        f"{socks_listen[0]}:{socks_listen[1]}",
    )

    try:
        while True:
            try:
                client, _ = server.accept()
            except socket.timeout:
                continue

            threading.Thread(
                target=handle_public_socks_client,
                args=(
                    session,
                    client,
                    tunnel_listen,
                ),
                daemon=True,
            ).start()
    finally:
        close_socket(
            server
        )


def handle_public_socks_client(session, client, tunnel_listen=None):
    target = None

    try:
        target = handle_socks5(
            client
        )

        if not target:
            return

        host, port = target

        if tunnel_listen and (host, port) == tunnel_listen:
            tunnel = socket.socket()
            tunnel.connect(
                tunnel_listen
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

        send_socks5_reply(
            client,
            True,
        )
        session.open_stream(
            client,
            host,
            port,
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


def serve_tunnel(session, tunnel_listen):
    if tunnel_listen is None:
        return

    server = socket.socket()
    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )
    server.bind(
        tunnel_listen
    )
    server.listen(
        10
    )
    server.settimeout(
        1
    )

    print(
        "tunnel listen",
        f"{tunnel_listen[0]}:{tunnel_listen[1]}",
    )

    try:
        while True:
            try:
                tunnel, _ = server.accept()
            except socket.timeout:
                continue

            threading.Thread(
                target=session.tunnel_reader,
                args=(tunnel,),
                daemon=True,
            ).start()
    finally:
        close_socket(
            server
        )


def serve_forward(session, listen_host, listen_port, target_host, target_port):
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
                target=session.open_stream,
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
