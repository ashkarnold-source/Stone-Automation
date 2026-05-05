from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.database import init_db
from app.routers import dashboard, prospects, activities, sequences, events, intelligence
from app.services.gmail import get_auth_url, handle_callback, is_authenticated
from app.services.scheduler import create_scheduler, run_email_sequences, check_gmail_replies, send_morning_digest
from app.auth import basic_auth_middleware

app = FastAPI(title="Stone Command Center")
app.add_middleware(BaseHTTPMiddleware, dispatch=basic_auth_middleware)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(dashboard.router)
app.include_router(prospects.router)
app.include_router(activities.router)
app.include_router(sequences.router)
app.include_router(events.router)
app.include_router(intelligence.router)

_scheduler = None


@app.on_event("startup")
def on_startup():
    global _scheduler
    init_db()
    _scheduler = create_scheduler()
    _scheduler.start()


@app.on_event("shutdown")
def on_shutdown():
    if _scheduler:
        _scheduler.shutdown()


# Manual job triggers (for testing without waiting for schedule)
@app.post("/scheduler/run-emails")
def trigger_emails():
    run_email_sequences()
    return RedirectResponse(url="/", status_code=303)


@app.post("/scheduler/run-replies")
def trigger_replies():
    check_gmail_replies()
    return RedirectResponse(url="/", status_code=303)


@app.post("/scheduler/run-digest")
def trigger_digest():
    send_morning_digest()
    return RedirectResponse(url="/", status_code=303)


@app.get("/auth/gmail")
def gmail_auth():
    return RedirectResponse(url=get_auth_url())


@app.get("/auth/gmail/callback")
def gmail_callback(code: str):
    handle_callback(code)
    return RedirectResponse(url="/")


@app.get("/health")
def health():
    return {"status": "ok", "gmail_connected": is_authenticated()}
