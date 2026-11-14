import asyncio
import http
import logging
import os
import platform

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from app.adapters.terminal.base import DEFAULT_COLS, DEFAULT_ROWS
from app.services.request_origin import is_same_origin
from app.services.terminal import TerminalService


HOST = "0.0.0.0"
PORT = int(os.environ.get("HEADLESS_WS_PORT", "8092"))
INITIAL_SIZE_TIMEOUT = 2.0
# Ein funktionierender TUI-Start zeichnet nach ~0,1 s; hängende Starts nie.
FIRST_OUTPUT_TIMEOUT = 2.0
FIRST_OUTPUT_MIN_BYTES = 16
START_ATTEMPTS = 8

logger = logging.getLogger(__name__)


def check_origin(connection, request):
    """Reject WebSocket handshakes initiated by foreign web pages."""
    origin = request.headers.get("Origin")
    host = request.headers.get("Host")
    if is_same_origin(origin, host):
        return None
    logger.warning("Rejected terminal WebSocket from Origin %s (Host %s)", origin, host)
    return connection.respond(http.HTTPStatus.FORBIDDEN, "Cross-origin WebSocket rejected\n")


def parse_resize(message) -> tuple[int, int] | None:
    """'RESIZE:<cols>:<rows>' -> (cols, rows), sonst None."""
    if not isinstance(message, str) or not message.startswith("RESIZE:"):
        return None
    try:
        _, cols, rows = message.split(":", 2)
        cols, rows = int(cols), int(rows)
    except ValueError:
        return None
    if cols < 1 or rows < 1:
        return None
    return min(cols, 1000), min(rows, 1000)


async def initial_size(websocket, timeout: float = INITIAL_SIZE_TIMEOUT):
    """Wait briefly for the browser's first RESIZE message.

    Returns (cols, rows, pending): pending is a first message that was not a
    resize (e.g. a key press) and must be forwarded once the TUI runs.
    """
    try:
        message = await asyncio.wait_for(websocket.recv(), timeout)
    except (asyncio.TimeoutError, TimeoutError):
        return DEFAULT_COLS, DEFAULT_ROWS, None
    size = parse_resize(message)
    if size:
        return size[0], size[1], None
    return DEFAULT_COLS, DEFAULT_ROWS, message if isinstance(message, str) else None


async def read_first_output(session, timeout: float, minimum: int = FIRST_OUTPUT_MIN_BYTES) -> bytes:
    """Collect the first output of a freshly started TUI.

    Returns b"" if fewer than ``minimum`` bytes arrive in time (the TUI hangs);
    the caller then discards the session, so a read cut off by the timeout
    loses nothing that is still needed.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    data = b""
    while len(data) < minimum:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return b""
        try:
            chunk = await asyncio.wait_for(session.read(), remaining)
        except (asyncio.TimeoutError, TimeoutError):
            return b""
        if not chunk:
            # Prozess sofort beendet (z. B. Fehlermeldung): Ausgabe zeigen.
            return data or b"\r\n"
        data += chunk
    return data


async def terminal(websocket):
    logger.info("New WebSocket connection from %s", websocket.remote_address)
    if platform.system() != "Linux":
        await websocket.send("\r\nTerminal ist nur unter Linux verfügbar.\r\n")
        return

    from app.services.terminal_session import TerminalSession

    # Die Seite meldet direkt nach dem Verbindungsaufbau ihre Fenstergröße;
    # damit startet die TUI gleich in der richtigen Größe.
    try:
        cols, rows, pending = await initial_size(websocket)
    except ConnectionClosed:
        return

    service = TerminalService()
    session = None
    first_output = b""
    for attempt in range(1, START_ATTEMPTS + 1):
        result = service.start_tui(cols, rows)
        if not result:
            await websocket.send("\r\nTerminal konnte nicht gestartet werden (Autodarts nicht gefunden).\r\n")
            return
        pid, fd = result
        logger.info("Terminal started with pid=%s, fd=%s (attempt %s)", pid, fd, attempt)
        candidate = TerminalSession(pid, fd)

        # "autodarts remote" bleibt beim Start gelegentlich hängen und gibt dann
        # nie etwas aus. Ein funktionierender Start zeichnet sofort. Ohne
        # Ausgabe: beenden und neu starten.
        first_output = await read_first_output(candidate, FIRST_OUTPUT_TIMEOUT)
        if first_output:
            session = candidate
            break

        logger.warning("Terminal pid=%s produced no output; restarting TUI", pid)
        await asyncio.get_running_loop().run_in_executor(None, candidate.close)
        if attempt == 1:
            try:
                await websocket.send("\r\nAutodarts-TUI reagiert nicht, neuer Versuch …\r\n")
            except ConnectionClosed:
                return

    if session is None:
        await websocket.send(
            "\r\nDie Autodarts-TUI hat mehrfach nicht reagiert. "
            "Bitte Seite neu laden oder Autodarts auf der Startseite neu starten.\r\n"
        )
        return

    pid = session.pid
    text = session.decode(first_output)
    if text:
        await websocket.send(text)
    if pending is not None:
        try:
            session.write(pending)
        except OSError:
            pass

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
                    size = parse_resize(message)
                    if size:
                        try:
                            session.resize(*size)
                        except OSError:
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
