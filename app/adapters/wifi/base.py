from abc import ABC, abstractmethod


class WifiAdapter(ABC):
    @abstractmethod
    def detect(self) -> dict:
        """Detect available Linux networking tools without changing the system."""
        raise NotImplementedError
