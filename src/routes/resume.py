import logging

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Annotated

from services.resume import ResumeService, get_resume_service
from models.schemas import ATSResponse
from utils.security import decode_jwt_token

router = APIRouter()
bearer = HTTPBearer()

ALLOWED_EXTENSIONS = (".pdf", ".doc", ".docx")


@router.post("/upload", response_model=ATSResponse)
async def upload_resume(
    file: Annotated[UploadFile, File(description="Resume PDF/DOC/DOCX file")],
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    service: ResumeService = Depends(get_resume_service),
):
    if not file.filename or not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF, DOC or DOCX files are allowed"
        )

    return await service.process_resume(file, credentials.credentials)


@router.get("/results")
async def get_results(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    service: ResumeService = Depends(get_resume_service),
):
    custHash = decode_jwt_token(credentials.credentials)["custHash"]
    return await service.get_results(custHash)


@router.get("/scores")
async def get_scores(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    service: ResumeService = Depends(get_resume_service),
):
    custHash = decode_jwt_token(credentials.credentials)["custHash"]
    result = await service.get_results(custHash)
    logging.info("Retrieved %d scores for user %s", len(result.get("results", [])), custHash)
    return result
