from abc import ABC, abstractmethod


class IProgress(ABC):
    """Live progress of one long step, for the progress bars. Safe to call from any thread and
    as often as convenient; implementations throttle."""

    @abstractmethod
    def update(self, fraction: float | None, detail: str = "") -> None:
        """`fraction` from 0 to 1, or None when the step cannot tell how far along it is."""


class NullProgress(IProgress):
    def update(self, fraction: float | None, detail: str = "") -> None:
        pass


NO_PROGRESS = NullProgress()
