import unittest

from sample_proxy import main


class CliTests(unittest.TestCase):
    def test_node_accepts_socks_tunnel_peer_and_forwards(self):
        args = main.parse_args(
            [
                "node",
                "--socks-listen",
                "0.0.0.0:7123",
                "--tunnel-listen",
                "127.0.0.1:7124",
                "--connect-socks",
                "115.29.197.159:8092",
                "--connect-target",
                "127.0.0.1:7124",
                "--forward",
                "0.0.0.0:13308=rm-bp1.mysql.rds.aliyuncs.com:3306",
                "--forward",
                "0.0.0.0:16380=r-bp1.redis.rds.aliyuncs.com:6379",
                "--allow-target",
                "172.19.120.101:8080",
            ]
        )

        self.assertEqual(args.command, "node")
        self.assertEqual(args.socks_listen, ("0.0.0.0", 7123))
        self.assertEqual(args.tunnel_listen, ("127.0.0.1", 7124))
        self.assertEqual(args.connect_socks, ("115.29.197.159", 8092))
        self.assertEqual(args.connect_target, ("127.0.0.1", 7124))
        self.assertEqual(
            args.forward,
            [
                ("0.0.0.0", 13308, "rm-bp1.mysql.rds.aliyuncs.com", 3306),
                ("0.0.0.0", 16380, "r-bp1.redis.rds.aliyuncs.com", 6379),
            ],
        )
        self.assertEqual(args.allow_target, [("172.19.120.101", 8080)])

    def test_gateway_accepts_reverse_listen_mappings(self):
        args = main.parse_args(
            [
                "gateway",
                "--host",
                "0.0.0.0",
                "--port",
                "7000",
                "--reverse-listen",
                "0.0.0.0:18080=192.168.1.10:8080",
                "--reverse-listen",
                "127.0.0.1:15432=192.168.1.20:5432",
            ]
        )

        self.assertEqual(args.command, "gateway")
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 7000)
        self.assertEqual(
            args.reverse_listen,
            [
                ("0.0.0.0", 18080, "192.168.1.10", 8080),
                ("127.0.0.1", 15432, "192.168.1.20", 5432),
            ],
        )

    def test_proxy_accepts_gateway_and_socks_options(self):
        args = main.parse_args(
            [
                "proxy",
                "--gateway-host",
                "203.0.113.10",
                "--gateway-port",
                "7000",
                "--socks-listen-host",
                "127.0.0.1",
                "--socks-listen-port",
                "1080",
                "--allow-target",
                "192.168.1.10:8080",
            ]
        )

        self.assertEqual(args.command, "proxy")
        self.assertEqual(args.gateway_host, "203.0.113.10")
        self.assertEqual(args.gateway_port, 7000)
        self.assertEqual(args.socks_listen_host, "127.0.0.1")
        self.assertEqual(args.socks_listen_port, 1080)
        self.assertEqual(args.allow_target, [("192.168.1.10", 8080)])


if __name__ == "__main__":
    unittest.main()
