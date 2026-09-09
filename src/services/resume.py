import io
import logging
import time
from datetime import datetime, timezone

import PyPDF2
from docx import Document
from docx.oxml.ns import qn
from fastapi import UploadFile, HTTPException, status
from google import genai
from google.genai import errors, types
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from config import settings
from models.schemas import ATSResponse
from services.database import get_db
from utils.security import decode_jwt_token

# Dimension -> (weight out of 100, what a 0 and a 10 look like).
# The model rates each dimension 0-10; the total is computed in code so the
# score is arithmetically consistent rather than something the model guesses.
RUBRIC: tuple[tuple[str, int, str], ...] = (
    (
        "parseability", 25,
        "How cleanly an ATS can extract the content. 10 = single column, standard "
        "section headings, plain bullets, no tables/text boxes/graphics/headers or "
        "footers, machine-readable dates. 0 = multi-column or heavily graphical "
        "layout whose reading order would scramble on extraction.",
    ),
    (
        "keyword_coverage", 20,
        "Presence of concrete, role-relevant skills, tools and domain terms an ATS "
        "keyword filter would look for. 10 = specific technologies and responsibilities "
        "stated in the words a job posting would use. 0 = vague duties with no "
        "identifiable hard skills.",
    ),
    (
        "quantified_impact", 20,
        "Whether achievements carry numbers and outcomes. 10 = most bullets state a "
        "measurable result (scale, latency, revenue, percentage, headcount). "
        "0 = a list of responsibilities with no evidence of impact.",
    ),
    (
        "structure_and_completeness", 15,
        "Whether the expected sections exist and are ordered sensibly, with continuous "
        "dated history. 10 = contact, experience, skills and education all present, "
        "reverse-chronological, no unexplained gaps. 0 = key sections missing.",
    ),
    (
        "clarity_and_formatting", 10,
        "Consistency and density. 10 = uniform tense and bullet style, length matched "
        "to experience, no typos. 0 = inconsistent formatting, wall of text, or far "
        "too thin or bloated for the stated career stage.",
    ),
    (
        "contact_and_links", 10,
        "Reachability and verifiable presence. 10 = email, phone and relevant "
        "professional links (LinkedIn/GitHub/portfolio) as appropriate to the field. "
        "0 = no reliable way to contact or verify the candidate.",
    ),
)

RUBRIC_WEIGHTS = {name: weight for name, weight, _ in RUBRIC}

# Fixed so the same document scores the same on repeat uploads.
SCORING_SEED = 7

RETRY_ATTEMPTS = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RubricRatings(BaseModel):
    parseability: int
    keyword_coverage: int
    quantified_impact: int
    structure_and_completeness: int
    clarity_and_formatting: int
    contact_and_links: int


class ScoringResult(BaseModel):
    is_resume: bool
    ratings: RubricRatings
    feedback: str
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]


def weighted_breakdown(ratings: RubricRatings) -> dict[str, float]:
    return {
        name: round(min(max(getattr(ratings, name), 0), 10) / 10 * weight, 1)
        for name, weight in RUBRIC_WEIGHTS.items()
    }

_RUBRIC_TEXT = "\n".join(
    f"- {name} (worth {weight} of the final 100): {anchor}" for name, weight, anchor in RUBRIC
)

PROMPT_TEMPLATE = f"""You are a strict ATS (Applicant Tracking System) auditor. Decide whether the
document is a resume, and if it is, rate it against a fixed rubric.

Rate each dimension on an integer scale of 0 to 10, judging ONLY that dimension:

{_RUBRIC_TEXT}

Calibration — apply these consistently, and be brutal:
- 9-10 is reserved for genuinely exceptional work; most real resumes score 4-7 on a
  given dimension.
- Rate what is actually on the page. Do not credit skills that are merely listed but
  never evidenced in the experience section.
- Do not compute a total score. The rubric weights are applied separately.

feedback must be 2-3 sentences of overall assessment. strengths, weaknesses and
suggestions must each contain 3-5 specific, actionable entries that refer to this
document rather than to resumes in general.

If the document is NOT a resume, set is_resume to false, set every rating to 0, leave
feedback as an empty string, and return empty lists.

Document content:
{{text}}
"""

def _block_lines(element):
    """Yield text lines from a docx block container, in document order.

    Walks w:p and w:tbl children and recurses into table cells. Collecting every
    w:t descendant of a paragraph (rather than reading Paragraph.text) also picks
    up content that python-docx skips, notably text boxes.
    """
    for child in element.iterchildren():
        if child.tag == qn("w:p"):
            line = "".join(node.text or "" for node in child.iter(qn("w:t"))).strip()
            if line:
                yield line
        elif child.tag == qn("w:tbl"):
            for row in child.iterchildren(qn("w:tr")):
                cells = [
                    " ".join(_block_lines(cell))
                    for cell in row.iterchildren(qn("w:tc"))
                ]
                line = " | ".join(cell for cell in cells if cell)
                if line:
                    yield line


def extract_docx_text(doc) -> str:
    """Full visible text of a .docx, including tables, text boxes and headers.

    python-docx's doc.paragraphs covers only body-level paragraphs, so a resume
    laid out in a table extracts as little more than the candidate's name.
    """
    body = list(_block_lines(doc.element.body))

    # Contact details are often parked in the header, which is a separate part.
    # Headers repeat per section, so keep only the first occurrence of each line.
    header, footer = [], []
    seen = set()
    for section in doc.sections:
        for part, bucket in ((section.header, header), (section.footer, footer)):
            for line in _block_lines(part._element):
                if line not in seen:
                    seen.add(line)
                    bucket.append(line)

    return "\n".join(header + body + footer)


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

        # Shape kept as the frontend already integrates it: stringified _id and
        # timestamps wrapped as Mongo extended JSON.
        result_dict = dict(result)
        result_dict["_id"] = str(result_dict["_id"])
        for item in result_dict.get("results", []):
            timestamp = item.get("timestamp")
            if isinstance(timestamp, datetime):
                item["timestamp"] = {"$date": timestamp.isoformat()}
        return result_dict

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
                text = extract_docx_text(Document(io.BytesIO(contents)))
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

    def _score_with_gemini(self, text: str) -> ScoringResult:
        client = genai.Client(api_key=settings.gemini_apikey)
        config = types.GenerateContentConfig(
            temperature=0,
            seed=SCORING_SEED,
            response_mime_type="application/json",
            response_schema=ScoringResult,
        )

        for attempt in range(RETRY_ATTEMPTS):
            try:
                response = client.models.generate_content(
                    model=settings.gemini_model,
                    contents=PROMPT_TEMPLATE.format(text=text),
                    config=config,
                )
                break
            except errors.APIError as e:
                retryable = e.code in RETRYABLE_STATUS and attempt < RETRY_ATTEMPTS - 1
                if not retryable:
                    logging.exception("Gemini request failed")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Failed to reach the scoring model: {str(e)}"
                    )
                logging.warning("Gemini returned %s, retrying (attempt %d)", e.code, attempt + 1)
                time.sleep(2 ** attempt)
            except Exception as e:
                logging.exception("Gemini request failed")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Failed to reach the scoring model: {str(e)}"
                )

        result = response.parsed
        if not isinstance(result, ScoringResult):
            logging.error("Scoring model returned unusable output: %s", (response.text or "")[:500])
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Scoring model returned an unreadable response. Please try again."
            )
        return result

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

            if not result.is_resume:
                return ATSResponse(is_resume=False)

            breakdown = weighted_breakdown(result.ratings)
            score = round(sum(breakdown.values()), 1)

            self.results.update_one(
                {"custHash": custHash},
                {
                    "$setOnInsert": {"custHash": custHash},
                    "$push": {"results": {
                        "filename": file.filename,
                        "timestamp": datetime.now(timezone.utc),
                        "score": score,
                        "breakdown": breakdown,
                    }}
                },
                upsert=True
            )

            return ATSResponse(
                is_resume=True,
                score=score,
                breakdown=breakdown,
                feedback=result.feedback,
                strengths=result.strengths,
                weaknesses=result.weaknesses,
                suggestions=result.suggestions,
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
