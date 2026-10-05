"""Errors raised while compiling a rule or resolving a Service."""


class PatternError(ValueError):
    """A rule field is invalid. `field` is a camelCase dotted path the Admin maps to a field."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class ServiceNotResolvedError(LookupError):
    """No Service (or no usable environment) for a path; becomes `service_not_resolved`."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail
