"""Liveness endpoint."""

from fastapi import APIRouter

from beerwolf_shop.presentation.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns `ok` when the HTTP process is up. Does not query Postgres or GitHub.",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
