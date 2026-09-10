import asyncio
import unittest

from sample_proxy.core.listeners import start_forward, start_public_socks
from sample_proxy.core.tunnel_session import TunnelSession


class AsyncTunnelTests(unittest.IsolatedAsyncioTestCase):
    async def test_tcp_forward_uses_active_tunnel(self):
        async def echo(reader, writer):
            try:
                data = await reader.read(
                    1024
                )
                writer.write(
                    data
                )
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        echo_server = await asyncio.start_server(
            echo,
            "127.0.0.1",
            0,
        )
        echo_port = echo_server.sockets[0].getsockname()[1]

        token = "integration-token"
        cloud_session = TunnelSession(
            allow_targets={("127.0.0.1", echo_port)},
            token=token,
        )
        cloud_socks = await start_public_socks(
            cloud_session,
            ("127.0.0.1", 0),
            tunnel_pipe=("pipe", 1),
        )
        cloud_port = cloud_socks.sockets[0].getsockname()[1]

        local_session = TunnelSession(
            local_stream_starts_odd=True,
            token=token,
        )
        connect_task = asyncio.create_task(
            local_session.connect_peer_loop(
                ("127.0.0.1", cloud_port),
                ("pipe", 1),
                retry_interval=0.1,
            )
        )

        for _ in range(20):
            if local_session.has_tunnel():
                break
            await asyncio.sleep(
                0.05
            )

        self.assertTrue(
            local_session.has_tunnel()
        )

        forward_server = await start_forward(
            local_session,
            "127.0.0.1",
            0,
            "127.0.0.1",
            echo_port,
        )
        forward_port = forward_server.sockets[0].getsockname()[1]

        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            forward_port,
        )
        writer.write(
            b"hello"
        )
        await writer.drain()

        self.assertEqual(
            await reader.readexactly(5),
            b"hello",
        )

        writer.close()
        await writer.wait_closed()
        connect_task.cancel()

        for server in (forward_server, cloud_socks, echo_server):
            server.close()
            await server.wait_closed()
