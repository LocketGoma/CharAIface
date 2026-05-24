from fastapi import APIRouter

from backend.app.services.system_status_service import SystemStatusService


router = APIRouter(prefix="/system", tags=["system"])
status_service = SystemStatusService()


@router.get("/status")
def get_system_status() -> dict:
    return status_service.build_payload(sample_seconds=0.2)
