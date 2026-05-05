from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, timedelta

from app.database import get_db
from app.models import Sequence, SequenceStep, SequenceEnrollment, Prospect

router = APIRouter(prefix="/sequences")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def list_sequences(request: Request, db: Session = Depends(get_db)):
    sequences = db.query(Sequence).order_by(Sequence.created_at.desc()).all()
    return templates.TemplateResponse("sequences.html", {
        "request": request,
        "sequences": sequences,
    })


@router.post("/create")
def create_sequence(
    name: str = Form(...),
    description: str = Form(None),
    db: Session = Depends(get_db),
):
    seq = Sequence(name=name, description=description)
    db.add(seq)
    db.commit()
    db.refresh(seq)
    return RedirectResponse(url=f"/sequences/{seq.id}", status_code=303)


@router.get("/{sequence_id}", response_class=HTMLResponse)
def sequence_detail(request: Request, sequence_id: int, db: Session = Depends(get_db)):
    sequence = db.query(Sequence).filter(Sequence.id == sequence_id).first()
    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence not found")

    active_count = db.query(SequenceEnrollment).filter(
        SequenceEnrollment.sequence_id == sequence_id,
        SequenceEnrollment.status == "active"
    ).count()

    return templates.TemplateResponse("sequence_detail.html", {
        "request": request,
        "sequence": sequence,
        "active_count": active_count,
    })


@router.post("/{sequence_id}/steps/add")
def add_step(
    sequence_id: int,
    channel: str = Form(...),
    delay_days: int = Form(0),
    subject_template: str = Form(None),
    body_template: str = Form(None),
    db: Session = Depends(get_db),
):
    last_step = (
        db.query(SequenceStep)
        .filter(SequenceStep.sequence_id == sequence_id)
        .order_by(SequenceStep.step_number.desc())
        .first()
    )
    next_num = (last_step.step_number + 1) if last_step else 1

    step = SequenceStep(
        sequence_id=sequence_id,
        step_number=next_num,
        channel=channel,
        delay_days=delay_days,
        subject_template=subject_template,
        body_template=body_template,
    )
    db.add(step)
    db.commit()
    return RedirectResponse(url=f"/sequences/{sequence_id}", status_code=303)


@router.post("/{sequence_id}/enroll")
def enroll_prospect(
    sequence_id: int,
    prospect_id: int = Form(...),
    db: Session = Depends(get_db),
):
    sequence = db.query(Sequence).filter(Sequence.id == sequence_id).first()
    if not sequence or not sequence.steps:
        raise HTTPException(status_code=400, detail="Sequence has no steps")

    existing = db.query(SequenceEnrollment).filter(
        SequenceEnrollment.prospect_id == prospect_id,
        SequenceEnrollment.sequence_id == sequence_id,
        SequenceEnrollment.status == "active",
    ).first()
    if existing:
        return RedirectResponse(url=f"/prospects/{prospect_id}", status_code=303)

    first_step = sequence.steps[0]
    enrollment = SequenceEnrollment(
        prospect_id=prospect_id,
        sequence_id=sequence_id,
        current_step=1,
        next_action_date=date.today() + timedelta(days=first_step.delay_days),
        status="active",
    )
    db.add(enrollment)
    db.commit()
    return RedirectResponse(url=f"/prospects/{prospect_id}", status_code=303)
