from abc import ABC, abstractmethod


class ILlmClient(ABC):
    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    async def complete_json(self, system: str, prompt: str) -> dict:
        """Ask the model and return the JSON object in its reply."""
