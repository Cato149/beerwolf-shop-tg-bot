"""Map domain exceptions to stable HTTP status codes and detail strings."""

from beerwolf_shop.domain.exceptions import (
    AccessDeniedError,
    ActiveCommissionExistsError,
    AuthError,
    DomainError,
    DuplicateDeliveryError,
    GithubIntegrationError,
    InvalidStatusTransitionError,
    OrderNotFoundError,
    UserNotFoundError,
)

# Client-side GitHub errors: bad input or order state, not an upstream outage.
_GITHUB_CLIENT_ERRORS = frozenset(
    {
        "invalid_repo_url",
        "progress_unavailable",
        "repo_not_linked",
        "github_project_unknown",
        "github_project_already_linked",
        "github_status_option_missing",
        "github_project_add_failed",
    }
)


def domain_error_response(exc: DomainError) -> tuple[int, str]:
    """Return `(status_code, detail)` for a domain failure.

    Upstream GitHub transport failures are 502 so GitHub webhooks are retried;
    validation / business GitHub errors stay 400.
    """
    if isinstance(exc, AuthError):
        return 401, str(exc) or "unauthorized"
    if isinstance(exc, AccessDeniedError):
        return 403, "forbidden"
    if isinstance(exc, OrderNotFoundError):
        return 404, "order_not_found"
    if isinstance(exc, UserNotFoundError):
        return 404, "user_not_found"
    if isinstance(exc, DuplicateDeliveryError):
        return 409, "duplicate_delivery"
    if isinstance(exc, ActiveCommissionExistsError):
        return 409, "active_commission_exists"
    if isinstance(exc, InvalidStatusTransitionError):
        return 409, str(exc) or "invalid_status_transition"
    if isinstance(exc, GithubIntegrationError):
        detail = str(exc) or "github_error"
        if detail in _GITHUB_CLIENT_ERRORS:
            return 400, detail
        return 502, detail
    return 400, str(exc) or exc.__class__.__name__
