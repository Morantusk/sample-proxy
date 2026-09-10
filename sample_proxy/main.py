import argparse
import os

from sample_proxy.config import as_list, load_config
from sample_proxy.core.tunnel_node import run_node


def parse_host_port(value):
    host, port = value.rsplit(":", 1)
    return host, int(port)


def parse_forward(value):
    listen, target = value.split("=", 1)
    listen_host, listen_port = parse_host_port(listen)
    target_host, target_port = parse_host_port(target)
    return listen_host, listen_port, target_host, target_port


def load_token(token_file=None):
    if token_file:
        with open(
            token_file,
            "r",
            encoding="utf-8",
        ) as file:
            return file.read().strip()

    return os.environ.get(
        "SAMPLE_PROXY_TOKEN"
    )


def choose(name, args, config, default=None):
    value = getattr(
        args,
        name,
        None,
    )
    if value is not None:
        return value

    return config.get(
        name,
        default,
    )


def choose_list(name, args, config):
    cli_value = getattr(
        args,
        name,
        None,
    )
    config_value = as_list(
        config.get(name)
    )

    if cli_value:
        return config_value + cli_value

    return config_value


def parse_config_host_port(config, name):
    value = config.get(
        name
    )
    if value is None or isinstance(value, tuple):
        return value
    return parse_host_port(
        value
    )


def parse_config_forwards(config):
    values = []
    for name in (
        "forward",
        "forwards",
        "tcp_forward",
        "tcp_forwards",
    ):
        values.extend(
            as_list(
                config.get(name)
            )
        )

    return [
        parse_forward(value)
        for value in values
    ]


def parse_config_allow_targets(config):
    values = []
    for name in (
        "allow_target",
        "allow_targets",
    ):
        values.extend(
            as_list(
                config.get(name)
            )
        )

    return [
        parse_host_port(value)
        for value in values
    ]


def normalize_config(config):
    normalized = dict(
        config
    )

    for name in (
        "socks_listen",
        "tunnel_listen",
        "tunnel_pipe",
        "connect_socks",
        "connect_target",
        "admin_listen",
    ):
        normalized[name] = parse_config_host_port(
            normalized,
            name,
        )

    normalized["forward"] = parse_config_forwards(
        normalized
    )
    normalized["allow_target"] = parse_config_allow_targets(
        normalized
    )
    return normalized


def build_parser():
    parser = argparse.ArgumentParser(
        prog="sample-proxy",
        description="Run a unified SOCKS and tunnel proxy node.",
    )
    parser.add_argument(
        "--config",
        help="Read node options from a TOML config file. CLI values override or append file values.",
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
        "--config",
        dest="node_config",
        help="Read node options from a TOML config file. CLI values override or append file values.",
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
        "--tunnel-pipe",
        type=parse_host_port,
        metavar="NAME:ID",
        help="Virtual tunnel endpoint accepted through --socks-listen, for example pipe:1.",
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
        "--tcp-forward",
        dest="forward",
        action="append",
        type=parse_forward,
        metavar="LISTEN_HOST:LISTEN_PORT=TARGET_HOST:TARGET_PORT",
        help="Alias of --forward. Expose a plain TCP listener for one fixed target through the active tunnel.",
    )
    node.add_argument(
        "--allow-target",
        action="append",
        default=[],
        type=parse_host_port,
        metavar="HOST:PORT",
        help="Allow peer tunnel OPEN requests to connect to this local target. Repeat for multiple targets.",
    )
    node.add_argument(
        "--token-file",
        help="Read the tunnel authentication token from this file. Falls back to SAMPLE_PROXY_TOKEN.",
    )
    node.add_argument(
        "--tunnel-pool-size",
        type=int,
        help="Number of outbound tunnels to keep when --connect-socks is set.",
    )
    node.add_argument(
        "--ping-interval",
        type=float,
        help="Seconds between tunnel ping packets.",
    )
    node.add_argument(
        "--pong-timeout",
        type=float,
        help="Seconds without pong before a tunnel is closed.",
    )
    node.add_argument(
        "--admin-listen",
        type=parse_host_port,
        metavar="HOST:PORT",
        help="Local HTTP admin listener for /health and /stats.",
    )

    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config = normalize_config(
        load_config(
            args.config
            or getattr(args, "node_config", None)
        )
    )

    if args.command == "node":
        token_file = choose(
            "token_file",
            args,
            config,
        )
        try:
            run_node(
                socks_listen=choose(
                    "socks_listen",
                    args,
                    config,
                ),
                tunnel_listen=choose(
                    "tunnel_listen",
                    args,
                    config,
                ),
                tunnel_pipe=choose(
                    "tunnel_pipe",
                    args,
                    config,
                ),
                connect_socks=choose(
                    "connect_socks",
                    args,
                    config,
                ),
                connect_target=choose(
                    "connect_target",
                    args,
                    config,
                ),
                forwards=choose_list(
                    "forward",
                    args,
                    config,
                ),
                allow_targets=set(
                    choose_list(
                        "allow_target",
                        args,
                        config,
                    )
                ),
                token=load_token(token_file),
                tunnel_pool_size=choose(
                    "tunnel_pool_size",
                    args,
                    config,
                    1,
                ),
                ping_interval=choose(
                    "ping_interval",
                    args,
                    config,
                    30,
                ),
                pong_timeout=choose(
                    "pong_timeout",
                    args,
                    config,
                    15,
                ),
                admin_listen=choose(
                    "admin_listen",
                    args,
                    config,
                ),
            )
        except ValueError as e:
            raise SystemExit(str(e))
        return


if __name__ == "__main__":
    main()
