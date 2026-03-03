from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Feedback Survey Chatbot")

# CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Survey Questions from the Google Form
SURVEY_QUESTIONS = [
    {
        "id": "name",
        "question": "Name of Member/Spouse/YNG (Optional)",
        "type": "text",
        "required": False,
        "placeholder": "Enter your name (or skip if you prefer to remain anonymous)"
    },
    {
        "id": "overall_rating",
        "question": "Overall rating for the workshop",
        "type": "rating",
        "required": True,
        "scale": 5,
        "description": "Please rate from 1 (Poor) to 5 (Excellent)"
    },
    {
        "id": "engaged_peers",
        "question": "I engaged with peers",
        "type": "rating",
        "required": True,
        "scale": 5,
        "description": "Rate your agreement: 1 (Strongly Disagree) to 5 (Strongly Agree)"
    },
    {
        "id": "content_compelling",
        "question": "The content shared was compelling",
        "type": "rating",
        "required": True,
        "scale": 5,
        "description": "Rate your agreement: 1 (Strongly Disagree) to 5 (Strongly Agree)"
    },
    {
        "id": "open_to_ideas",
        "question": "I was open to new ideas and perspectives",
        "type": "rating",
        "required": True,
        "scale": 5,
        "description": "Rate your agreement: 1 (Strongly Disagree) to 5 (Strongly Agree)"
    },
    {
        "id": "delivered_value",
        "question": "I feel the experience delivered value",
        "type": "rating",
        "required": True,
        "scale": 5,
        "description": "Rate your agreement: 1 (Strongly Disagree) to 5 (Strongly Agree)"
    },
    {
        "id": "extraordinary_resource",
        "question": "I found this to be an extraordinary resource",
        "type": "rating",
        "required": True,
        "scale": 5,
        "description": "Rate your agreement: 1 (Strongly Disagree) to 5 (Strongly Agree)"
    },
    {
        "id": "eureka_moment",
        "question": "What was the Eureka moment/Key Learning?",
        "type": "textarea",
        "required": True,
        "placeholder": "Describe your most impactful takeaway from the workshop..."
    },
    {
        "id": "explore_further",
        "question": "What specific topics, challenges, or questions would you like to explore further after this workshop?",
        "type": "textarea",
        "required": True,
        "placeholder": "Share what you'd like to dive deeper into..."
    },
    {
        "id": "improvements",
        "question": "If you were in charge of the event, what would you do or do differently?",
        "type": "textarea",
        "required": True,
        "placeholder": "Share your suggestions for improvement..."
    }
]

NVIDIA_NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY")
NVIDIA_NIM_MODEL = os.getenv("NVIDIA_NIM_MODEL", "meta/llama-3.1-8b-instruct")
NVIDIA_NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

class ValidationRequest(BaseModel):
    question: str
    answer: str
    question_type: str
    previous_qa: List[Dict[str, str]] = []
    is_follow_up: bool = False

class ValidationResponse(BaseModel):
    is_valid: bool
    follow_up_needed: bool
    follow_up_question: Optional[str] = None
    feedback: Optional[str] = None
    message: str

class SurveySubmission(BaseModel):
    responses: Dict[str, str]

@app.get("/")
async def root():
    return {"message": "Feedback Survey Chatbot API", "status": "running"}

@app.get("/questions")
async def get_questions():
    """Get all survey questions"""
    return {"questions": SURVEY_QUESTIONS, "total": len(SURVEY_QUESTIONS)}

@app.post("/validate-answer", response_model=ValidationResponse)
async def validate_answer(request: ValidationRequest):
    """
    LLM-driven validation with self-driven loop
    Returns: is_valid, follow_up_needed, follow_up_question (if needed)
    """
    if not NVIDIA_NIM_API_KEY:
        raise HTTPException(status_code=500, detail="NVIDIA NIM API key not configured")
    
    # Build context from previous Q&A
    context = ""
    if request.previous_qa:
        context = "Previous conversation:\n"
        for qa in request.previous_qa:
            context += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"
    
    # Determine validation criteria based on question type
    validation_criteria = ""
    if request.question_type == "rating":
        validation_criteria = """
        - Answer must be a number between 1-5
        - Accept numeric digits (1, 2, 3, 4, 5) or spelled out numbers
        - If unclear, ask for clarification with specific number
        """
    elif request.question_type == "textarea":
        validation_criteria = """
        - Answer should be meaningful and substantive (at least a few words)
        - Should directly address the question asked
        - If answer is too vague, brief, or off-topic, request specific details
        - If answer is good and complete, accept it
        """
    else:
        validation_criteria = """
        - Answer should be appropriate to the question
        - Optional fields can be skipped or have brief answers
        """
    
    # Construct prompt for LLM - NO THINKING PARAMETER
    system_prompt = """You are a survey validation assistant. Your task is to:
1. Check if the user's answer is valid and appropriate for the question
2. Determine if follow-up is needed to clarify or expand the answer
3. Provide constructive feedback

Respond ONLY in this JSON format:
{
    "is_valid": true/false,
    "follow_up_needed": true/false,
    "follow_up_question": "specific follow-up question if needed, otherwise null",
    "feedback": "brief feedback on the answer quality",
    "message": "user-friendly message about the validation result"
}

Rules:
- follow_up_needed should be true ONLY if the answer is vague, incomplete, or needs clarification
- If answer is good, set follow_up_needed to false
- Be helpful but concise
- Do not include any text outside the JSON"""

    user_prompt = f"""{context}
Current Question: {request.question}
Question Type: {request.question_type}
User's Answer: {request.answer}

Validation Criteria:
{validation_criteria}

Analyze the answer and respond in the required JSON format. Is this answer acceptable? Does it need follow-up?"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                NVIDIA_NIM_URL,
                headers={
                    "Authorization": f"Bearer {NVIDIA_NIM_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": NVIDIA_NIM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500
                    # NO reasoning/thinking parameter included
                }
            )
            
            if response.status_code != 200:
                error_detail = response.text
                raise HTTPException(status_code=502, detail=f"NVIDIA NIM error: {error_detail}")
            
            result = response.json()
            llm_response = result["choices"][0]["message"]["content"]
            
            # Parse JSON response
            import json
            try:
                # Extract JSON from potential markdown code blocks
                content = llm_response.strip()
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                validation_result = json.loads(content.strip())
                
                return ValidationResponse(
                    is_valid=validation_result.get("is_valid", True),
                    follow_up_needed=validation_result.get("follow_up_needed", False),
                    follow_up_question=validation_result.get("follow_up_question"),
                    feedback=validation_result.get("feedback"),
                    message=validation_result.get("message", "Answer processed")
                )
            except json.JSONDecodeError:
                # Fallback if LLM doesn't return valid JSON
                return ValidationResponse(
                    is_valid=True,
                    follow_up_needed=False,
                    follow_up_question=None,
                    feedback="Answer accepted",
                    message="Thank you for your response!"
                )
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="NVIDIA NIM request timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation error: {str(e)}")

@app.post("/submit-survey")
async def submit_survey(submission: SurveySubmission):
    """Submit completed survey"""
    # Here you would typically save to database
    # For now, return success
    return {
        "status": "success",
        "message": "Thank you for completing the survey! Your feedback has been recorded.",
        "responses_count": len(submission.responses)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))