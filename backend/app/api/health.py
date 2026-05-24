from fastapi import APIRouter, Response

from backend.app.services.health_service import HealthService


router = APIRouter(tags=["health"])

health_service = HealthService()


@router.get("/health")
def health(response: Response) -> dict:
    payload = health_service.build_payload()
    response.status_code = health_service.status_code_for_payload(payload)
    return payload
