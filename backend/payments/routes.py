import os
import logging
import razorpay
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.matching.models import Session
from backend.payments.models import Payment
from backend.payments.utils import verify_payment_signature, verify_webhook_signature

logger = logging.getLogger(__name__)
payments_bp = Blueprint('payments', __name__, url_prefix='/api/payments')

@payments_bp.route('/initiate', methods=['POST'])
@jwt_required()
def initiate_payment():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    
    session_id = data.get('sessionId')
    if not session_id:
        return jsonify({"success": False, "error": "sessionId is required"}), 400
        
    session = Session.query.get(session_id)
    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404
        
    if str(session.learner_id) != str(user_id):
        return jsonify({"success": False, "error": "Not the learner"}), 403
        
    if session.session_type != 'paid':
        return jsonify({"success": False, "error": "Wrong session type"}), 400
        
    if session.status != 'scheduled':
        return jsonify({"success": False, "error": "Session must be scheduled"}), 400
        
    existing_payment = Payment.query.filter_by(
        session_id=session.id, 
        payment_status='success'
    ).first()
    
    if existing_payment:
        return jsonify({"success": False, "error": "Payment already completed for this session"}), 409
        
    key_id = os.environ.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
    
    if not key_id or not key_secret:
        return jsonify({"success": False, "error": "Razorpay not configured"}), 500
        
    client = razorpay.Client(auth=(key_id, key_secret))
    
    gross_amount = session.amount_paid
    if gross_amount is None:
        return jsonify({"success": False, "error": "Session has no amount"}), 400

    amount_paise = int(session.amount_paid * 100)
    if amount_paise <= 0:
        return jsonify({"success": False, "error": "Invalid session amount"}), 400
        
    platform_fee = float(gross_amount) * 0.15
    net_amount = float(gross_amount) - platform_fee
    
    new_payment = Payment(
        payer_id=session.learner_id,
        payee_id=session.teacher_id,
        session_id=session.id,
        payment_type='session',
        target_ref_id=session.id,
        gross_amount=gross_amount,
        platform_fee=platform_fee,
        net_amount=net_amount,
        payment_status='pending'
    )
    
    db.session.add(new_payment)
    db.session.flush()
    
    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": str(new_payment.id),
            "payment_capture": 1
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": "Razorpay API error"}), 502
        
    new_payment.gateway_ref = order['id']
    db.session.commit()
    
    return jsonify({
        "success": True,
        "data": {
            "paymentId": str(new_payment.id),
            "razorpayOrderId": order['id'],
            "amount": float(gross_amount),
            "currency": "INR",
            "keyId": key_id
        }
    }), 200

@payments_bp.route('/verify', methods=['POST'])
@jwt_required()
def verify_payment():

    data = request.get_json() or {}
    
    order_id = data.get('razorpayOrderId')
    payment_id = data.get('razorpayPaymentId')
    signature = data.get('razorpaySignature')
    
    if not order_id or not payment_id or not signature:
        return jsonify({"success": False, "error": "Missing parameters"}), 400

    if not verify_payment_signature(order_id, payment_id, signature):
        return jsonify({"success": False, "error": "Invalid signature"}), 400
        
    payment = Payment.query.filter_by(gateway_ref=order_id).first()
    if not payment:
        return jsonify({"success": False, "error": "Payment not found"}), 404

    if payment.payment_status == 'success':
        return jsonify({
            "success": True,
            "data": {
                "message": "Payment already verified",
                "paymentId": str(payment.id)
            }
        }), 200
        
    payment.payment_status = 'success'
    payment.gateway_ref = payment_id
    
    if payment.payment_type == "featured_listing":
        from backend.skills.models import Skill
        skill = Skill.query.get(payment.target_ref_id)
        if skill:
            skill.is_featured = True
            current_expiry = skill.featured_until if (skill.featured_until and skill.featured_until > datetime.utcnow()) else datetime.utcnow()
            skill.featured_until = current_expiry + timedelta(days=7)
            
    db.session.commit()
    
    return jsonify({
        "success": True,
        "data": {
            "message": "Payment verified successfully",
            "paymentId": str(payment.id)
        }
    }), 200

@payments_bp.route('/webhook', methods=['POST'])
def razorpay_webhook():
    """
    Razorpay server-to-server webhook.
    No JWT required — but webhook signature MUST be verified before any processing.
    Always returns 200 to prevent Razorpay retry storms.
    """
    # ── 1. Signature check FIRST — before parsing JSON ───────────────────────
    signature = request.headers.get("X-Razorpay-Signature")
    if not signature:
        logger.warning("Webhook received without X-Razorpay-Signature header")
        return jsonify({"status": "ok"}), 200  # still 200 to avoid retries

    body = request.get_data()

    # ⚠️ SECURITY: verify_webhook_signature uses RAZORPAY_WEBHOOK_SECRET from env only
    if not verify_webhook_signature(body, signature):
        logger.warning("Invalid Razorpay webhook signature — request rejected")
        return jsonify({"status": "ok"}), 200  # still 200 to avoid retries

    # ── 2. Parse event ────────────────────────────────────────────────────────
    data = request.get_json(force=True) or {}
    event = data.get('event')
    payload = data.get('payload', {})
    logger.info(f"Razorpay webhook received: event={event}")

    # ── 3. payment.captured → mark success (idempotent) ──────────────────────
    if event == "payment.captured":
        try:
            entity = payload['payment']['entity']
            order_id = entity.get('order_id')
            payment_id_rzp = entity.get('id')

            payment = Payment.query.filter_by(gateway_ref=order_id).first()
            if not payment:
                logger.warning(f"Webhook payment.captured: no Payment found for order {order_id}")
            elif payment.payment_status == 'success':
                logger.info(f"Webhook payment.captured: already success for order {order_id} — skipping")
            else:
                payment.payment_status = 'success'
                payment.gateway_ref = payment_id_rzp

                if payment.payment_type == "featured_listing":
                    from backend.skills.models import Skill
                    skill = Skill.query.get(payment.target_ref_id)
                    if skill:
                        skill.is_featured = True
                        base = (
                            skill.featured_until
                            if (skill.featured_until and skill.featured_until > datetime.utcnow())
                            else datetime.utcnow()
                        )
                        skill.featured_until = base + timedelta(days=7)

                db.session.commit()
                logger.info(f"Webhook payment.captured: marked success for order {order_id}")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Webhook payment.captured processing error: {e}")

    # ── 4. payment.failed → mark failed (idempotent) ─────────────────────────
    elif event == "payment.failed":
        try:
            entity = payload['payment']['entity']
            order_id = entity.get('order_id')

            payment = Payment.query.filter_by(gateway_ref=order_id).first()
            if not payment:
                logger.warning(f"Webhook payment.failed: no Payment found for order {order_id}")
            elif payment.payment_status == 'success':
                # Never downgrade a captured payment — log and skip
                logger.warning(f"Webhook payment.failed: order {order_id} already success — skipping downgrade")
            else:
                payment.payment_status = 'failed'
                db.session.commit()
                logger.info(f"Webhook payment.failed: marked failed for order {order_id}")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Webhook payment.failed processing error: {e}")

    else:
        logger.info(f"Webhook: unhandled event type '{event}' — ignoring")

    # ── 5. Always 200 — non-200 triggers Razorpay retries ────────────────────
    return jsonify({"status": "ok"}), 200
