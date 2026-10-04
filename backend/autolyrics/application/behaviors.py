import logging
import time

from mediatorx import IMessage, IPipelineBehavior, MessageHandlerDelegate


class LoggingBehavior(IPipelineBehavior[IMessage, object]):
    """Logs every message the mediator handles, with its duration."""

    def __init__(self, logger: logging.Logger | None = None):
        self._log = logger or logging.getLogger("autolyrics.mediator")

    async def handle(self, message: IMessage, next: MessageHandlerDelegate[object]) -> object:
        name = type(message).__name__
        started = time.perf_counter()
        try:
            response = await next()
        except Exception:
            self._log.info("%s failed after %.2fs", name, time.perf_counter() - started)
            raise
        self._log.debug("%s handled in %.2fs", name, time.perf_counter() - started)
        return response
