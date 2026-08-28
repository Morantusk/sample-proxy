import argparse

from sample_proxy.core.tunnel_gateway import run_gateway
from sample_proxy.core.tunnel_proxy_socks import run_socks_proxy
from sample_proxy.core.tunnel_proxy_tcp import run_tcp_proxy


def parse_host_port(value):
    host, port = value.rsplit(":", 1)
    return host, int(port)


def parse_reverse_listen(value):
    listen, target = value.split("=", 1)
    listen_host, listen_port = parse_host_port(listen)
    target_host, target_port = parse_host_port(target)
    return listen_host, listen_port, target_host, target_port


def build_parser():
    parser = argparse.ArgumentParser(
        prog="sample-proxy",
        description="Run the tunnel proxy or gateway.",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    gateway = subparsers.add_parser(
        "gateway",
        help="Run the cloud-side tunnel gateway.",
    )
    gateway.add_argument("--host", default="0.0.0.0")
    gateway.add_argument("--port", type=int, default=7000)
    gateway.add_argument(
        "--reverse-listen",
        action="append",
        default=[],
        type=parse_reverse_listen,
        metavar="LISTEN_HOST:LISTEN_PORT=TARGET_HOST:TARGET_PORT",
        help="Expose a cloud-side TCP listener and forward it to an intranet target through the tunnel.",
    )

    proxy = subparsers.add_parser(
        "proxy",
        help="Run the intranet-side tunnel proxy.",
    )
    proxy.add_argument("--gateway-host", required=True)
    proxy.add_argument("--gateway-port", type=int, default=7000)
    proxy.add_argument(
        "--mode",
        choices=("socks", "tcp"),
        default="socks",
    )
    proxy.add_argument("--socks-listen-host", default="127.0.0.1")
    proxy.add_argument("--socks-listen-port", type=int, default=1080)
    proxy.add_argument("--tcp-listen-host", default="127.0.0.1")
    proxy.add_argument("--tcp-listen-port", type=int, default=8000)
    proxy.add_argument("--target-host")
    proxy.add_argument("--target-port", type=int)
    proxy.add_argument(
        "--allow-target",
        action="append",
        default=[],
        type=parse_host_port,
        metavar="HOST:PORT",
        help="Allow a gateway reverse mapping to connect to this intranet target. Repeat for multiple targets.",
    )

    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.command == "gateway":
        run_gateway(
            host=args.host,
            port=args.port,
            reverse_listens=args.reverse_listen,
        )
        return

    gateway = (
        args.gateway_host,
        args.gateway_port,
    )

    if args.mode == "socks":
        run_socks_proxy(
            gateway=gateway,
            listen_host=args.socks_listen_host,
            listen_port=args.socks_listen_port,
            allow_targets=set(args.allow_target),
        )
        return

    if args.target_host is None or args.target_port is None:
        raise SystemExit(
            "proxy --mode tcp requires --target-host and --target-port"
        )

    run_tcp_proxy(
        gateway=gateway,
        listen_host=args.tcp_listen_host,
        listen_port=args.tcp_listen_port,
        target_host=args.target_host,
        target_port=args.target_port,
    )


if __name__ == "__main__":
    main()
