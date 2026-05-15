import hmac
import logging
import os
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from backend.modules.routes import router

BASE_DIR = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("siftly")

API_KEY = os.environ.get("API_KEY", "")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api"):
            if not API_KEY:
                log.warning("API_KEY env var not set — rejecting all /api requests")
                return JSONResponse({"detail": "Server misconfigured"}, status_code=500)
            incoming = request.headers.get("X-API-Key", "")
            if not hmac.compare_digest(incoming.encode(), API_KEY.encode()):
                log.warning("Unauthorized request from %s to %s", _client_ip(request), request.url.path)
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """60 requests per minute per IP on /api routes (in-memory, single-process)."""

    def __init__(self, app, calls: int = 60, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self._log: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api"):
            return await call_next(request)
        ip = _client_ip(request)
        now = time.monotonic()
        window_start = now - self.period
        self._log[ip] = [t for t in self._log[ip] if t > window_start]
        if len(self._log[ip]) >= self.calls:
            log.warning("Rate limit hit for %s", ip)
            return JSONResponse({"detail": "Too many requests"}, status_code=429)
        self._log[ip].append(now)
        return await call_next(request)


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        ms = (time.monotonic() - start) * 1000
        log.info("%s %s %d  %.0fms  %s",
                 request.method, request.url.path,
                 response.status_code, ms, _client_ip(request))
        return response


app = FastAPI(title="Siftly Backend")

# Order matters: rate-limit → auth → logging → CORS → routes
app.add_middleware(RequestLogMiddleware)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(RateLimitMiddleware, calls=60, period=60)
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


@app.get("/health")
async def health():
    return {"status": "ok"}
