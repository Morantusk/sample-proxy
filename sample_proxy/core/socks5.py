import socket


def recv_exact(sock, size):
    data = b""

    while len(data) < size:

        chunk = sock.recv(
            size - len(data)
        )

        if not chunk:
            return None

        data += chunk

    return data


def handle_socks5(client):
    # greeting

    header = recv_exact(
        client,
        2
    )

    if not header:
        return None

    version, nmethods = header

    recv_exact(
        client,
        nmethods
    )

    # no auth

    client.sendall(
        b"\x05\x00"
    )

    # connect request

    req = recv_exact(
        client,
        4
    )

    ver, cmd, _, atyp = req

    if cmd != 1:
        raise Exception(
            "only connect"
        )

    if atyp == 1:

        host = socket.inet_ntoa(
            recv_exact(
                client,
                4
            )
        )


    elif atyp == 3:

        length = recv_exact(
            client,
            1
        )[0]

        host = recv_exact(
            client,
            length
        ).decode()


    else:

        raise Exception(
            "unsupported"
        )

    port = int.from_bytes(
        recv_exact(
            client,
            2
        ),
        "big"
    )

    print(
        "SOCKS5 CONNECT",
        host,
        port
    )

    return host, port
