import asyncio
import hashlib
import hmac
import os
import time
import uuid
from dataclasses import dataclass, field

from sample_proxy.core.protocol import *
from sample_proxy.core.socks5 import async_connect_through_socks5


PING_INTERVAL = 30
PONG_TIMEOUT = 15
AUTH_CHALLENGE_SIZE = 32


@dataclass
class TunnelConnection:
    id: str
    reader: object
    writer: object
    status: str = "authenticating"
    opened_at: float = field(default_factory=time.time)
    last_ping_at: float = 0
    last_pong_at: float = field(default_factory=time.time)
    active_streams: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TunnelSession:
    def __init__(
        self,
        allow_targets=None,
        local_stream_starts_odd=False,
        token=None,
        ping_interval=PING_INTERVAL,
        pong_timeout=PONG_TIMEOUT,
    ):
        self.allow_targets = allow_targets or set()
        self.token = token
        self.ping_interval = ping_interval
        self.pong_timeout = pong_timeout
        self.node_id = str(
            uuid.uuid4()
        )
        self.local_stream_lock = asyncio.Lock()
        self.local_stream_id = -1 if local_stream_starts_odd else 0
        self.next_tunnel_index = 0
        self.tunnels = []
        self.local_clients = {}
        self.local_stream_tunnels = {}
        self.remote_writers = {}
        self.remote_stream_tunnels = {}
        self.background_tasks = set()

    def track_task(self, task):
        self.background_tasks.add(
            task
        )
        task.add_done_callback(
            self.background_tasks.discard
        )
        return task

    def socket_name(self, writer):
        try:
            local = writer.get_extra_info(
                "sockname"
            )
            remote = writer.get_extra_info(
                "peername"
            )
            return f"local={local[0]}:{local[1]} remote={remote[0]}:{remote[1]}"
        except Exception:
            return "local=? remote=?"

    def tunnel_name(self, tunnel):
        return self.socket_name(
            tunnel.writer
        )

    async def next_local_stream(self):
        async with self.local_stream_lock:
            self.local_stream_id += 2
            return self.local_stream_id

    def ready_tunnels(self):
        return [
            tunnel for tunnel in self.tunnels
            if tunnel.status == "ready"
        ]

    def get_tunnel(self):
        ready = self.ready_tunnels()
        if not ready:
            return None

        tunnel = ready[
            self.next_tunnel_index % len(ready)
        ]
        self.next_tunnel_index += 1
        return tunnel

    def has_tunnel(self):
        return bool(
            self.ready_tunnels()
        )

    def add_tunnel(self, reader, writer):
        tunnel = TunnelConnection(
            id=str(uuid.uuid4()),
            reader=reader,
            writer=writer,
        )
        self.tunnels.append(
            tunnel
        )
        return tunnel

    def set_tunnel_ready(self, tunnel):
        tunnel.status = "ready"

    def clear_tunnel(self, tunnel):
        tunnel.status = "dead"
        if tunnel in self.tunnels:
            self.tunnels.remove(
                tunnel
            )

    async def close_tunnel_streams(self, tunnel):
        local_sids = [
            sid for sid, current in self.local_stream_tunnels.items()
            if current is tunnel
        ]
        remote_sids = [
            sid for sid, current in self.remote_stream_tunnels.items()
            if current is tunnel
        ]

        for sid in local_sids + remote_sids:
            await self.close_stream(
                sid
            )

    async def safe_send(self, msg_type, sid, data=b""):
        tunnel = self.get_tunnel()
        if tunnel is None:
            raise ConnectionError(
                "no active tunnel"
            )

        await self.send_to_tunnel(
            tunnel,
            msg_type,
            sid,
            data,
        )

    async def send_to_tunnel(self, tunnel, msg_type, sid, data=b""):
        async with tunnel.send_lock:
            await async_send_packet(
                tunnel.writer,
                msg_type,
                sid,
                data,
            )
        tunnel.bytes_out += len(data)

    def auth_digest(self, challenge):
        return hmac.new(
            self.token.encode(),
            challenge,
            hashlib.sha256,
        ).digest()

    async def authenticate_incoming(self, tunnel):
        if not self.token:
            print(
                "auth disabled"
            )
            return True

        challenge = os.urandom(
            AUTH_CHALLENGE_SIZE
        )
        await self.send_to_tunnel(
            tunnel,
            TYPE_AUTH_CHALLENGE,
            0,
            challenge,
        )

        packet = await async_recv_packet(
            tunnel.reader
        )

        if not packet:
            print(
                "auth failed: peer closed before auth"
            )
            return False

        msg_type, sid, data = packet

        if msg_type != TYPE_AUTH:
            print(
                "auth failed: first packet is not AUTH",
                msg_type,
                sid,
            )
            await self.send_to_tunnel(
                tunnel,
                TYPE_AUTH_FAIL,
                0,
            )
            return False

        ok = hmac.compare_digest(
            data,
            self.auth_digest(
                challenge
            ),
        )

        if not ok:
            print(
                "auth failed: digest mismatch"
            )
            await self.send_to_tunnel(
                tunnel,
                TYPE_AUTH_FAIL,
                0,
            )
            return False

        await self.send_to_tunnel(
            tunnel,
            TYPE_AUTH_OK,
            0,
        )
        print(
            "auth ok"
        )
        return True

    async def authenticate_outgoing(self, tunnel):
        if not self.token:
            print(
                "auth disabled"
            )
            return

        packet = await async_recv_packet(
            tunnel.reader
        )

        if not packet:
            raise ConnectionError(
                "peer closed before auth challenge"
            )

        msg_type, _, challenge = packet

        if msg_type != TYPE_AUTH_CHALLENGE:
            raise PermissionError(
                "auth rejected: peer did not send challenge"
            )

        await self.send_to_tunnel(
            tunnel,
            TYPE_AUTH,
            0,
            self.auth_digest(
                challenge
            ),
        )

        packet = await async_recv_packet(
            tunnel.reader
        )

        if not packet:
            raise ConnectionError(
                "peer closed before auth response"
            )

        msg_type, _, data = packet

        if msg_type != TYPE_AUTH_OK:
            detail = data.decode(errors="ignore") if data else ""
            raise PermissionError(
                f"auth rejected: {detail}"
            )

        print(
            "auth ok"
        )

    def start_ping_loop(self, tunnel):
        self.track_task(
            asyncio.create_task(
                self.ping_loop(tunnel)
            )
        )

    async def ping_loop(self, tunnel):
        while tunnel.status == "ready":
            await asyncio.sleep(
                self.ping_interval
            )

            if tunnel.status != "ready":
                break

            try:
                now = time.time()
                if (
                    tunnel.last_ping_at
                    and tunnel.last_pong_at < tunnel.last_ping_at
                    and now - tunnel.last_ping_at > self.pong_timeout
                ):
                    raise TimeoutError(
                        "pong timeout"
                    )

                await self.send_to_tunnel(
                    tunnel,
                    TYPE_PING,
                    0,
                )
                tunnel.last_ping_at = now
                print(
                    "ping sent"
                )
            except Exception as e:
                tunnel.status = "dead"
                print(
                    "ping failed",
                    e,
                )
                await self.close_writer(
                    tunnel.writer
                )
                break

    def encode_open_target(self, host, port):
        return (
            f"{self.node_id}|{host}:{port}"
        ).encode()

    def parse_open_target(self, data):
        text = data.decode()
        if "|" in text:
            _, target = text.split(
                "|",
                1,
            )
        else:
            target = text

        host, port = target.rsplit(
            ":",
            1,
        )
        return host, int(port)

    async def tunnel_reader(self, reader, writer, authenticated=False):
        tunnel = self.add_tunnel(
            reader,
            writer,
        )
        await self.run_tunnel(
            tunnel,
            authenticated=authenticated,
        )

    async def run_tunnel(self, tunnel, authenticated=False):
        if not authenticated and not await self.authenticate_incoming(tunnel):
            await self.close_writer(
                tunnel.writer
            )
            self.clear_tunnel(
                tunnel
            )
            return

        self.set_tunnel_ready(
            tunnel
        )

        print(
            "tunnel connected",
            self.tunnel_name(tunnel),
        )
        self.start_ping_loop(
            tunnel
        )

        try:
            while True:
                packet = await async_recv_packet(
                    tunnel.reader
                )

                if not packet:
                    print(
                        "tunnel peer closed",
                        self.tunnel_name(tunnel),
                    )
                    break

                msg_type, sid, data = packet
                tunnel.bytes_in += len(data)

                print(
                    "tunnel recv",
                    msg_type,
                    sid,
                    len(data),
                )

                if msg_type == TYPE_OPEN:
                    await self.handle_remote_open(
                        tunnel,
                        sid,
                        data,
                    )
                elif msg_type == TYPE_DATA:
                    await self.handle_data(
                        sid,
                        data,
                    )
                elif msg_type == TYPE_CLOSE:
                    await self.close_stream(
                        sid
                    )
                elif msg_type == TYPE_PING:
                    await self.send_to_tunnel(
                        tunnel,
                        TYPE_PONG,
                        0,
                    )
                    print(
                        "pong sent"
                    )
                elif msg_type == TYPE_PONG:
                    tunnel.last_pong_at = time.time()
                    print(
                        "pong recv"
                    )
        except Exception as e:
            print(
                "tunnel error",
                self.tunnel_name(tunnel),
                e,
            )
        finally:
            await self.close_tunnel_streams(
                tunnel
            )
            self.clear_tunnel(
                tunnel
            )
            await self.close_writer(
                tunnel.writer
            )
            print(
                "tunnel closed",
                self.tunnel_name(tunnel),
            )

    async def handle_data(self, sid, data):
        remote = self.remote_writers.get(
            sid
        )
        if remote:
            remote.write(
                data
            )
            await remote.drain()
            return

        client = self.local_clients.get(
            sid
        )
        if client:
            client.write(
                data
            )
            await client.drain()

    async def close_stream(self, sid):
        remote = self.remote_writers.pop(
            sid,
            None,
        )
        self.remote_stream_tunnels.pop(
            sid,
            None,
        )
        if remote:
            await self.close_writer(remote)

        client = self.local_clients.pop(
            sid,
            None,
        )
        self.local_stream_tunnels.pop(
            sid,
            None,
        )
        if client:
            await self.close_writer(client)

    async def handle_remote_open(self, tunnel, sid, data):
        try:
            host, port = self.parse_open_target(
                data
            )

            if self.allow_targets and (host, port) not in self.allow_targets:
                raise PermissionError(
                    f"target not allowed: {host}:{port}"
                )

            remote_reader, remote_writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host,
                    port,
                ),
                timeout=10,
            )

            self.remote_writers[sid] = remote_writer
            self.remote_stream_tunnels[sid] = tunnel
            tunnel.active_streams += 1

            print(
                "target connected",
                sid,
                host,
                port,
            )

            self.track_task(
                asyncio.create_task(
                    self.remote_reader(
                        sid,
                        remote_reader,
                        remote_writer,
                    )
                )
            )
        except Exception as e:
            print(
                "target connect failed",
                sid,
                e,
            )
            try:
                await self.send_to_tunnel(
                    tunnel,
                    TYPE_CLOSE,
                    sid,
                    str(e).encode(),
                )
            except Exception:
                pass

    async def remote_reader(self, sid, reader, writer):
        try:
            while True:
                data = await reader.read(
                    4096
                )

                if not data:
                    break

                tunnel = self.remote_stream_tunnels.get(
                    sid
                )
                if tunnel is None:
                    break

                await self.send_to_tunnel(
                    tunnel,
                    TYPE_DATA,
                    sid,
                    data,
                )
        except Exception as e:
            print(
                "target reader error",
                sid,
                e,
            )
        finally:
            self.remote_writers.pop(
                sid,
                None,
            )
            tunnel = self.remote_stream_tunnels.pop(
                sid,
                None,
            )
            if tunnel:
                tunnel.active_streams = max(
                    0,
                    tunnel.active_streams - 1,
                )
            await self.close_writer(
                writer
            )
            try:
                if tunnel:
                    await self.send_to_tunnel(
                        tunnel,
                        TYPE_CLOSE,
                        sid,
                    )
            except Exception:
                pass

    async def open_stream(self, reader, writer, target_host, target_port):
        sid = await self.next_local_stream()
        tunnel = self.get_tunnel()
        if tunnel is None:
            raise ConnectionError(
                "no active tunnel"
            )

        self.local_clients[sid] = writer
        self.local_stream_tunnels[sid] = tunnel
        tunnel.active_streams += 1

        try:
            await self.send_to_tunnel(
                tunnel,
                TYPE_OPEN,
                sid,
                self.encode_open_target(
                    target_host,
                    target_port,
                ),
            )

            while True:
                data = await reader.read(
                    4096
                )

                if not data:
                    break

                await self.send_to_tunnel(
                    tunnel,
                    TYPE_DATA,
                    sid,
                    data,
                )
        except Exception as e:
            print(
                "local stream error",
                sid,
                e,
            )
        finally:
            self.local_clients.pop(
                sid,
                None,
            )
            self.local_stream_tunnels.pop(
                sid,
                None,
            )
            tunnel.active_streams = max(
                0,
                tunnel.active_streams - 1,
            )
            try:
                await self.send_to_tunnel(
                    tunnel,
                    TYPE_CLOSE,
                    sid,
                )
            except Exception:
                pass
            await self.close_writer(
                writer
            )

    async def connect_peer_once(self, connect_socks, connect_target):
        if connect_socks is None:
            return

        if connect_target is None:
            raise ValueError(
                "connect_target is required when connect_socks is set"
            )

        if not self.token:
            raise ValueError(
                "token is required when connect_socks is set; use --token-file or SAMPLE_PROXY_TOKEN"
            )

        reader, writer = await asyncio.open_connection(
            connect_socks[0],
            connect_socks[1],
        )
        await async_connect_through_socks5(
            reader,
            writer,
            connect_target[0],
            connect_target[1],
        )
        print(
            "socks connect ok",
            self.socket_name(writer),
        )

        tunnel = self.add_tunnel(
            reader,
            writer,
        )
        await self.authenticate_outgoing(
            tunnel,
        )

        await self.run_tunnel(
            tunnel,
            authenticated=True,
        )

    async def connect_peer_loop(self, connect_socks, connect_target, retry_interval=3):
        if connect_socks is None:
            return

        while True:
            try:
                print(
                    "connect peer socks",
                    f"{connect_socks[0]}:{connect_socks[1]}",
                    "target",
                    f"{connect_target[0]}:{connect_target[1]}",
                )
                await self.connect_peer_once(
                    connect_socks,
                    connect_target,
                )
            except ValueError as e:
                print(
                    "connect peer config error",
                    e,
                )
                return
            except Exception as e:
                print(
                    "connect peer failed",
                    e,
                )

            print(
                "reconnect peer after",
                retry_interval,
                "seconds",
            )
            await asyncio.sleep(
                retry_interval
            )

    def stats(self):
        now = time.time()
        tunnels = []
        for tunnel in self.tunnels:
            tunnels.append(
                {
                    "id": tunnel.id,
                    "status": tunnel.status,
                    "address": self.tunnel_name(tunnel),
                    "active_streams": tunnel.active_streams,
                    "bytes_in": tunnel.bytes_in,
                    "bytes_out": tunnel.bytes_out,
                    "opened_seconds": round(now - tunnel.opened_at, 3),
                    "last_ping_seconds": round(now - tunnel.last_ping_at, 3)
                    if tunnel.last_ping_at else None,
                    "last_pong_seconds": round(now - tunnel.last_pong_at, 3),
                }
            )

        return {
            "node_id": self.node_id,
            "ready_tunnels": len(
                self.ready_tunnels()
            ),
            "tunnels": tunnels,
            "local_streams": len(self.local_clients),
            "remote_streams": len(self.remote_writers),
            "local_stream_ids": sorted(
                self.local_clients.keys()
            ),
            "remote_stream_ids": sorted(
                self.remote_writers.keys()
            ),
            "background_tasks": len(self.background_tasks),
        }

    async def close_writer(self, writer):
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
