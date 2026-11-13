from abc import ABC, abstractmethod


class SystemAdapter(ABC):

    @abstractmethod
    def reboot(self) -> bool:
        """Reboot the operating system."""
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> bool:
        """Shut down the operating system."""
        raise NotImplementedError

    @abstractmethod
    def get_logs(self, target: str = "app", lines: int = 50) -> str:
        """Read recent system or service logs."""
        raise NotImplementedError