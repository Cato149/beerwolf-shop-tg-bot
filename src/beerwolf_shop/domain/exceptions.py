"""Domain exceptions raised by use cases and mapped in presentation."""


class DomainError(Exception):
    """Base class for expected business failures."""


class OrderNotFoundError(DomainError):
    pass


class UserNotFoundError(DomainError):
    pass


class AccessDeniedError(DomainError):
    pass


class InvalidStatusTransitionError(DomainError):
    pass


class ActiveCommissionExistsError(DomainError):
    """The customer already has an unfinished primary commission."""


class GithubIntegrationError(DomainError):
    pass


class AuthError(DomainError):
    pass


class DuplicateDeliveryError(DomainError):
    """GitHub webhook delivery was already processed."""
