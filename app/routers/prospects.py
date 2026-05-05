from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import Prospect, Activity, SequenceEnrollment, Sequence
from app.services.csv_import import parse_csv
from app.services.ai import generate_prospect_brief, generate_email_draft

router = APIRouter(prefix="/prospects")
templates = Jinja2Templates(directory="app/templates")

STATUSES = ["identified", "contacted", "engaged", "proposal", "closed_won", "closed_lost", "not_interested"]
OWNERSHIP_TYPES = ["independent", "pe_backed", "regional_chain"]
REVENUE_TIERS = ["under_5m", "5m_10m", "10m_25m", "25m_plus"]


@router.get("", response_class=HTMLResponse)
def list_prospects(
    request: Request,
    db: Session = Depends(get_db),
    status: Optional[str] = None,
    ownership: Optional[str] = None,
    state: Optional[str] = None,
    revenue: Optional[str] = None,
    q: Optional[str] = None,
):
    query = db.query(Prospect)

    if status:
        query = query.filter(Prospect.status == status)
    if ownership:
        query = query.filter(Prospect.ownership_type == ownership)
    if state:
        query = query.filter(Prospect.state == state)
    if revenue:
        query = query.filter(Prospect.revenue_tier == revenue)
    if q:
        search = f"%{q}%"
        query = query.filter(
            Prospect.company_name.ilike(search) |
            Prospect.contact_name.ilike(search) |
            Prospect.email.ilike(search)
        )

    prospects = query.order_by(Prospect.created_at.desc()).all()

    states = [r[0] for r in db.query(Prospect.state).distinct().filter(Prospect.state.isnot(None)).all()]
    total = db.query(Prospect).count()

    return templates.TemplateResponse("prospects.html", {
        "request": request,
        "prospects": prospects,
        "statuses": STATUSES,
        "ownership_types": OWNERSHIP_TYPES,
        "revenue_tiers": REVENUE_TIERS,
        "states": sorted(states),
        "filters": {"status": status, "ownership": ownership, "state": state, "revenue": revenue, "q": q},
        "total": total,
    })


@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request):
    return templates.TemplateResponse("import.html", {"request": request, "result": None})


@router.post("/import")
async def import_csv(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()
    try:
        records = parse_csv(contents)
    except Exception as e:
        return templates.TemplateResponse("import.html", {
            "request": request,
            "result": {"success": False, "error": str(e)}
        })

    added = 0
    skipped = 0
    for rec in records:
        existing = db.query(Prospect).filter(
            Prospect.company_name == rec["company_name"],
            Prospect.email == rec.get("email")
        ).first()
        if existing:
            skipped += 1
            continue
        db.add(Prospect(**rec))
        added += 1

    db.commit()
    return templates.TemplateResponse("import.html", {
        "request": request,
        "result": {"success": True, "added": added, "skipped": skipped, "total": len(records)}
    })


@router.get("/{prospect_id}", response_class=HTMLResponse)
def prospect_detail(request: Request, prospect_id: int, db: Session = Depends(get_db)):
    prospect = db.query(Prospect).filter(Prospect.id == prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    activities = (
        db.query(Activity)
        .filter(Activity.prospect_id == prospect_id)
        .order_by(Activity.activity_date.desc())
        .all()
    )

    sequences = db.query(Sequence).filter(Sequence.is_active == True).all()
    enrollment = (
        db.query(SequenceEnrollment)
        .filter(
            SequenceEnrollment.prospect_id == prospect_id,
            SequenceEnrollment.status == "active"
        )
        .first()
    )

    # Latest research insight
    from app.models import Insight
    import json as _json
    latest_insight = (
        db.query(Insight)
        .filter(Insight.prospect_id == prospect_id, Insight.insight_type == "company_research")
        .order_by(Insight.created_at.desc())
        .first()
    )
    insight_signals = []
    if latest_insight and latest_insight.signals_json:
        try:
            insight_signals = _json.loads(latest_insight.signals_json)
        except Exception:
            pass

    return templates.TemplateResponse("prospect_detail.html", {
        "request": request,
        "prospect": prospect,
        "activities": activities,
        "sequences": sequences,
        "enrollment": enrollment,
        "statuses": STATUSES,
        "latest_insight": latest_insight,
        "insight_signals": insight_signals,
    })


@router.post("/{prospect_id}/update")
def update_prospect(
    prospect_id: int,
    status: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
):
    prospect = db.query(Prospect).filter(Prospect.id == prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Not found")
    if status:
        prospect.status = status
    if notes is not None:
        prospect.notes = notes
    db.commit()
    return RedirectResponse(url=f"/prospects/{prospect_id}", status_code=303)


@router.get("/{prospect_id}/brief")
def prospect_brief(prospect_id: int, db: Session = Depends(get_db)):
    prospect = db.query(Prospect).filter(Prospect.id == prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Not found")
    brief = generate_prospect_brief({
        "company_name": prospect.company_name,
        "contact_name": prospect.contact_name,
        "title": prospect.title,
        "ownership_type": prospect.ownership_type,
        "revenue_tier": prospect.revenue_tier,
        "city": prospect.city,
        "state": prospect.state,
        "notes": prospect.notes,
    })
    return {"brief": brief}


@router.get("/{prospect_id}/draft-email")
def draft_email(prospect_id: int, db: Session = Depends(get_db)):
    prospect = db.query(Prospect).filter(Prospect.id == prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Not found")
    draft = generate_email_draft({
        "company_name": prospect.company_name,
        "contact_name": prospect.contact_name,
        "title": prospect.title,
        "ownership_type": prospect.ownership_type,
        "revenue_tier": prospect.revenue_tier,
        "city": prospect.city,
        "state": prospect.state,
    })
    return draft
