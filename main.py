from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
MODELL_NAME = "qwen/qwen3.5-397b-a17b"
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

@app.get("/", response_class=HTMLResponse)
async def read_index():
    file_path = os.path.join(os.path.dirname(__file__), "abc.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Internal Server Error: abc.html not found</h1>", 500

@app.post("/evaluate")
async def evaluate_response(request: Request):
    data = await request.json()
    question = data.get("question")
    answer = data.get("answer")
    question_id = data.get("question_id")
    
    # Define prompt for the LLM
    prompt = f"""
    You are an autonomous survey agent for a workshop titled "AI Empowerment for Leaders" by Mehul Nanavati.
    Your goal is to evaluate the user's response to a specific question and decide if a follow-up is needed.
    
    Current Question: {question}
    User's Answer: {answer}
    
    CRITERIA for follow-up:
    1. If the rating is 5 or below, ask for specific reasons for the low score.
    2. If the answer for "Eureka moment", "Future topics", or "Improvements" is too vague (e.g., "good", "nothing", "okay"), ask them to elaborate.
    3. If the answer is interesting or highly positive, briefly acknowledge and move on.
    
    Response format: JSON ONLY
    {{
        "needs_follow_up": boolean,
        "follow_up_question": "string or null",
        "reason": "short explanation"
    }}
    """
    
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODELL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"}
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(INVOKE_URL, headers=headers, json=payload, timeout=30.0)
            llm_data = response.json()
            result = llm_data['choices'][0]['message']['content']
            print(f"Result: {result}")
            return JSONResponse(content=eval(result)) # Simple eval for JSON response format
    except Exception as e:
        print(f"Error calling LLM: {e}")
        return JSONResponse(content={"needs_follow_up": False, "follow_up_question": None, "reason": "Error"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
