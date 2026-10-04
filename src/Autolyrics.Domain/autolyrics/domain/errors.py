class DomainError(Exception):
    """Base for errors the presentation layer maps to client responses."""


class JobNotFoundError(DomainError):
    def __init__(self, job_id: str):
        super().__init__(f"no such job: {job_id}")
        self.job_id = job_id


class JobStateError(DomainError):
    """The job is in the wrong state for the request (still running, not finished)."""


class NotFoundError(DomainError):
    """A requested part of a job (a line, a file) does not exist."""


class InvalidInputError(DomainError):
    """The request carries data the domain cannot accept."""


class StageFailedError(DomainError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage}: {message}")
        self.stage = stage
