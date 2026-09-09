import io
import json
import logging
from datetime import datetime, timezone

import PyPDF2
from docx import Document
from fastapi import UploadFile, HTTPException, status
from google import genai
from google.genai import types
from pymongo.errors import DuplicateKeyError

from config import settings
from models.schemas import ATSResponse
from services.database import get_db
from utils.security import decode_jwt_token

PROMPT_TEMPLATE = """Your task is to check if the document is a resume or not and return JSON format.
If a resume then analyze this document for ATS (Applicant Tracking System) compatibility and provide a detailed score and feedback in JSON format.
Provide for a valid resume:
1. ATS score (0-100) Be Brutal
2. Overall feedback
3. List of strengths
4. List of weaknesses
5. List of suggestions for improvement

Use this JSON schema if NOT a resume:
{{"is_resume": 0}}

Use this JSON schema for a valid resume:
{{"is_resume": 1, "score": 0, "feedback": "", "strengths": [""], "weaknesses": [""], "suggestions": [""]}}

Respond only with valid JSON with the above fields. Do not write an introduction or summary.
NOTE: Adhere strictly to the format given.

Document content: {text}
"""

_indexes_ready = False


def _ensure_indexes(rate_limits):
    global _indexes_ready
    if _indexes_ready:
        return
    rate_limits.create_index("custHash", unique=True)
    rate_limits.create_index("createdAt", expireAfterSeconds=86400)
    _indexes_ready = True


class ResumeService:
    def __init__(self):
        self.db = get_db()
        self.results = self.db["results"]
        self.rate_limits = self.db["rate_limits"]
        _ensure_indexes(self.rate_limits)

    async def get_results(self, custHash: str) -> dict:
        try:
            result = self.results.find_one({"custHash": custHash})
        except Exception:
            logging.exception("Failed to fetch results for %s", custHash)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to fetch results for customer."
            )

        if result is None:
            return {"custHash": custHash, "results": []}

        return {"custHash": custHash, "results": result.get("results", [])}

    def extract_text_from_file(self, file: UploadFile) -> str:
        contents = file.file.read()
        filename = (file.filename or "").lower()
        text = ""

        if filename.endswith(".pdf"):
            try:
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(contents))
                for page in pdf_reader.pages:
                    text += page.extract_text() or ""
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to read PDF: {str(e)}"
                )

        elif filename.endswith((".doc", ".docx")):
            try:
                doc = Document(io.BytesIO(contents))
                text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to read DOC/DOCX: {str(e)}"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file format. Please upload PDF, DOC or DOCX files only."
            )

        if not text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File appears to be empty or contains no extractable text"
            )

        return text.strip()

    def _score_with_gemini(self, text: str) -> dict:
        client = genai.Client(api_key=settings.gemini_apikey)
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=PROMPT_TEMPLATE.format(text=text),
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
        except Exception as e:
            logging.exception("Gemini request failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to reach the scoring model: {str(e)}"
            )

        content = (response.text or "").strip()
        if "```" in content:
            content = content.replace("```json", "```").split("```")[1]

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logging.error("Scoring model returned non-JSON output: %s", content[:500])
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Scoring model returned an unreadable response. Please try again."
            )

    async def process_resume(self, file: UploadFile, token: str) -> ATSResponse:
        custHash = decode_jwt_token(token)["custHash"]

        try:
            self.rate_limits.insert_one(
                {"custHash": custHash, "createdAt": datetime.now(timezone.utc)}
            )
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. You can only check 1 resume per day."
            )

        try:
            text = self.extract_text_from_file(file)
            result = self._score_with_gemini(text)

            if not result.get("is_resume"):
                return ATSResponse(is_resume=False)

            missing = [
                f for f in ("score", "feedback", "strengths", "weaknesses", "suggestions")
                if f not in result
            ]
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Invalid response from scoring model: missing {', '.join(missing)}"
                )

            self.results.update_one(
                {"custHash": custHash},
                {
                    "$setOnInsert": {"custHash": custHash},
                    "$push": {"results": {
                        "filename": file.filename,
                        "timestamp": datetime.now(timezone.utc),
                        "score": float(result["score"])
                    }}
                },
                upsert=True
            )

            return ATSResponse(
                is_resume=True,
                score=float(result["score"]),
                feedback=result["feedback"],
                strengths=result["strengths"],
                weaknesses=result["weaknesses"],
                suggestions=result["suggestions"],
            )

        except HTTPException:
            self.rate_limits.delete_one({"custHash": custHash})
            raise
        except Exception as e:
            self.rate_limits.delete_one({"custHash": custHash})
            logging.exception("Unexpected failure while processing resume")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred: {str(e)}"
            )


def get_resume_service() -> ResumeService:
    return ResumeService()
