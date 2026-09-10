import asyncio
import json
import unittest

from sample_proxy.core.admin import start_admin
from sample_proxy.core.tunnel_session import TunnelSession


class AdminTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_reports_tunnel_state(self):
        session = TunnelSession()
        server = await start_admin(
            session,
            ("127.0.0.1", 0),
        )
        port = server.sockets[0].getsockname()[1]

        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            port,
        )
        writer.write(
            b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n"
        )
        await writer.drain()
        response = await reader.read()

        writer.close()
        await writer.wait_closed()
        server.close()
        await server.wait_closed()

        _, body = response.split(
            b"\r\n\r\n",
            1,
        )
        data = json.loads(
            body.decode()
        )

        self.assertFalse(
            data["ok"]
        )
        self.assertEqual(
            data["ready_tunnels"],
            0,
        )
