"""
Industry Intelligence service — uses Claude with web search to:
1. Research individual prospects (signals, news, urgency)
2. Run weekly home healthcare industry scans
3. Generate outreach angles based on real-time signals
"""
import os
import json
import logging
from datetime import date, datetime

import anthropic

logger = logging.getLogger(__name__)

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 8}


def _client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def _extract_text(message) -> str:
    parts = []
    for block in message.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts)


def _parse_json(text: str, fallback):
    try:
        # Try to find JSON object or array
        for opener, closer in [("{", "}"), ("[", "]")]:
            start = text.find(opener)
            end = text.rfind(closer) + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
    except Exception as e:
        logger.warning(f"JSON parse failed: {e}")
    return fallback


def research_prospect(prospect_data: dict) -> dict:
    """Live web research on a specific prospect company."""
    client = _client()
    if not client:
        return {"error": "ANTHROPIC_API_KEY not set"}

    company = prospect_data.get("company_name", "")
    location = ", ".join(filter(None, [prospect_data.get("city"), prospect_data.get("state")]))

    prompt = f"""You are a market analyst for an equity advisory firm focused on home healthcare. Research the company "{company}" in {location} using web_search.

Find:
1. Recent news (last 12 months) — leadership changes, expansion, M&A, partnerships
2. Ownership signals — independent? PE-backed? Part of a chain?
3. Regulatory or financial pressures affecting this agency or its region
4. Why now is a relevant moment for an equity advisory conversation

Return ONLY a JSON object with these keys:
- "summary": 2-sentence overview of the company's current situation
- "signals": array of objects, each with {{ "type": "...", "headline": "...", "source_url": "..." }} — at least 2 signals if findable
- "outreach_angle": one paragraph specific talking point referencing the signals above
- "urgency_score": integer 1-10 indicating time-sensitivity of the opportunity

Output the JSON only, no preamble."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2500,
            tools=[WEB_SEARCH_TOOL],
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(message)
        result = _parse_json(text, {})
        if not result:
            return {"summary": text[:500], "signals": [], "outreach_angle": "", "urgency_score": 0}
        return result
    except Exception as e:
        logger.error(f"research_prospect error: {e}")
        return {"error": str(e)}


def weekly_industry_scan() -> dict:
    """Weekly scan of home healthcare industry trends and signals."""
    client = _client()
    if not client:
        return {"error": "ANTHROPIC_API_KEY not set"}

    today = date.today().isoformat()
    prompt = f"""You are an industry analyst tracking home healthcare for an equity advisory firm. Today is {today}.

Use web_search to research and produce this week's intelligence briefing covering:

1. RECENT NEWS (last 14 days):
   - CMS / regulatory changes affecting home health reimbursement, oversight, or operations
   - PE deal activity (acquisitions, fundraises, exits, rollups) in home healthcare
   - Notable company news (M&A, leadership shifts, expansions, closures)

2. MARKET TRENDS:
   - How is reimbursement changing (PDGM, value-based, Medicare Advantage)?
   - Where is consolidation heating up — by geography or segment?
   - Labor cost & workforce dynamics
   - Tech / AI adoption in home health

3. DOWNWIND EFFECTS:
   - What changes are creating urgency for independent agency owners?
   - Which independent operators are most pressured to consider equity events?

4. AI IN HOME HEALTH:
   - Notable vendors, deployments, ROI evidence
   - How AI is changing competitive dynamics for independents

Return ONLY a JSON object with these keys:
- "executive_summary": array of 3 bullet strings — the most important week-over-week movements
- "regulatory": array of {{ "headline": "...", "summary": "...", "impact": "...", "source_url": "..." }}
- "pe_activity": array of {{ "headline": "...", "summary": "...", "impact": "...", "source_url": "..." }}
- "trends": array of {{ "trend": "...", "evidence": "...", "implication": "..." }}
- "urgency_signals": array of 3 specific reasons agency owners should evaluate equity options now
- "ai_developments": array of {{ "topic": "...", "summary": "...", "source_url": "..." }}

Output the JSON only, no preamble."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=6000,
            tools=[WEB_SEARCH_TOOL],
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(message)
        result = _parse_json(text, {})
        if not result:
            return {"executive_summary": [text[:500]], "regulatory": [], "pe_activity": [], "trends": [], "urgency_signals": [], "ai_developments": []}
        return result
    except Exception as e:
        logger.error(f"weekly_industry_scan error: {e}")
        return {"error": str(e)}


def find_qualified_prospects(state: str = None, additional_criteria: str = "") -> list:
    """Use web search to discover new prospects matching the firm's ICP."""
    client = _client()
    if not client:
        return []

    geography = f"in {state}" if state else "in the United States"
    prompt = f"""Use web_search to find independent home healthcare agencies {geography} that match this profile:
- Estimated revenue: $5M+
- Ownership: independent (NOT PE-backed, NOT part of a regional chain)
- Indications they may be receptive to equity advisory: founder approaching exit, growth stalling, expansion needs, succession concerns
{f"- Additional criteria: {additional_criteria}" if additional_criteria else ""}

For each company you find, return an object with:
- "company_name"
- "city"
- "state"
- "revenue_estimate" (e.g. "$5–10M")
- "leadership" (names if findable)
- "fit_signals" (2-3 short reasons why they fit)
- "source_url"

Return ONLY a JSON array. Output the JSON only, no preamble. Aim for 5-10 results."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            tools=[WEB_SEARCH_TOOL],
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(message)
        result = _parse_json(text, [])
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.error(f"find_qualified_prospects error: {e}")
        return []


def store_prospect_insight(db, prospect_id: int, research: dict):
    """Save a research result to the insights table."""
    from app.models import Insight
    insight = Insight(
        prospect_id=prospect_id,
        insight_type="company_research",
        summary=research.get("summary", ""),
        outreach_angle=research.get("outreach_angle", ""),
        signals_json=json.dumps(research.get("signals", [])),
        urgency_score=research.get("urgency_score", 0),
    )
    db.add(insight)
    db.commit()
    return insight


def store_industry_report(db, scan: dict):
    """Save a weekly industry scan to the industry_reports table."""
    from app.models import IndustryReport
    report = IndustryReport(
        week_of=date.today(),
        executive_summary=json.dumps(scan.get("executive_summary", [])),
        regulatory_json=json.dumps(scan.get("regulatory", [])),
        pe_activity_json=json.dumps(scan.get("pe_activity", [])),
        trends_json=json.dumps(scan.get("trends", [])),
        urgency_signals=json.dumps(scan.get("urgency_signals", [])),
        ai_developments_json=json.dumps(scan.get("ai_developments", [])),
    )
    db.add(report)
    db.commit()
    return report
