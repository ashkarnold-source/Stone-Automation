from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta

from app.database import get_db
from app.models import Prospect, Activity, SequenceEnrollment, SequenceStep, Event

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PIPELINE_STAGES = ["identified", "contacted", "engaged", "proposal", "closed_won"]
STAGE_LABELS = {
    "identified": "Identified",
    "contacted": "Contacted",
    "engaged": "Engaged",
    "proposal": "Proposal",
    "closed_won": "Closed",
}


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    today = date.today()

    # Pipeline counts
    pipeline = {}
    for stage in PIPELINE_STAGES:
        pipeline[stage] = db.query(Prospect).filter(Prospect.status == stage).count()

    # Today's queue — active enrollments due today or overdue
    due_enrollments = (
        db.query(SequenceEnrollment)
        .filter(
            SequenceEnrollment.status == "active",
            SequenceEnrollment.next_action_date <= today,
        )
        .all()
    )

    queue = {"email": [], "linkedin": [], "phone": [], "total": 0}
    for enrollment in due_enrollments:
        step = (
            db.query(SequenceStep)
            .filter(
                SequenceStep.sequence_id == enrollment.sequence_id,
                SequenceStep.step_number == enrollment.current_step,
            )
            .first()
        )
        if step and step.channel in queue:
            days_over = (today - enrollment.next_action_date).days
            queue[step.channel].append({
                "prospect": enrollment.prospect,
                "step": step,
                "enrollment": enrollment,
                "days_overdue": days_over,
            })
            queue["total"] += 1

    # Recent activity (last 7 days)
    week_ago = date.today() - timedelta(days=7)
    recent_activities = (
        db.query(Activity)
        .filter(Activity.activity_date >= week_ago)
        .order_by(Activity.activity_date.desc())
        .limit(10)
        .all()
    )

    # Upcoming events (next 90 days)
    ninety_days = today + timedelta(days=90)
    upcoming_events = (
        db.query(Event)
        .filter(Event.event_date >= today, Event.event_date <= ninety_days)
        .order_by(Event.event_date)
        .limit(3)
        .all()
    )

    total_prospects = db.query(Prospect).count()
    active_sequences = db.query(SequenceEnrollment).filter(SequenceEnrollment.status == "active").count()

    from app.services.scheduler import job_status
    from app.services.gmail import is_authenticated

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "pipeline": pipeline,
        "stage_labels": STAGE_LABELS,
        "queue": queue,
        "recent_activities": recent_activities,
        "upcoming_events": upcoming_events,
        "total_prospects": total_prospects,
        "active_sequences": active_sequences,
        "today": today,
        "job_status": job_status,
        "gmail_connected": is_authenticated(),
    })
