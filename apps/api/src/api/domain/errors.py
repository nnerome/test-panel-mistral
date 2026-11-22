"""Domain errors. Each maps to one HTTP status; ownership failures map to 404 on purpose,
so a request for another customer's object is indistinguishable from a nonexistent one
and never leaks that the object exists."""


class DomainError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class OwnershipError(NotFoundError):
    """The object exists but belongs to another customer: answer 404, never 403."""

    code = "not_found"


class AuthRequiredError(DomainError):
    status_code = 401
    code = "login_required"


class StepUpRequiredError(DomainError):
    status_code = 401
    code = "strong_auth_required"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class GuardrailViolation(DomainError):
    status_code = 400
    code = "refused"


class BankError(DomainError):
    status_code = 502
    code = "bank_unavailable"


class BankTimeoutError(BankError):
    code = "bank_timeout"
