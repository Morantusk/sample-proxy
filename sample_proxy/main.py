import argparse

from sample_proxy.core.tunnel_node import run_node


def parse_host_port(value):
    host, port = value.rsplit(":", 1)
    return host, int(port)


def parse_forward(value):
    listen, target = value.split("=", 1)
    listen_host, listen_port = parse_host_port(listen)
    target_host, target_port = parse_host_port(target)
    return listen_host, listen_port, target_host, target_port


def build_parser():
    parser = argparse.ArgumentParser(
        prog="sample-proxy",
        description="Run a unified SOCKS and tunnel proxy node.",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    node = subparsers.add_parser(
        "node",
        help="Run a unified node with public SOCKS, internal tunnel, peer connection, and local forwards.",
    )
    node.add_argument(
        "--socks-listen",
        type=parse_host_port,
        metavar="HOST:PORT",
        help="Public SOCKS5 listener.",
    )
    node.add_argument(
        "--tunnel-listen",
        type=parse_host_port,
        metavar="HOST:PORT",
        help="Internal raw tunnel listener.",
    )
    node.add_argument(
        "--connect-socks",
        type=parse_host_port,
        metavar="HOST:PORT",
        help="Peer public SOCKS5 address used to connect an outbound tunnel.",
    )
    node.add_argument(
        "--connect-target",
        type=parse_host_port,
        metavar="HOST:PORT",
        help="Peer internal tunnel target requested through --connect-socks.",
    )
    node.add_argument(
        "--forward",
        action="append",
        default=[],
        type=parse_forward,
        metavar="LISTEN_HOST:LISTEN_PORT=TARGET_HOST:TARGET_PORT",
        help="Expose a local TCP listener and forward it to the peer side through the active tunnel.",
    )
    node.add_argument(
        "--allow-target",
        action="append",
        default=[],
        type=parse_host_port,
        metavar="HOST:PORT",
        help="Allow peer tunnel OPEN requests to connect to this local target. Repeat for multiple targets.",
    )

    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.command == "node":
        run_node(
            socks_listen=args.socks_listen,
            tunnel_listen=args.tunnel_listen,
            connect_socks=args.connect_socks,
            connect_target=args.connect_target,
            forwards=args.forward,
            allow_targets=set(args.allow_target),
        )
        return


if __name__ == "__main__":
    main()
