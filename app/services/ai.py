import os
import anthropic

_client = None


def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def generate_prospect_brief(prospect_data: dict) -> str:
    client = get_client()
    if not client:
        return "Add ANTHROPIC_API_KEY to .env to enable AI briefs."

    prompt = f"""You are preparing a sales call brief for a consultant who provides equity advisory services to home healthcare companies.

Prospect details:
- Company: {prospect_data.get('company_name')}
- Contact: {prospect_data.get('contact_name')} ({prospect_data.get('title')})
- Ownership: {prospect_data.get('ownership_type', 'unknown')}
- Revenue tier: {prospect_data.get('revenue_tier', 'unknown')}
- Location: {prospect_data.get('city')}, {prospect_data.get('state')}
- Notes: {prospect_data.get('notes', 'none')}

Write a 3-bullet call prep brief covering:
1. Likely business context / situation for this type of agency
2. Most relevant equity service angles to lead with
3. Recommended opening question to establish pain/interest

Keep it concise and actionable. No fluff."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


def generate_email_draft(prospect_data: dict, template_body: str = None) -> dict:
    client = get_client()
    if not client:
        return {"subject": "", "body": "Add ANTHROPIC_API_KEY to .env to enable AI drafts."}

    base_context = f"""Company: {prospect_data.get('company_name')}
Contact: {prospect_data.get('contact_name')} ({prospect_data.get('title')})
Ownership: {prospect_data.get('ownership_type', 'unknown')}
Revenue: {prospect_data.get('revenue_tier', 'unknown')}
Location: {prospect_data.get('city')}, {prospect_data.get('state')}"""

    if template_body:
        prompt = f"""You are drafting a personalized cold email for {prospect_data.get('contact_name')} at {prospect_data.get('company_name')}.

Prospect context:
{base_context}

Template to personalize:
{template_body}

Rewrite this email with a specific, personalized first line that references something relevant to their situation. Keep the rest tight and under 150 words total. Output JSON with keys "subject" and "body"."""
    else:
        prompt = f"""Draft a short cold outreach email from Ashley Stennis, an equity services consultant for home healthcare companies.

Prospect:
{base_context}

The email should:
- Open with a personalized, specific observation about their situation
- Briefly mention equity advisory value (succession, growth capital, PE positioning)
- End with a single low-friction ask (15-min call)
- Be under 120 words

Output JSON with keys "subject" and "body"."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    import json
    text = message.content[0].text
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {"subject": "Following up", "body": text}


def generate_weekly_digest(pipeline_stats: dict, due_items: list) -> str:
    client = get_client()
    if not client:
        return "Add ANTHROPIC_API_KEY to .env to enable AI digest."

    prompt = f"""Write a brief weekly outbound digest for Ashley Stennis, equity services consultant.

Pipeline this week:
{pipeline_stats}

Overdue outreach items: {len(due_items)}

Write 3 short bullets:
1. Pipeline health (what's moving, what's stalled)
2. Top priority action this week
3. One strategic note on outbound momentum

Be direct and specific. No preamble."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text
