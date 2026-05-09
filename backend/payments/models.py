import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from backend.extensions import db

class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'))
    payee_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=True)
    session_id = db.Column(UUID(as_uuid=True), db.ForeignKey('sessions.id'), nullable=True)
    payment_type = db.Column(db.String(30), nullable=False)
    target_ref_id = db.Column(UUID(as_uuid=True), nullable=True)
    gross_amount = db.Column(db.Numeric(8, 2), nullable=False)
    platform_fee = db.Column(db.Numeric(8, 2), nullable=False)
    net_amount = db.Column(db.Numeric(8, 2), nullable=False)
    payment_status = db.Column(db.String(20), default='pending')
    gateway_ref = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, server_default=func.now())
