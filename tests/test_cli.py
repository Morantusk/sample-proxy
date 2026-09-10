import unittest
import tempfile
from unittest.mock import patch

from sample_proxy import main


class CliTests(unittest.TestCase):
    def test_node_accepts_socks_tunnel_peer_and_forwards(self):
        args = main.parse_args(
            [
                "node",
                "--socks-listen",
                "0.0.0.0:7123",
                "--tunnel-pipe",
                "pipe:1",
                "--connect-socks",
                "115.29.197.159:8092",
                "--connect-target",
                "pipe:1",
                "--forward",
                "0.0.0.0:13308=rm-bp1.mysql.rds.aliyuncs.com:3306",
                "--forward",
                "0.0.0.0:16380=r-bp1.redis.rds.aliyuncs.com:6379",
                "--allow-target",
                "172.19.120.101:8080",
                "--token-file",
                "C:\\secure\\sample-proxy.token",
                "--tunnel-pool-size",
                "3",
                "--ping-interval",
                "20",
                "--pong-timeout",
                "8",
                "--admin-listen",
                "127.0.0.1:9900",
            ]
        )

        self.assertEqual(args.command, "node")
        self.assertEqual(args.socks_listen, ("0.0.0.0", 7123))
        self.assertEqual(args.tunnel_pipe, ("pipe", 1))
        self.assertEqual(args.connect_socks, ("115.29.197.159", 8092))
        self.assertEqual(args.connect_target, ("pipe", 1))
        self.assertEqual(
            args.forward,
            [
                ("0.0.0.0", 13308, "rm-bp1.mysql.rds.aliyuncs.com", 3306),
                ("0.0.0.0", 16380, "r-bp1.redis.rds.aliyuncs.com", 6379),
            ],
        )
        self.assertEqual(args.allow_target, [("172.19.120.101", 8080)])
        self.assertEqual(args.token_file, "C:\\secure\\sample-proxy.token")
        self.assertEqual(args.tunnel_pool_size, 3)
        self.assertEqual(args.ping_interval, 20)
        self.assertEqual(args.pong_timeout, 8)
        self.assertEqual(args.admin_listen, ("127.0.0.1", 9900))

    def test_load_token_uses_environment_when_file_is_not_set(self):
        with patch.dict("os.environ", {"SAMPLE_PROXY_TOKEN": "secret-token"}):
            self.assertEqual(main.load_token(), "secret-token")

    def test_node_accepts_tcp_forward_alias(self):
        args = main.parse_args(
            [
                "node",
                "--tcp-forward",
                "127.0.0.1:18080=172.19.120.101:8080",
            ]
        )

        self.assertEqual(
            args.forward,
            [("127.0.0.1", 18080, "172.19.120.101", 8080)],
        )

    def test_config_file_values_are_normalized(self):
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            suffix=".toml",
        ) as file:
            file.write(
                '\n'.join(
                    [
                        'socks_listen = "127.0.0.1:1080"',
                        'tunnel_pipe = "pipe:1"',
                        'tunnel_pool_size = 2',
                        'admin_listen = "127.0.0.1:9900"',
                        'forwards = ["127.0.0.1:8000=example.com:80"]',
                        'tcp_forwards = ["127.0.0.1:8001=example.org:81"]',
                        'allow_target = "172.19.120.100:8080"',
                        'allow_targets = ["172.19.120.101:8080"]',
                    ]
                )
            )
            path = file.name

        config = main.normalize_config(
            main.load_config(path)
        )

        self.assertEqual(
            config["socks_listen"],
            ("127.0.0.1", 1080),
        )
        self.assertEqual(
            config["tunnel_pipe"],
            ("pipe", 1),
        )
        self.assertEqual(
            config["tunnel_pool_size"],
            2,
        )
        self.assertEqual(
            config["admin_listen"],
            ("127.0.0.1", 9900),
        )
        self.assertEqual(
            config["forward"],
            [
                ("127.0.0.1", 8000, "example.com", 80),
                ("127.0.0.1", 8001, "example.org", 81),
            ],
        )
        self.assertEqual(
            config["allow_target"],
            [
                ("172.19.120.100", 8080),
                ("172.19.120.101", 8080),
            ],
        )

if __name__ == "__main__":
    unittest.main()
