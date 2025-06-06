from fastapi import UploadFile, HTTPException, status
from models.schemas import ATSResponse
from docx import Document
import PyPDF2
import io
import requests
import json
from config import settings
from utils.security import decode_jwt_token
from services.database import get_db
from datetime import datetime
from google import genai

class ResumeService:
    def __init__(self):
        self.gemini_apikey = settings.gemini_apikey
        self.db = get_db()
        self.results = self.db["results"]

    async def get_results(self, custHash: str) -> dict:
        try:
            result = self.results.find_one({"custHash": custHash})
            
            if result is None:
                return {"custHash": custHash, "results": []}
            
            # Convert ObjectId to string and remove _id field
            result_dict = dict(result)
            if '_id' in result_dict:
                result_dict['_id'] = str(result_dict['_id'])
            
            # Convert datetime objects to ISO format strings
            if 'results' in result_dict:
                for item in result_dict['results']:
                    if 'timestamp' in item and isinstance(item['timestamp'], datetime):
                        item['timestamp'] = {"$date": item['timestamp'].isoformat()}
            return result_dict
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch results for customer."
            )

    def extract_text_from_file(self, file: UploadFile) -> str:
        # Read file content
        contents = file.file.read()
        text = ""
        
        # Extract text based on file type
        if file.filename.endswith('.pdf'):
            try:
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(contents))
                for page in pdf_reader.pages:
                    text += page.extract_text()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"Failed to read PDF: {str(e)}"
                )
                
        elif file.filename.endswith(('.doc', '.docx')):
            try:
                doc = Document(io.BytesIO(contents))
                text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
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

    async def process_resume(self, file: UploadFile, token: str) -> ATSResponse:
        try:
            # Read PDF content
            text = self.extract_text_from_file(file)

            prompt = f"""Your task is to check if the document is a resume or not and return JSON format. 
                                If a resume then analyze this document for ATS (Applicant Tracking System) compatibility and provide a detailed score and feedback in JSON format.
                                Provide for a valid resume:
                                1. ATS score (0-100) Be Brutal
                                2. Overall feedback
                                3. List of strengths
                                4. List of weaknesses
                                5. List of suggestions for improvement
                                
                                Use this JSON schema if NOT a resume:
                                result = {{
                                    "is_resume": 0, 
                                }}

                                Use this JSON schema for a Valid resume:
                                result = {{
                                    "is_resume": 1, 
                                    "score": ,
                                    "feedback": "",
                                    "strengths": [""],
                                    "weaknesses": [""],
                                    "suggestions": [""]
                                }}
                                Return: result

                                Respond only with valid JSON with the following fields. Do not write an introduction or summary.
                                NOTE: Adhere Strictly to the format given.

                                Document content: {text}
                                """

            # Call Llama3.2 for ATS scoring
            try:
                print("Calling Llama model for ATS analysis...")
                client = genai.Client(api_key=self.gemini_apikey)
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=prompt,
                )
                print("Llama model response:")
                print(response.text)
             
                # if response.status_code != 200:
                #     raise HTTPException(
                #         status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                #         detail=f"Failed to get ATS analysis from Llama model: {response.text}"
                #     )
                

                # Parse the response
                try:
                    content = response.text
                    content = content.replace("```json", "```")
                    if "```" in content:
                        json_content = content.split("```")[1].split("```")[0]
                    else:
                        json_content = content

                    result = json.loads(json_content)
                    print(result)

                except json.JSONDecodeError:
                            # If it's not valid JSON, use the raw response
                    result = {"is_resume": 0, "score": 0, "feedback": result["response"], "strengths": [], "weaknesses": [], "suggestions": []}
                
                if result["is_resume"] == 0:
                    return ATSResponse(is_resume = 0)

                # Validate the response format
                required_fields = ["score", "feedback", "strengths", "weaknesses", "suggestions"]
                for field in required_fields:
                    if field not in result:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Invalid response from Llama model: missing {field}"
                        )
                    
                custHash = decode_jwt_token(token)["custHash"]

                #store the result in a database collection with the custHash as the primary key 
                #and a result field which will be a map of map with file name as key a
                #and current timestamp as second key and the score as value 
                #when a new file is uploaded, the result should be appended with the new score and the new file name
                self.results.update_one(
                    {"custHash": custHash},
                    {
                        "$setOnInsert": {"custHash": custHash},
                        "$push": {"results": {
                            "filename": file.filename,
                            "timestamp": datetime.now(),
                            "score": float(result["score"])
                        }}
                    },
                    upsert=True
                )

                return ATSResponse(
                    is_resume=1,
                    score=float(result["score"]),
                    feedback=result["feedback"],
                    strengths=result["strengths"],
                    weaknesses=result["weaknesses"],
                    suggestions=result["suggestions"]
                )

            except requests.RequestException as e:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Failed to connect to Llama model: {str(e)}"
                )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred: {str(e)}"
            )

def get_resume_service() -> ResumeService:
    return ResumeService() 
