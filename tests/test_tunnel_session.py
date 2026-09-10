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


class FakeAsyncReader:
    def __init__(self, received=b""):
        self.received = received

    async def readexactly(self, size):
        if len(self.received) < size:
            raise EOFError()
        data = self.received[:size]
        self.received = self.received[size:]
        return data


class FakeAsyncWriter:
    def __init__(self):
        self.sent = b""
        self.closed = False

    def write(self, data):
        self.sent += data

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass

    def get_extra_info(self, name):
        if name == "sockname":
            return ("127.0.0.1", 10000)
        if name == "peername":
            return ("127.0.0.1", 10001)
        return None


class TunnelSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_send_writes_packet_to_active_tunnel(self):
        session = TunnelSession()
        reader = FakeAsyncReader()
        writer = FakeAsyncWriter()
        tunnel = session.add_tunnel(
            reader,
            writer,
        )
        session.set_tunnel_ready(
            tunnel
        )

        await session.safe_send(
            TYPE_OPEN,
            1,
            b"pipe-test",
        )

        self.assertGreater(
            len(writer.sent),
            9,
        )

    async def test_connect_peer_requires_token(self):
        session = TunnelSession()

        with self.assertRaisesRegex(
            ValueError,
            "token is required",
        ):
            await session.connect_peer_once(
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

    async def test_outgoing_auth_uses_hmac_digest_not_raw_token(self):
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
        reader = FakeAsyncReader(
            received.sent
        )
        writer = FakeAsyncWriter()

        await session.authenticate_outgoing(
            session.add_tunnel(
                reader,
                writer,
            )
        )

        self.assertNotIn(
            token.encode(),
            writer.sent,
        )

        msg_type, sid, data = recv_packet(
            FakeSocket(writer.sent)
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

    async def test_ready_tunnels_are_selected_round_robin(self):
        session = TunnelSession()
        first = session.add_tunnel(
            FakeAsyncReader(),
            FakeAsyncWriter(),
        )
        second = session.add_tunnel(
            FakeAsyncReader(),
            FakeAsyncWriter(),
        )
        session.set_tunnel_ready(first)
        session.set_tunnel_ready(second)

        self.assertIs(
            session.get_tunnel(),
            first,
        )
        self.assertIs(
            session.get_tunnel(),
            second,
        )
        self.assertIs(
            session.get_tunnel(),
            first,
        )

    async def test_ping_loop_closes_tunnel_after_pong_timeout(self):
        session = TunnelSession(
            ping_interval=0.01,
            pong_timeout=0.001,
        )
        writer = FakeAsyncWriter()
        tunnel = session.add_tunnel(
            FakeAsyncReader(),
            writer,
        )
        session.set_tunnel_ready(
            tunnel
        )

        await session.ping_loop(
            tunnel
        )

        self.assertEqual(
            tunnel.status,
            "dead",
        )
        self.assertTrue(
            writer.closed,
        )


if __name__ == "__main__":
    unittest.main()
