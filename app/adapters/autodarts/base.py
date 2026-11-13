from abc import ABC, abstractmethod


class AutodartsAdapter(ABC):

    @abstractmethod
    def status(self) -> dict:
        """
        Return the current Autodarts status.

        The returned dictionary must contain:
        - installed: bool
        - running: bool
        - path: str | None
        - version: str | None
        - terminal_user: str | None
        """
        raise NotImplementedError

    @abstractmethod
    def start(self) -> bool:
        """Start Autodarts."""
        raise NotImplementedError

    @abstractmethod
    def restart(self) -> bool:
        """Restart Autodarts."""
        raise NotImplementedError

    @abstractmethod
    def version(self) -> str | None:
        """Return the installed Autodarts version."""
        raise NotImplementedError

    @abstractmethod
    def is_running(self) -> bool:
        """Return whether the Autodarts process is running."""
        raise NotImplementedError

    @abstractmethod
    def terminal_user(self) -> str | None:
        """Return the user account used to run Autodarts."""
        raise NotImplementedError

    @abstractmethod
    def terminal_launch_info(self):
        """Return information required to launch the Autodarts terminal."""
        raise NotImplementedError