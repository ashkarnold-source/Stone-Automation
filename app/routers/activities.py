from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models import Activity, Prospect, SequenceEnrollment, SequenceStep
from app.services.gmail import send_email, is_authenticated

router = APIRouter(prefix="/activities")
templates = Jinja2Templates(directory="app/templates")

CHANNELS = ["email", "linkedin", "phone", "event", "note"]
OUTCOMES = ["no_response", "replied", "call_booked", "not_interested", "voicemail", "left_message"]


@router.post("/log")
def log_activity(
    prospect_id: int = Form(...),
    channel: str = Form(...),
    subject: str = Form(None),
    body: str = Form(None),
    outcome: str = Form(None),
    advance_sequence: bool = Form(False),
    db: Session = Depends(get_db),
):
    activity = Activity(
        prospect_id=prospect_id,
        channel=channel,
        subject=subject,
        body=body,
        outcome=outcome,
        activity_date=datetime.utcnow(),
    )
    db.add(activity)

    # Update prospect status if meaningful outcome
    prospect = db.query(Prospect).filter(Prospect.id == prospect_id).first()
    if prospect and outcome in ("replied", "call_booked") and prospect.status == "identified":
        prospect.status = "contacted"

    # Advance sequence enrollment if requested
    if advance_sequence:
        _advance_enrollment(prospect_id, outcome, db)

    db.commit()
    return RedirectResponse(url=f"/prospects/{prospect_id}", status_code=303)


@router.post("/send-email")
async def send_prospect_email(
    prospect_id: int = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    db: Session = Depends(get_db),
):
    prospect = db.query(Prospect).filter(Prospect.id == prospect_id).first()
    if not prospect or not prospect.email:
        raise HTTPException(status_code=400, detail="Prospect has no email address")

    if not is_authenticated():
        raise HTTPException(status_code=400, detail="Gmail not connected. Go to /auth/gmail to connect.")

    result = send_email(prospect.email, subject, body)

    if result["success"]:
        activity = Activity(
            prospect_id=prospect_id,
            channel="email",
            direction="outbound",
            subject=subject,
            body=body,
            outcome="no_response",
            activity_date=datetime.utcnow(),
        )
        db.add(activity)
        if prospect.status == "identified":
            prospect.status = "contacted"
        _advance_enrollment(prospect_id, "sent", db)
        db.commit()

    return RedirectResponse(url=f"/prospects/{prospect_id}", status_code=303)


def _advance_enrollment(prospect_id: int, outcome: str, db: Session):
    from datetime import date
    enrollment = (
        db.query(SequenceEnrollment)
        .filter(
            SequenceEnrollment.prospect_id == prospect_id,
            SequenceEnrollment.status == "active",
        )
        .first()
    )
    if not enrollment:
        return

    if outcome in ("replied", "call_booked", "not_interested"):
        enrollment.status = "replied" if outcome in ("replied", "call_booked") else "opted_out"
        return

    # Find next step
    next_step = (
        db.query(SequenceStep)
        .filter(
            SequenceStep.sequence_id == enrollment.sequence_id,
            SequenceStep.step_number == enrollment.current_step + 1,
        )
        .first()
    )

    if next_step:
        enrollment.current_step += 1
        enrollment.next_action_date = date.today().__class__.fromordinal(
            date.today().toordinal() + next_step.delay_days
        )
    else:
        enrollment.status = "completed"
