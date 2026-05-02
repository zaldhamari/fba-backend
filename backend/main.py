from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from backend.modules.routes import router

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="FBA Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "frontend" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "frontend" / "templates"))

app.include_router(router, prefix="/api")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
