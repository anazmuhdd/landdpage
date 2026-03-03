from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import os

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def read_index():
    file_path = os.path.join(os.path.dirname(__file__), "abc.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Internal Server Error: abc.html not found</h1>", 500

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
