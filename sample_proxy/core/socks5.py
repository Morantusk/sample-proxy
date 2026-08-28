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


def send_socks5_reply(client, success):
    status = b"\x00" if success else b"\x01"
    client.sendall(
        b"\x05"
        + status
        + b"\x00\x01"
        + b"\x00\x00\x00\x00"
        + b"\x00\x00"
    )


def connect_through_socks5(sock, target_host, target_port):
    sock.sendall(
        b"\x05\x01\x00"
    )

    response = recv_exact(
        sock,
        2,
    )

    if response != b"\x05\x00":
        raise ConnectionError(
            "SOCKS5 server rejected no-auth method"
        )

    try:
        address = socket.inet_aton(
            target_host
        )
        request = (
            b"\x05\x01\x00\x01"
            + address
            + target_port.to_bytes(
                2,
                "big",
            )
        )
    except OSError:
        encoded_host = target_host.encode()
        if len(encoded_host) > 255:
            raise ValueError(
                "SOCKS5 domain is too long"
            )

        request = (
            b"\x05\x01\x00\x03"
            + bytes(
                [len(encoded_host)]
            )
            + encoded_host
            + target_port.to_bytes(
                2,
                "big",
            )
        )

    sock.sendall(
        request
    )

    header = recv_exact(
        sock,
        4,
    )

    if not header:
        raise ConnectionError(
            "SOCKS5 server closed during CONNECT"
        )

    version, status, _, atyp = header

    if version != 5 or status != 0:
        raise ConnectionError(
            f"SOCKS5 CONNECT failed with status {status}"
        )

    if atyp == 1:
        recv_exact(
            sock,
            4,
        )
    elif atyp == 3:
        length = recv_exact(
            sock,
            1,
        )[0]
        recv_exact(
            sock,
            length,
        )
    elif atyp == 4:
        recv_exact(
            sock,
            16,
        )
    else:
        raise ConnectionError(
            "SOCKS5 server returned unsupported address type"
        )

    recv_exact(
        sock,
        2,
    )
