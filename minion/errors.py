"""Exceptions raised by Minion."""


class MinionError(Exception):
    """Base class for all Minion errors. The message is meant for humans and agents."""


class NotFound(MinionError):
    """A desktop, profile or snapshot does not exist."""


class BackendError(MinionError):
    """The container runtime (or the local X stack) failed or is missing."""


class AgentError(MinionError):
    """The in-desktop agent reported an error (bad target, failed action, ...)."""

    def __init__(self, message: str, code: int = -32000):
        super().__init__(message)
        self.code = code
