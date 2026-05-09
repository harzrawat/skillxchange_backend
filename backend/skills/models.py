import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from backend.extensions import db

class Skill(db.Model):
    __tablename__ = 'skills'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=True)
    mode = db.Column(db.String(20), nullable=True)
    credits_per_session = db.Column(db.Integer, nullable=True)
    price_per_session = db.Column(db.Numeric(8, 2), nullable=True)
    is_featured = db.Column(db.Boolean, default=False)
    featured_until = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=func.now())

class SkillRequest(db.Model):
    __tablename__ = 'skill_requests'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, server_default=func.now())
