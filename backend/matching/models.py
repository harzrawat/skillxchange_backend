import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from backend.extensions import db

class Match(db.Model):
    __tablename__ = 'matches'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    learner_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    skill_id = db.Column(UUID(as_uuid=True), db.ForeignKey('skills.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    session_type = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, server_default=func.now())

class Session(db.Model):
    __tablename__ = 'sessions'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = db.Column(UUID(as_uuid=True), db.ForeignKey('matches.id'), nullable=False)
    teacher_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    learner_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    skill_id = db.Column(UUID(as_uuid=True), db.ForeignKey('skills.id'), nullable=False)
    session_type = db.Column(db.String(20), nullable=True)
    credits_used = db.Column(db.Integer, nullable=True)
    amount_paid = db.Column(db.Numeric(8, 2), nullable=True)
    platform_fee = db.Column(db.Numeric(8, 2), nullable=True)
    video_call_url = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(20), default='scheduled')
    scheduled_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
