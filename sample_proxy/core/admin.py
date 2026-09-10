import json


async def start_admin(session, admin_listen):
    if admin_listen is None:
        return None

    async def handle_client(reader, writer):
        try:
            request = await reader.readline()
            parts = request.decode(errors="ignore").strip().split()
            path = parts[1] if len(parts) >= 2 else "/"

            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break

            if path == "/health":
                status = 200 if session.has_tunnel() else 503
                body = {
                    "ok": session.has_tunnel(),
                    "ready_tunnels": len(session.ready_tunnels()),
                }
            elif path in ("/stats", "/tunnels", "/streams", "/"):
                status = 200
                body = session.stats()
            else:
                status = 404
                body = {
                    "error": "not found"
                }

            payload = json.dumps(
                body,
                ensure_ascii=True,
            ).encode()
            reason = {
                200: "OK",
                404: "Not Found",
                503: "Service Unavailable",
            }[status]
            writer.write(
                f"HTTP/1.1 {status} {reason}\r\n".encode()
                + b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(payload)}\r\n".encode()
                + b"Connection: close\r\n\r\n"
                + payload
            )
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    import asyncio

    server = await asyncio.start_server(
        handle_client,
        admin_listen[0],
        admin_listen[1],
        backlog=20,
    )

    print(
        "admin listen",
        f"{admin_listen[0]}:{admin_listen[1]}",
    )
    return server
