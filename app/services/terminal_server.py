import asyncio
import http
import logging
import os
import platform

from websockets.asyncio.server import serve

from app.services.request_origin import is_same_origin
from app.services.terminal import TerminalService


HOST = "0.0.0.0"
PORT = int(os.environ.get("HEADLESS_WS_PORT", "8092"))

logger = logging.getLogger(__name__)


def check_origin(connection, request):
    """Reject WebSocket handshakes initiated by foreign web pages."""
    origin = request.headers.get("Origin")
    host = request.headers.get("Host")
    if is_same_origin(origin, host):
        return None
    logger.warning("Rejected terminal WebSocket from Origin %s (Host %s)", origin, host)
    return connection.respond(http.HTTPStatus.FORBIDDEN, "Cross-origin WebSocket rejected\n")


async def terminal(websocket):
    logger.info("New WebSocket connection from %s", websocket.remote_address)
    if platform.system() != "Linux":
        await websocket.send("\r\nTerminal ist nur unter Linux verfügbar.\r\n")
        return

    from app.services.terminal_session import TerminalSession

    service = TerminalService()
    result = service.start_tui()

    if not result:
        await websocket.send("\r\nTerminal konnte nicht gestartet werden (Autodarts nicht gefunden).\r\n")
        return
    logger.info("Terminal started with pid=%s, fd=%s", result[0], result[1])

    pid, fd = result
    session = TerminalSession(pid, fd)

    async def read_pty():
        while True:
            try:
                data = await session.read()
                if not data:
                    break
                text = session.decode(data)
                if text:
                    await websocket.send(text)
            except Exception:
                break

    async def write_pty():
        try:
            async for message in websocket:
                if not isinstance(message, str):
                    continue

                if message.startswith("RESIZE:"):
                    try:
                        _, cols, rows = message.split(":", 2)
                        session.resize(int(cols), int(rows))
                    except (ValueError, OSError):
                        pass
                else:
                    try:
                        session.write(message)
                    except OSError:
                        break
        except Exception:
            pass

    tasks = {
        asyncio.create_task(read_pty()),
        asyncio.create_task(write_pty()),
    }

    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        # Prozess zuerst beenden, damit der blockierende read() im Executor zurückkehrt.
        await asyncio.get_running_loop().run_in_executor(None, session.close)
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Terminal session pid=%s closed", pid)


async def websocket_server():
    async with serve(terminal, HOST, PORT, process_request=check_origin):
        print(f"Terminal-WebSocket listening on {HOST}:{PORT}")
        await asyncio.Future()


def start_terminal_server():
    asyncio.run(websocket_server())


if __name__ == "__main__":
    start_terminal_server()
