import os
import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.models import Prospect, Activity, SequenceEnrollment, SequenceStep

logger = logging.getLogger(__name__)

# Tracks last run time for each job — shown on dashboard
job_status = {
    "email_sequences": {"last_run": None, "last_result": "Not run yet"},
    "reply_check":     {"last_run": None, "last_result": "Not run yet"},
    "morning_digest":  {"last_run": None, "last_result": "Not run yet"},
    "industry_scan":   {"last_run": None, "last_result": "Not run yet"},
}


def run_email_sequences():
    from app.services.gmail import send_email, is_authenticated
    from app.services.ai import generate_email_draft

    job_status["email_sequences"]["last_run"] = datetime.now().strftime("%b %-d %-I:%M %p")

    if not is_authenticated():
        job_status["email_sequences"]["last_result"] = "Skipped — Gmail not connected"
        return

    db = SessionLocal()
    try:
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())

        due = (
            db.query(SequenceEnrollment)
            .filter(
                SequenceEnrollment.status == "active",
                SequenceEnrollment.next_action_date <= today,
            )
            .all()
        )

        sent = skipped = 0
        for enrollment in due:
            step = (
                db.query(SequenceStep)
                .filter(
                    SequenceStep.sequence_id == enrollment.sequence_id,
                    SequenceStep.step_number == enrollment.current_step,
                )
                .first()
            )

            if not step or step.channel != "email":
                skipped += 1
                continue

            prospect = enrollment.prospect
            if not prospect.email:
                skipped += 1
                continue

            # Don't double-send if scheduler runs twice today
            already_sent = (
                db.query(Activity)
                .filter(
                    Activity.prospect_id == prospect.id,
                    Activity.channel == "email",
                    Activity.direction == "outbound",
                    Activity.activity_date >= today_start,
                )
                .first()
            )
            if already_sent:
                skipped += 1
                continue

            # Build email content
            if step.body_template:
                body = step.body_template
                body = body.replace("{{company}}", prospect.company_name or "")
                body = body.replace("{{contact_name}}", prospect.contact_name or "there")
                body = body.replace("{{state}}", prospect.state or "")
                subject = (step.subject_template or "Following up").replace(
                    "{{company}}", prospect.company_name or ""
                )
            else:
                draft = generate_email_draft({
                    "company_name": prospect.company_name,
                    "contact_name": prospect.contact_name,
                    "title": prospect.title,
                    "ownership_type": prospect.ownership_type,
                    "revenue_tier": prospect.revenue_tier,
                    "city": prospect.city,
                    "state": prospect.state,
                })
                subject = draft.get("subject", "Quick question")
                body = draft.get("body", "")

            result = send_email(prospect.email, subject, body)

            if result["success"]:
                db.add(Activity(
                    prospect_id=prospect.id,
                    channel="email",
                    direction="outbound",
                    subject=subject,
                    body=body,
                    outcome="no_response",
                    activity_date=datetime.utcnow(),
                ))

                # Advance to next step or complete
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
                    enrollment.next_action_date = date.today() + timedelta(days=next_step.delay_days)
                else:
                    enrollment.status = "completed"

                if prospect.status == "identified":
                    prospect.status = "contacted"

                sent += 1

        db.commit()
        job_status["email_sequences"]["last_result"] = f"Sent {sent} emails, skipped {skipped}"
        logger.info(f"Email sequences: sent={sent} skipped={skipped}")

    except Exception as e:
        db.rollback()
        job_status["email_sequences"]["last_result"] = f"Error: {e}"
        logger.error(f"Email sequence error: {e}")
    finally:
        db.close()


def check_gmail_replies():
    from app.services.gmail import get_recent_replies, is_authenticated

    job_status["reply_check"]["last_run"] = datetime.now().strftime("%b %-d %-I:%M %p")

    if not is_authenticated():
        job_status["reply_check"]["last_result"] = "Skipped — Gmail not connected"
        return

    db = SessionLocal()
    try:
        replies = get_recent_replies(max_results=50)
        detected = 0

        for reply in replies:
            from_field = reply.get("from", "")
            email = from_field.split("<")[-1].rstrip(">").strip() if "<" in from_field else from_field.strip()

            if not email:
                continue

            prospect = db.query(Prospect).filter(Prospect.email.ilike(email)).first()
            if not prospect:
                continue

            # Skip if already logged
            existing = (
                db.query(Activity)
                .filter(
                    Activity.prospect_id == prospect.id,
                    Activity.channel == "email",
                    Activity.direction == "inbound",
                    Activity.subject == reply.get("subject"),
                )
                .first()
            )
            if existing:
                continue

            db.add(Activity(
                prospect_id=prospect.id,
                channel="email",
                direction="inbound",
                subject=reply.get("subject"),
                outcome="replied",
                activity_date=datetime.utcnow(),
            ))

            if prospect.status in ("identified", "contacted"):
                prospect.status = "engaged"

            enrollment = (
                db.query(SequenceEnrollment)
                .filter(
                    SequenceEnrollment.prospect_id == prospect.id,
                    SequenceEnrollment.status == "active",
                )
                .first()
            )
            if enrollment:
                enrollment.status = "replied"

            detected += 1

        db.commit()
        job_status["reply_check"]["last_result"] = f"Detected {detected} new replies"
        logger.info(f"Reply check: detected={detected}")

    except Exception as e:
        db.rollback()
        job_status["reply_check"]["last_result"] = f"Error: {e}"
        logger.error(f"Reply check error: {e}")
    finally:
        db.close()


def send_morning_digest():
    from app.services.gmail import send_email, is_authenticated
    from app.services.ai import generate_weekly_digest

    job_status["morning_digest"]["last_run"] = datetime.now().strftime("%b %-d %-I:%M %p")

    if not is_authenticated():
        job_status["morning_digest"]["last_result"] = "Skipped — Gmail not connected"
        return

    to_email = os.getenv("FROM_EMAIL")
    if not to_email:
        job_status["morning_digest"]["last_result"] = "Skipped — FROM_EMAIL not set"
        return

    db = SessionLocal()
    try:
        pipeline = {}
        for stage in ["identified", "contacted", "engaged", "proposal", "closed_won"]:
            pipeline[stage] = db.query(Prospect).filter(Prospect.status == stage).count()

        due_count = (
            db.query(SequenceEnrollment)
            .filter(
                SequenceEnrollment.status == "active",
                SequenceEnrollment.next_action_date <= date.today(),
            )
            .count()
        )

        yesterday = datetime.utcnow() - timedelta(hours=24)
        new_replies = (
            db.query(Activity)
            .filter(Activity.direction == "inbound", Activity.activity_date >= yesterday)
            .count()
        )

        emails_sent_today = (
            db.query(Activity)
            .filter(
                Activity.channel == "email",
                Activity.direction == "outbound",
                Activity.activity_date >= datetime.combine(date.today(), datetime.min.time()),
            )
            .count()
        )

        ai_notes = generate_weekly_digest(pipeline, [])

        app_url = os.getenv("APP_URL", "http://localhost:8000")
        body = f"""Good morning Ashley,

Here's your Stone Command Center daily briefing for {date.today().strftime('%A, %B %-d')}.

PIPELINE
  Identified:  {pipeline['identified']}
  Contacted:   {pipeline['contacted']}
  Engaged:     {pipeline['engaged']}
  Proposal:    {pipeline['proposal']}
  Closed Won:  {pipeline['closed_won']}

TODAY
  New replies (last 24h):  {new_replies}
  Emails sent today:       {emails_sent_today}
  Actions still due:       {due_count}

AI NOTES
{ai_notes}

Open your command center: {app_url}
"""

        result = send_email(to_email, f"Stone Briefing — {date.today().strftime('%b %-d')}", body)
        job_status["morning_digest"]["last_result"] = "Sent" if result["success"] else f"Failed: {result.get('error')}"

    except Exception as e:
        job_status["morning_digest"]["last_result"] = f"Error: {e}"
        logger.error(f"Morning digest error: {e}")
    finally:
        db.close()


def run_weekly_industry_scan():
    """Weekly Monday 6am job: pulls fresh industry intelligence."""
    from app.services.intelligence import weekly_industry_scan, store_industry_report

    job_status["industry_scan"]["last_run"] = datetime.now().strftime("%b %-d %-I:%M %p")

    db = SessionLocal()
    try:
        scan = weekly_industry_scan()
        if "error" in scan:
            job_status["industry_scan"]["last_result"] = f"Error: {scan['error']}"
            return
        store_industry_report(db, scan)
        job_status["industry_scan"]["last_result"] = "New report saved"
    except Exception as e:
        db.rollback()
        job_status["industry_scan"]["last_result"] = f"Error: {e}"
        logger.error(f"Industry scan error: {e}")
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()

    # Auto-send emails daily at 8am
    scheduler.add_job(
        run_email_sequences,
        CronTrigger(hour=8, minute=0),
        id="email_sequences",
        replace_existing=True,
    )

    # Check for replies every hour
    scheduler.add_job(
        check_gmail_replies,
        CronTrigger(minute=0),
        id="reply_check",
        replace_existing=True,
    )

    # Morning digest at 7am
    scheduler.add_job(
        send_morning_digest,
        CronTrigger(hour=7, minute=0),
        id="morning_digest",
        replace_existing=True,
    )

    # Weekly industry scan — Mondays at 6am
    scheduler.add_job(
        run_weekly_industry_scan,
        CronTrigger(day_of_week="mon", hour=6, minute=0),
        id="industry_scan",
        replace_existing=True,
    )

    return scheduler
