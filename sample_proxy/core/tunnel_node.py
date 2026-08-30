import threading

from sample_proxy.core.listeners import (
    serve_forward,
    serve_public_socks,
    serve_tunnel,
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
    ):
        self.socks_listen = socks_listen
        self.tunnel_listen = tunnel_listen
        self.tunnel_pipe = tunnel_pipe
        self.connect_socks = connect_socks
        self.connect_target = connect_target
        self.forwards = forwards or []
        self.session = TunnelSession(
            allow_targets=allow_targets,
            local_stream_starts_odd=connect_socks is not None,
        )

    def serve(self):
        if self.tunnel_listen:
            threading.Thread(
                target=serve_tunnel,
                args=(
                    self.session,
                    self.tunnel_listen,
                ),
                daemon=True,
            ).start()

        if self.socks_listen:
            threading.Thread(
                target=serve_public_socks,
                args=(
                    self.session,
                    self.socks_listen,
                    self.tunnel_listen,
                    self.tunnel_pipe,
                ),
                daemon=True,
            ).start()

        for mapping in self.forwards:
            threading.Thread(
                target=serve_forward,
                args=(
                    self.session,
                    *mapping,
                ),
                daemon=True,
            ).start()

        self.session.connect_peer(
            self.connect_socks,
            self.connect_target,
        )

        print(
            "node started"
        )

        try:
            while True:
                threading.Event().wait(
                    1
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
):
    node = TunnelNode(
        socks_listen=socks_listen,
        tunnel_listen=tunnel_listen,
        tunnel_pipe=tunnel_pipe,
        connect_socks=connect_socks,
        connect_target=connect_target,
        forwards=forwards,
        allow_targets=allow_targets,
    )
    node.serve()
