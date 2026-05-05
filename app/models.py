from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Prospect(Base):
    __tablename__ = "prospects"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False, index=True)
    contact_name = Column(String)
    title = Column(String)
    email = Column(String, index=True)
    phone = Column(String)
    linkedin_url = Column(String)
    revenue_tier = Column(String)           # under_5m | 5m_10m | 10m_25m | 25m_plus
    ownership_type = Column(String)         # independent | pe_backed | regional_chain
    state = Column(String, index=True)
    city = Column(String)
    source = Column(String, default="csv_upload")
    status = Column(String, default="identified", index=True)
    # identified | contacted | engaged | proposal | closed_won | closed_lost | not_interested
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    activities = relationship("Activity", back_populates="prospect", cascade="all, delete-orphan")
    enrollments = relationship("SequenceEnrollment", back_populates="prospect", cascade="all, delete-orphan")
    event_links = relationship("EventProspect", back_populates="prospect", cascade="all, delete-orphan")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    prospect_id = Column(Integer, ForeignKey("prospects.id"), nullable=False)
    channel = Column(String, nullable=False)   # email | linkedin | phone | event | note
    direction = Column(String, default="outbound")  # outbound | inbound
    subject = Column(String)
    body = Column(Text)
    outcome = Column(String)  # no_response | replied | call_booked | not_interested | voicemail
    activity_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    prospect = relationship("Prospect", back_populates="activities")


class Sequence(Base):
    __tablename__ = "sequences"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    steps = relationship("SequenceStep", back_populates="sequence", order_by="SequenceStep.step_number", cascade="all, delete-orphan")
    enrollments = relationship("SequenceEnrollment", back_populates="sequence", cascade="all, delete-orphan")


class SequenceStep(Base):
    __tablename__ = "sequence_steps"

    id = Column(Integer, primary_key=True, index=True)
    sequence_id = Column(Integer, ForeignKey("sequences.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    channel = Column(String, nullable=False)   # email | linkedin | phone
    delay_days = Column(Integer, default=0)    # days after previous step
    subject_template = Column(String)
    body_template = Column(Text)

    sequence = relationship("Sequence", back_populates="steps")


class SequenceEnrollment(Base):
    __tablename__ = "sequence_enrollments"

    id = Column(Integer, primary_key=True, index=True)
    prospect_id = Column(Integer, ForeignKey("prospects.id"), nullable=False)
    sequence_id = Column(Integer, ForeignKey("sequences.id"), nullable=False)
    current_step = Column(Integer, default=1)
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    next_action_date = Column(Date)
    status = Column(String, default="active")  # active | paused | completed | replied | opted_out
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    prospect = relationship("Prospect", back_populates="enrollments")
    sequence = relationship("Sequence", back_populates="enrollments")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    event_date = Column(Date)
    end_date = Column(Date)
    location = Column(String)
    event_type = Column(String)  # conference | trade_show | association | webinar | networking
    website = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    prospect_links = relationship("EventProspect", back_populates="event", cascade="all, delete-orphan")


class EventProspect(Base):
    __tablename__ = "event_prospects"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    prospect_id = Column(Integer, ForeignKey("prospects.id"), nullable=False)
    status = Column(String, default="targeting")
    # targeting | reached_out | confirmed_attending | met | following_up | converted
    notes = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    event = relationship("Event", back_populates="prospect_links")
    prospect = relationship("Prospect", back_populates="event_links")


class Insight(Base):
    """AI-generated research and signals about prospects or the industry."""
    __tablename__ = "insights"

    id = Column(Integer, primary_key=True, index=True)
    prospect_id = Column(Integer, ForeignKey("prospects.id"), nullable=True)
    insight_type = Column(String)  # company_research | industry_signal | urgency_alert
    summary = Column(Text)
    outreach_angle = Column(Text)
    signals_json = Column(Text)        # JSON list of {type, headline, source_url}
    urgency_score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class IndustryReport(Base):
    """Weekly market intelligence reports."""
    __tablename__ = "industry_reports"

    id = Column(Integer, primary_key=True, index=True)
    week_of = Column(Date)
    executive_summary = Column(Text)   # JSON list of bullets
    regulatory_json = Column(Text)
    pe_activity_json = Column(Text)
    trends_json = Column(Text)
    urgency_signals = Column(Text)     # JSON list of strings
    ai_developments_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
