import asyncio

from sample_proxy.core.socks5 import (
    async_handle_socks5,
    async_send_socks5_reply,
)


def writer_name(writer):
    try:
        peer = writer.get_extra_info("peername")
        return f"{peer[0]}:{peer[1]}"
    except Exception:
        return "?:?"


async def close_writer(writer):
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass


async def start_public_socks(
    session,
    socks_listen,
    tunnel_listen=None,
    tunnel_pipe=None,
):
    if socks_listen is None:
        return None

    async def handle_client(reader, writer):
        await handle_public_socks_client(
            session,
            reader,
            writer,
            tunnel_listen,
            tunnel_pipe,
        )

    server = await asyncio.start_server(
        handle_client,
        socks_listen[0],
        socks_listen[1],
        backlog=100,
    )

    print(
        "socks listen",
        f"{socks_listen[0]}:{socks_listen[1]}",
    )
    return server


async def handle_public_socks_client(
    session,
    reader,
    writer,
    tunnel_listen=None,
    tunnel_pipe=None,
):
    target = None

    try:
        print(
            "socks accepted",
            writer_name(writer),
        )

        target = await async_handle_socks5(
            reader,
            writer,
        )

        if not target:
            await close_writer(
                writer
            )
            return

        host, port = target

        if tunnel_pipe and (host, port) == tunnel_pipe:
            print(
                "pipe tunnel accepted",
                f"{host}:{port}",
            )
            await async_send_socks5_reply(
                writer,
                True,
            )
            await session.tunnel_reader(
                reader,
                writer,
            )
            return

        if tunnel_listen and (host, port) == tunnel_listen:
            print(
                "tcp tunnel accepted",
                f"{host}:{port}",
            )
            tunnel_reader, tunnel_writer = await asyncio.open_connection(
                tunnel_listen[0],
                tunnel_listen[1],
            )
            await async_send_socks5_reply(
                writer,
                True,
            )
            await relay_pair(
                reader,
                writer,
                tunnel_reader,
                tunnel_writer,
            )
            return

        if not session.has_tunnel():
            print(
                "public socks rejected: no active tunnel",
                host,
                port,
            )
            await async_send_socks5_reply(
                writer,
                False,
            )
            await close_writer(
                writer
            )
            return

        await async_send_socks5_reply(
            writer,
            True,
        )
        await session.open_stream(
            reader,
            writer,
            host,
            port,
        )
    except Exception as e:
        print(
            "public socks error",
            target,
            e,
        )
        await close_writer(
            writer
        )


async def start_tunnel(session, tunnel_listen):
    if tunnel_listen is None:
        return None

    async def handle_tunnel(reader, writer):
        print(
            "tunnel accepted",
            writer_name(writer),
        )
        await session.tunnel_reader(
            reader,
            writer,
        )

    server = await asyncio.start_server(
        handle_tunnel,
        tunnel_listen[0],
        tunnel_listen[1],
        backlog=10,
    )

    print(
        "tunnel listen",
        f"{tunnel_listen[0]}:{tunnel_listen[1]}",
    )
    return server


async def start_forward(session, listen_host, listen_port, target_host, target_port):
    async def handle_client(reader, writer):
        print(
            "forward accepted",
            writer_name(writer),
            "->",
            f"{target_host}:{target_port}",
        )

        if not session.has_tunnel():
            print(
                "forward rejected: no active tunnel",
                f"{target_host}:{target_port}",
            )
            await close_writer(
                writer
            )
            return

        await session.open_stream(
            reader,
            writer,
            target_host,
            target_port,
        )

    server = await asyncio.start_server(
        handle_client,
        listen_host,
        listen_port,
        backlog=100,
    )

    print(
        "forward listen",
        f"{listen_host}:{listen_port}",
        "->",
        f"{target_host}:{target_port}",
    )
    return server


async def relay_pair(reader_a, writer_a, reader_b, writer_b):
    async def relay(reader, writer):
        try:
            while True:
                data = await reader.read(
                    4096
                )
                if not data:
                    break
                writer.write(
                    data
                )
                await writer.drain()
        finally:
            await close_writer(
                writer
            )

    task_a = asyncio.create_task(
        relay(reader_a, writer_b)
    )
    task_b = asyncio.create_task(
        relay(reader_b, writer_a)
    )
    await asyncio.wait(
        {task_a, task_b},
        return_when=asyncio.FIRST_COMPLETED,
    )
    task_a.cancel()
    task_b.cancel()
    await close_writer(
        writer_a
    )
    await close_writer(
        writer_b
    )
