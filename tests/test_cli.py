import unittest
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

    def test_load_token_uses_environment_when_file_is_not_set(self):
        with patch.dict("os.environ", {"SAMPLE_PROXY_TOKEN": "secret-token"}):
            self.assertEqual(main.load_token(), "secret-token")

if __name__ == "__main__":
    unittest.main()
