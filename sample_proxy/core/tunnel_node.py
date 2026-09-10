import asyncio

from sample_proxy.core.admin import start_admin
from sample_proxy.core.listeners import (
    start_forward,
    start_public_socks,
    start_tunnel,
)
from sample_proxy.core.tunnel_session import TunnelSession


class TunnelNode:
    def __init__(
        self,
        socks_listen=None,
        tunnel_listen=None,
        tunnel_pipe=None,
        connect_socks=None,
        connect_target=None,
        forwards=None,
        allow_targets=None,
        token=None,
        tunnel_pool_size=1,
        ping_interval=30,
        pong_timeout=15,
        admin_listen=None,
    ):
        self.socks_listen = socks_listen
        self.tunnel_listen = tunnel_listen
        self.tunnel_pipe = tunnel_pipe
        self.connect_socks = connect_socks
        self.connect_target = connect_target
        self.forwards = forwards or []
        self.tunnel_pool_size = tunnel_pool_size
        self.admin_listen = admin_listen
        self.session = TunnelSession(
            allow_targets=allow_targets,
            local_stream_starts_odd=connect_socks is not None,
            token=token,
            ping_interval=ping_interval,
            pong_timeout=pong_timeout,
        )
        self.servers = []
        self.tasks = []

    def validate_config(self):
        if self.connect_socks and not self.connect_target:
            raise ValueError(
                "connect_target is required when connect_socks is set"
            )

        if self.connect_socks and not self.session.token:
            raise ValueError(
                "token is required when connect_socks is set; use --token-file or SAMPLE_PROXY_TOKEN"
            )

        if self.tunnel_pipe and not self.session.token:
            raise ValueError(
                "token is required when tunnel_pipe is set; use --token-file or SAMPLE_PROXY_TOKEN"
            )

        if self.tunnel_pool_size < 1:
            raise ValueError(
                "tunnel_pool_size must be at least 1"
            )

    async def serve_async(self):
        self.validate_config()

        tunnel_server = await start_tunnel(
            self.session,
            self.tunnel_listen,
        )
        if tunnel_server:
            self.servers.append(
                tunnel_server
            )

        socks_server = await start_public_socks(
            self.session,
            self.socks_listen,
            self.tunnel_listen,
            self.tunnel_pipe,
        )
        if socks_server:
            self.servers.append(
                socks_server
            )

        for mapping in self.forwards:
            server = await start_forward(
                self.session,
                *mapping,
            )
            self.servers.append(
                server
            )

        admin_server = await start_admin(
            self.session,
            self.admin_listen,
        )
        if admin_server:
            self.servers.append(
                admin_server
            )

        if self.connect_socks:
            for _ in range(self.tunnel_pool_size):
                self.tasks.append(
                    asyncio.create_task(
                        self.session.connect_peer_loop(
                            self.connect_socks,
                            self.connect_target,
                        )
                    )
                )

        print(
            "node started"
        )

        await asyncio.Event().wait()

    def serve(self):
        try:
            asyncio.run(
                self.serve_async()
            )
        except KeyboardInterrupt:
            print(
                "node shutting down"
            )


def run_node(
    socks_listen=None,
    tunnel_listen=None,
    tunnel_pipe=None,
    connect_socks=None,
    connect_target=None,
    forwards=None,
    allow_targets=None,
    token=None,
    tunnel_pool_size=1,
    ping_interval=30,
    pong_timeout=15,
    admin_listen=None,
):
    node = TunnelNode(
        socks_listen=socks_listen,
        tunnel_listen=tunnel_listen,
        tunnel_pipe=tunnel_pipe,
        connect_socks=connect_socks,
        connect_target=connect_target,
        forwards=forwards,
        allow_targets=allow_targets,
        token=token,
        tunnel_pool_size=tunnel_pool_size,
        ping_interval=ping_interval,
        pong_timeout=pong_timeout,
        admin_listen=admin_listen,
    )
    node.serve()
