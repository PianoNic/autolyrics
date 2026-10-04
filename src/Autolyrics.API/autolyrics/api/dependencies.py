from fastapi import Request
from mediatorx import Mediator

from autolyrics.application.interfaces.jobs import IJobEventBroadcaster
from autolyrics.composition.container import Container


class ApiDependencies:
    """FastAPI dependency providers. The container lives on the app, not in a global, so every
    app (and every test) has its own object graph."""

    @staticmethod
    def container(request: Request) -> Container:
        return request.app.state.container

    @staticmethod
    def mediator(request: Request) -> Mediator:
        return request.app.state.container.mediator

    @staticmethod
    def broadcaster(request: Request) -> IJobEventBroadcaster:
        return request.app.state.container.broadcaster
