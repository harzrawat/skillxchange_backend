import uuid
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.postgresql import UUID
# pyrefly: ignore [missing-import]
from sqlalchemy.sql import func
from backend.extensions import db

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    avatar_url = db.Column(db.String(300), nullable=True)
    college = db.Column(db.String(150), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    credits = db.Column(db.Integer, default=50)
    is_premium = db.Column(db.Boolean, default=False)
    premium_expiry = db.Column(db.DateTime, nullable=True)
    sessions_taught = db.Column(db.Integer, default=0)
    teacher_score = db.Column(db.Numeric(3, 2), default=5.0)
    created_at = db.Column(db.DateTime, server_default=func.now())
