import os
from fastapi import FastAPI
from pydantic import BaseModel
from google import genai
from google.genai import types
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()
app = FastAPI()
clientGemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
clientTavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
class VideoRequest(BaseModel):
    youtube_url: str
    question: str = "Explain the statements in this video"

@app.post("/analyze-video")
def analyze_youtube(req: VideoRequest):
    response = clientGemini.models.generate_content(
        model="gemini-2.5-flash",
        contents=types.Content(
            parts=[
                types.Part(
                    file_data=types.FileData(
                        file_uri=req.youtube_url,
                        mime_type="video/*",
                    )
                ),
                types.Part(text=req.question),
            ]
        ),
    )
    return {"answer": response.text}

@app.post("/find_image")
def find_image(image_description: str):
    response = clientTavily.search(
        query=image_description,
        search_depth="advanced",
        include_images=True
    )
    return {"Image": response.get("images")[0]}