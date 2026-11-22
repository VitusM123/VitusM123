"""Fachliche Fehler. Werden in app.main auf HTTP-Statuscodes abgebildet."""


class DomainError(Exception):
    status_code = 400


class NotFoundError(DomainError):
    status_code = 404


class ValidationError(DomainError):
    status_code = 422


class ConflictError(DomainError):
    status_code = 409


class ForbiddenError(DomainError):
    status_code = 403
