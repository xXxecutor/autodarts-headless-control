from abc import ABC, abstractmethod

# Startgröße, falls der Browser (noch) keine Größe gemeldet hat.
DEFAULT_COLS = 120
DEFAULT_ROWS = 40


class TerminalAdapter(ABC):

    @abstractmethod
    def start(
        self,
        executable: str,
        user: str | None,
        arguments: list[str],
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
    ):
        """Start an interactive terminal session with the given window size."""
        raise NotImplementedError
