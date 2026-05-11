import json
import os
from typing import Any
from io import BytesIO

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pypdf import PdfReader 

load_dotenv()

def extract_pdf(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

def analyze_resume(resume_text: str, job_description: str) -> dict[str, Any] | None:
    client = OpenAI()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    prompt = {
        "job_description": job_description,
        "resume_text": resume_text,
        "required_output": {
            "matching_score": "integer 0-100",
            "summary": "brief fit summary",
            "education": ["degree in field from institution"],
            "experience": ["job title at company for duration"],
            "matched_skills": ["skill"],
            "knowledge": ["knowledge area"],
            "tools": ["tool"],
            "concerns": ["concern"],
        },
    }
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that analyzes resumes against job descriptions. Respond with valid JSON only.",
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt),
                },
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {}
        result["analysis_engine"] = f"llm:{model}"
        return result
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        print(f"Details: {e.__dict__}") # Log the full exception details for debugging
        return None


# FastAPI App and HTTP Handler
app = FastAPI(title="Resume Analyzer", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ResumeAnalyzerHandler:
    """HTTP request handler for resume analysis"""
    
    @staticmethod
    def extract_pdf_from_bytes(pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes"""
        reader = PdfReader(BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    
    @staticmethod
    async def handle_analyze(resume: UploadFile, job_description_text: str) -> dict[str, Any]:
        """Handle resume analysis request"""
        resume_content = await resume.read()
        resume_text = ResumeAnalyzerHandler.extract_pdf_from_bytes(resume_content)
        result = analyze_resume(resume_text, job_description_text)
        if result:
            return result
        else:
            raise HTTPException(status_code=400, detail="Failed to analyze resume")


# API Endpoints
@app.get("/")
async def serve_index():
    """Serve the index.html file."""
    return FileResponse("index.html")


@app.post("/analyze")
async def analyze_endpoint(resume: UploadFile = File(...), job_description_text: str = Form(...)):
    """Analyze a resume against a job description."""
    try:
        handler = ResumeAnalyzerHandler()
        return await handler.handle_analyze(resume, job_description_text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

    
def main():
    JD_PATH = "JD.txt"
    RESUME_PATH = "resume.pdf"
    
    if not os.path.exists(JD_PATH):
        print(f"Job description file not found: {JD_PATH}")
        return
    if not os.path.exists(RESUME_PATH):
        print(f"Resume file not found: {RESUME_PATH}")
        return 
    
    with open(JD_PATH, "r") as f:
        job_description = f.read()
    
    resume_text = extract_pdf(RESUME_PATH)
    
    result = analyze_resume(resume_text, job_description)
    if result:
        print(json.dumps(result, indent=2))
    else:
        print("Failed to analyze resume.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)