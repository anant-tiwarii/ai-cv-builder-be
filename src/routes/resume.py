from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.resume import ResumeService, get_resume_service
from models.schemas import ATSResponse, Result
from typing import Annotated, List
from utils.security import decode_jwt_token
import logging

router = APIRouter()
bearer = HTTPBearer(auto_error=False)  # Set to False to handle OPTIONS requests properly

@router.post("/upload", response_model=ATSResponse)
async def upload_resume(
    file: Annotated[UploadFile, File(description="Resume PDF/DOC/DOCX file")],
    request: Request,
    service: ResumeService = Depends(get_resume_service)
):

    token = request.headers.get("Authorization").split(" ")[1]
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(('.pdf', '.doc', '.docx')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF, DOC or DOCX files are allowed"
        )
    
    # Process resume
    try:
        return await service.process_resume(file, token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing resume: {str(e)}"
        )
    
@router.get("/results", response_model=List[Result])
async def get_results(
    request: Request,
    service: ResumeService = Depends(get_resume_service)
):
    token = request.headers.get("Authorization").split(" ")[1]
    custHash = decode_jwt_token(token)["custHash"]
    return await service.get_results(custHash)

@router.get("/scores")
async def get_scores(
    request: Request,
    service: ResumeService = Depends(get_resume_service)
):
    try:
        token = request.headers.get("Authorization").split(" ")[1]
        custHash = decode_jwt_token(token)["custHash"]
        result = await service.get_results(custHash)
        logging.info(f"Retrieved scores for user {custHash}: {result}")
        if not result:
            return {"custHash": custHash, "results": []}
        return result
    except Exception as e:
        logging.error(f"Error in get_scores: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving scores: {str(e)}"
        )

    
