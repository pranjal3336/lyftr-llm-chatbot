"""Domain errors mapped to JSON responses in main.py."""


class SessionNotFoundError(Exception):
    """Raised when a session has no stored messages."""


class AllProvidersUnavailableError(Exception):
    """Raised when every key in the pool failed."""


class ServiceUnhealthyError(Exception):
    """Raised by the health check when a dependency is not ready."""
