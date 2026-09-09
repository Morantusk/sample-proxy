import unittest

from sample_proxy.core.protocol import (
    TYPE_AUTH,
    TYPE_AUTH_CHALLENGE,
    TYPE_AUTH_OK,
    TYPE_OPEN,
    recv_packet,
    send_packet,
)
from sample_proxy.core.tunnel_node import TunnelNode
from sample_proxy.core.tunnel_session import TunnelSession


class FakeSocket:
    def __init__(self, received=b""):
        self.received = received
        self.sent = b""

    def recv(self, size):
        data = self.received[:size]
        self.received = self.received[size:]
        return data

    def sendall(self, data):
        self.sent += data


class TunnelSessionTests(unittest.TestCase):
    def test_safe_send_writes_packet_to_active_tunnel(self):
        session = TunnelSession()
        tunnel = FakeSocket()
        session.set_tunnel(tunnel)

        session.safe_send(
            TYPE_OPEN,
            1,
            b"pipe-test",
        )

        self.assertGreater(
            len(tunnel.sent),
            9,
        )

    def test_connect_peer_requires_token(self):
        session = TunnelSession()

        with self.assertRaisesRegex(
            ValueError,
            "token is required",
        ):
            session.connect_peer_once(
                ("127.0.0.1", 7123),
                ("pipe", 1),
            )

    def test_node_validates_missing_token_before_starting(self):
        node = TunnelNode(
            socks_listen=("127.0.0.1", 1080),
            connect_socks=("127.0.0.1", 7123),
            connect_target=("pipe", 1),
        )

        with self.assertRaisesRegex(
            ValueError,
            "token is required",
        ):
            node.validate_config()

    def test_node_requires_token_for_tunnel_pipe(self):
        node = TunnelNode(
            socks_listen=("0.0.0.0", 7123),
            tunnel_pipe=("pipe", 1),
        )

        with self.assertRaisesRegex(
            ValueError,
            "token is required",
        ):
            node.validate_config()

    def test_outgoing_auth_uses_hmac_digest_not_raw_token(self):
        token = "very-secret-token"
        challenge = b"challenge-bytes"
        received = FakeSocket()
        send_packet(
            received,
            TYPE_AUTH_CHALLENGE,
            0,
            challenge,
        )
        send_packet(
            received,
            TYPE_AUTH_OK,
            0,
        )

        session = TunnelSession(
            token=token
        )
        sock = FakeSocket(
            received.sent
        )

        session.authenticate_outgoing(
            sock
        )

        self.assertNotIn(
            token.encode(),
            sock.sent,
        )

        msg_type, sid, data = recv_packet(
            FakeSocket(sock.sent)
        )

        self.assertEqual(
            msg_type,
            TYPE_AUTH,
        )
        self.assertEqual(
            sid,
            0,
        )
        self.assertEqual(
            data,
            session.auth_digest(challenge),
        )


if __name__ == "__main__":
    unittest.main()
