class DomainError(Exception):
    """Business-rule violation. `code` is a localization key."""

    def __init__(self, code: str, message: str = "", **params: object) -> None:
        super().__init__(message or code)
        self.code = code
        self.params = params


class ValidationError(DomainError):
    pass


class DatabaseStartupError(Exception):
    """DB cannot be opened safely; never auto-create a new DB over a damaged one."""
