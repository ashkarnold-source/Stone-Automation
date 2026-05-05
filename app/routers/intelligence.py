import json
from fastapi import APIRouter, Depends, Request, BackgroundTasks, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date

from app.database import get_db, SessionLocal
from app.models import IndustryReport, Insight, Prospect
from app.services.intelligence import (
    research_prospect,
    weekly_industry_scan,
    find_qualified_prospects,
    store_prospect_insight,
    store_industry_report,
)

router = APIRouter(prefix="/intelligence")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def intelligence_home(request: Request, db: Session = Depends(get_db)):
    latest = db.query(IndustryReport).order_by(IndustryReport.created_at.desc()).first()

    parsed = None
    if latest:
        parsed = {
            "executive_summary": json.loads(latest.executive_summary or "[]"),
            "regulatory": json.loads(latest.regulatory_json or "[]"),
            "pe_activity": json.loads(latest.pe_activity_json or "[]"),
            "trends": json.loads(latest.trends_json or "[]"),
            "urgency_signals": json.loads(latest.urgency_signals or "[]"),
            "ai_developments": json.loads(latest.ai_developments_json or "[]"),
            "week_of": latest.week_of,
        }

    # Top urgent prospect insights (last 30 days)
    top_insights = (
        db.query(Insight)
        .filter(Insight.insight_type == "company_research")
        .filter(Insight.urgency_score >= 7)
        .order_by(Insight.created_at.desc())
        .limit(10)
        .all()
    )

    insights_with_prospects = []
    for ins in top_insights:
        prospect = db.query(Prospect).filter(Prospect.id == ins.prospect_id).first()
        if prospect:
            insights_with_prospects.append({"insight": ins, "prospect": prospect})

    return templates.TemplateResponse("intelligence.html", {
        "request": request,
        "report": parsed,
        "top_insights": insights_with_prospects,
    })


@router.post("/scan")
def run_industry_scan(background_tasks: BackgroundTasks):
    """Trigger a fresh weekly industry scan."""
    def task():
        db = SessionLocal()
        try:
            scan = weekly_industry_scan()
            if "error" not in scan:
                store_industry_report(db, scan)
        finally:
            db.close()

    background_tasks.add_task(task)
    return RedirectResponse(url="/intelligence?running=1", status_code=303)


@router.post("/research/{prospect_id}")
def research_one(prospect_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Trigger live research on a single prospect."""
    prospect = db.query(Prospect).filter(Prospect.id == prospect_id).first()
    if not prospect:
        return RedirectResponse(url="/prospects", status_code=303)

    prospect_data = {
        "company_name": prospect.company_name,
        "contact_name": prospect.contact_name,
        "title": prospect.title,
        "ownership_type": prospect.ownership_type,
        "revenue_tier": prospect.revenue_tier,
        "city": prospect.city,
        "state": prospect.state,
    }

    def task():
        db_local = SessionLocal()
        try:
            result = research_prospect(prospect_data)
            if "error" not in result:
                store_prospect_insight(db_local, prospect_id, result)
        finally:
            db_local.close()

    background_tasks.add_task(task)
    return RedirectResponse(url=f"/prospects/{prospect_id}?researching=1", status_code=303)


@router.get("/discover", response_class=HTMLResponse)
def discover_page(request: Request):
    return templates.TemplateResponse("discover.html", {
        "request": request,
        "results": None,
        "criteria": None,
    })


@router.post("/discover", response_class=HTMLResponse)
def discover_run(
    request: Request,
    state: str = Form(None),
    criteria: str = Form(""),
):
    results = find_qualified_prospects(state=state, additional_criteria=criteria)
    return templates.TemplateResponse("discover.html", {
        "request": request,
        "results": results,
        "criteria": {"state": state, "criteria": criteria},
    })


@router.post("/discover/import")
def discover_import(
    company_name: str = Form(...),
    city: str = Form(None),
    state: str = Form(None),
    fit_signals: str = Form(None),
    db: Session = Depends(get_db),
):
    existing = db.query(Prospect).filter(Prospect.company_name == company_name).first()
    if not existing:
        db.add(Prospect(
            company_name=company_name,
            city=city,
            state=state,
            notes=f"Discovered via AI: {fit_signals or ''}",
            source="ai_discovery",
            ownership_type="independent",
        ))
        db.commit()
    return RedirectResponse(url="/intelligence/discover", status_code=303)
