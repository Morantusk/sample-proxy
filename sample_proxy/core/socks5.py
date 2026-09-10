import asyncio
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


async def async_recv_exact(reader, size):
    try:
        return await reader.readexactly(size)
    except asyncio.IncompleteReadError:
        return None


async def async_handle_socks5(reader, writer):
    header = await async_recv_exact(
        reader,
        2
    )

    if not header:
        return None

    version, nmethods = header

    if version != 5:
        raise Exception(
            "unsupported socks version"
        )

    methods = await async_recv_exact(
        reader,
        nmethods
    )

    if methods is None:
        return None

    writer.write(
        b"\x05\x00"
    )
    await writer.drain()

    req = await async_recv_exact(
        reader,
        4
    )

    if not req:
        return None

    ver, cmd, _, atyp = req

    if ver != 5 or cmd != 1:
        raise Exception(
            "only connect"
        )

    if atyp == 1:
        address = await async_recv_exact(
            reader,
            4
        )
        if address is None:
            return None
        host = socket.inet_ntoa(
            address
        )
    elif atyp == 3:
        length = await async_recv_exact(
            reader,
            1
        )
        if length is None:
            return None
        host_data = await async_recv_exact(
            reader,
            length[0]
        )
        if host_data is None:
            return None
        host = host_data.decode()
    else:
        raise Exception(
            "unsupported"
        )

    port_data = await async_recv_exact(
        reader,
        2
    )

    if port_data is None:
        return None

    port = int.from_bytes(
        port_data,
        "big"
    )

    print(
        "SOCKS5 CONNECT",
        host,
        port
    )

    return host, port


async def async_send_socks5_reply(writer, success):
    status = b"\x00" if success else b"\x01"
    writer.write(
        b"\x05"
        + status
        + b"\x00\x01"
        + b"\x00\x00\x00\x00"
        + b"\x00\x00"
    )
    await writer.drain()


async def async_connect_through_socks5(reader, writer, target_host, target_port):
    writer.write(
        b"\x05\x01\x00"
    )
    await writer.drain()

    response = await async_recv_exact(
        reader,
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

    writer.write(
        request
    )
    await writer.drain()

    header = await async_recv_exact(
        reader,
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
        await async_recv_exact(
            reader,
            4,
        )
    elif atyp == 3:
        length = await async_recv_exact(
            reader,
            1,
        )
        if length is None:
            return
        await async_recv_exact(
            reader,
            length[0],
        )
    elif atyp == 4:
        await async_recv_exact(
            reader,
            16,
        )
    else:
        raise ConnectionError(
            "SOCKS5 server returned unsupported address type"
        )

    await async_recv_exact(
        reader,
        2,
    )
