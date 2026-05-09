import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from backend.extensions import db

class CreditTransaction(db.Model):
    __tablename__ = 'credit_transactions'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    delta = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(100), nullable=True)
    ref_id = db.Column(UUID(as_uuid=True), nullable=True)
    created_at = db.Column(db.DateTime, server_default=func.now())
