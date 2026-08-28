import struct

TYPE_OPEN = 1
TYPE_DATA = 2
TYPE_CLOSE = 3

HEADER_SIZE = 9


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


def send_packet(
        sock,
        msg_type,
        stream_id,
        payload=b""
):
    header = struct.pack(
        "!BII",
        msg_type,
        stream_id,
        len(payload)
    )

    sock.sendall(
        header + payload
    )


def recv_packet(sock):
    header = recv_exact(
        sock,
        HEADER_SIZE
    )

    if not header:
        return None

    msg_type, stream_id, length = struct.unpack(
        "!BII",
        header
    )

    payload = recv_exact(
        sock,
        length
    )

    return (
        msg_type,
        stream_id,
        payload
    )
