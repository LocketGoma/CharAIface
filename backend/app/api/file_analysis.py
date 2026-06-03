from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.file_analysis_service import (
    FileAnalysisError,
    FileAnalysisRequest,
    FileAnalysisService,
)


router = APIRouter(prefix="/file", tags=["file"])
file_analysis_service = FileAnalysisService()


class AnalyzeFileRequest(BaseModel):
    file_path: str
    sample_size: int = Field(default=10, ge=0, le=100)
    include_value_frequencies: bool = True
    save_result: bool = False
    output_format: str = "json"


@router.post("/analyze")
def analyze_file(request: AnalyzeFileRequest) -> dict:
    try:
        return file_analysis_service.analyze(
            FileAnalysisRequest(
                file_path=request.file_path,
                sample_size=request.sample_size,
                include_value_frequencies=request.include_value_frequencies,
                save_result=request.save_result,
                output_format=request.output_format,
            )
        )
    except FileAnalysisError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
