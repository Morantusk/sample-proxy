# sample-proxy

A unified SOCKS5 and TCP tunnel proxy node.

## Install

```powershell
python -m pip install --force-reinstall E:\Code\sample_proxy\dist\sample_proxy-0.3.0-py3-none-any.whl
```

Both sides must install the same version.

## Cloud Node

```powershell
python -m sample_proxy node `
  --socks-listen 0.0.0.0:7123 `
  --tunnel-pipe pipe:1 `
  --tcp-forward 0.0.0.0:18080=172.19.120.101:8080 `
  --admin-listen 127.0.0.1:9900 `
  --token-file C:\Users\chuzh\Desktop\sample-proxy.token
```

## Intranet Node

```powershell
python -m sample_proxy node `
  --socks-listen 127.0.0.1:1080 `
  --connect-socks 192.168.9.38:7123 `
  --connect-target pipe:1 `
  --tunnel-pool-size 4 `
  --ping-interval 30 `
  --pong-timeout 15 `
  --tcp-forward 127.0.0.1:8000=172.17.41.113:8000 `
  --allow-target 172.19.120.101:8080 `
  --admin-listen 127.0.0.1:9901 `
  --token-file C:\Users\nalong\Desktop\sample-proxy.token
```

## Traffic

```text
Intranet to cloud:
127.0.0.1:8000 -> tunnel -> cloud 172.17.41.113:8000

Cloud to intranet:
192.168.9.38:18080 -> tunnel -> intranet 172.19.120.101:8080
```

## Admin API

Keep admin listeners on `127.0.0.1` unless you have a trusted management network.

```powershell
curl http://127.0.0.1:9901/health
curl http://127.0.0.1:9901/stats
curl http://127.0.0.1:9901/tunnels
curl http://127.0.0.1:9901/streams
```

## Config File

Example intranet `config.toml`:

```toml
socks_listen = "127.0.0.1:1080"
connect_socks = "192.168.9.38:7123"
connect_target = "pipe:1"
tunnel_pool_size = 4
ping_interval = 30
pong_timeout = 15
admin_listen = "127.0.0.1:9901"
token_file = "C:/Users/nalong/Desktop/sample-proxy.token"

tcp_forwards = [
  "127.0.0.1:8000=172.17.41.113:8000",
]

allow_targets = [
  "172.19.120.101:8080",
]
```

Start with:

```powershell
python -m sample_proxy node --config .\config.toml
```
