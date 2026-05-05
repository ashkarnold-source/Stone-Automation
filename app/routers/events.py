from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date

from app.database import get_db
from app.models import Event, EventProspect, Prospect
from app.services.csv_import import parse_csv

router = APIRouter(prefix="/events")
templates = Jinja2Templates(directory="app/templates")

EVENT_TYPES = ["conference", "trade_show", "association", "webinar", "networking"]
ATTENDEE_STATUSES = ["targeting", "reached_out", "confirmed_attending", "met", "following_up", "converted"]


@router.get("", response_class=HTMLResponse)
def list_events(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    upcoming = db.query(Event).filter(Event.event_date >= today).order_by(Event.event_date).all()
    past = db.query(Event).filter(Event.event_date < today).order_by(Event.event_date.desc()).limit(5).all()

    return templates.TemplateResponse("events.html", {
        "request": request,
        "upcoming": upcoming,
        "past": past,
        "event_types": EVENT_TYPES,
    })


@router.post("/create")
def create_event(
    name: str = Form(...),
    event_date: str = Form(...),
    end_date: str = Form(None),
    location: str = Form(None),
    event_type: str = Form(None),
    website: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
):
    event = Event(
        name=name,
        event_date=date.fromisoformat(event_date),
        end_date=date.fromisoformat(end_date) if end_date else None,
        location=location,
        event_type=event_type,
        website=website,
        notes=notes,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return RedirectResponse(url=f"/events/{event.id}", status_code=303)


@router.get("/{event_id}", response_class=HTMLResponse)
def event_detail(request: Request, event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    links = (
        db.query(EventProspect)
        .filter(EventProspect.event_id == event_id)
        .all()
    )

    # Prospects not yet linked to this event
    linked_ids = [l.prospect_id for l in links]
    available = db.query(Prospect).filter(~Prospect.id.in_(linked_ids)).order_by(Prospect.company_name).all()

    return templates.TemplateResponse("event_detail.html", {
        "request": request,
        "event": event,
        "links": links,
        "available_prospects": available,
        "attendee_statuses": ATTENDEE_STATUSES,
    })


@router.post("/{event_id}/add-prospect")
def add_prospect_to_event(
    event_id: int,
    prospect_id: int = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(EventProspect).filter(
        EventProspect.event_id == event_id,
        EventProspect.prospect_id == prospect_id,
    ).first()
    if not existing:
        db.add(EventProspect(event_id=event_id, prospect_id=prospect_id))
        db.commit()
    return RedirectResponse(url=f"/events/{event_id}", status_code=303)


@router.post("/{event_id}/prospects/{link_id}/update")
def update_attendee_status(
    event_id: int,
    link_id: int,
    status: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
):
    link = db.query(EventProspect).filter(EventProspect.id == link_id).first()
    if link:
        link.status = status
        if notes is not None:
            link.notes = notes
        db.commit()
    return RedirectResponse(url=f"/events/{event_id}", status_code=303)


@router.post("/{event_id}/import-attendees")
async def import_attendees(
    event_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    contents = await file.read()
    records = parse_csv(contents)
    added = 0
    for rec in records:
        if not rec.get("company_name"):
            continue
        prospect = db.query(Prospect).filter(Prospect.company_name == rec["company_name"]).first()
        if not prospect:
            prospect = Prospect(**rec)
            db.add(prospect)
            db.flush()

        existing = db.query(EventProspect).filter(
            EventProspect.event_id == event_id,
            EventProspect.prospect_id == prospect.id
        ).first()
        if not existing:
            db.add(EventProspect(event_id=event_id, prospect_id=prospect.id))
            added += 1

    db.commit()
    return RedirectResponse(url=f"/events/{event_id}", status_code=303)
