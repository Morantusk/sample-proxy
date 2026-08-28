import socket


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


def relay_socket(left, right):
    try:
        while True:
            data = left.recv(
                4096
            )

            if not data:
                break

            right.sendall(
                data
            )
    finally:
        close_socket(left)
        close_socket(right)
