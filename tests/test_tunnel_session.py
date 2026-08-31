import unittest

from sample_proxy.core.protocol import TYPE_OPEN
from sample_proxy.core.tunnel_node import TunnelNode
from sample_proxy.core.tunnel_session import TunnelSession


class FakeSocket:
    def __init__(self):
        self.sent = b""

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


if __name__ == "__main__":
    unittest.main()
