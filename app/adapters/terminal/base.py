from abc import ABC, abstractmethod


class TerminalAdapter(ABC):

    @abstractmethod
    def start(self, executable: str, user: str | None, arguments: list[str]):
        """Start an interactive terminal session."""
        raise NotImplementedError