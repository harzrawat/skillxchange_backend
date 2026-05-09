import os
import hmac
import hashlib
import razorpay
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.matching.models import Session
from backend.payments.models import Payment

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
    if not gross_amount:
        return jsonify({"success": False, "error": "Session has no amount"}), 400
        
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
            "amount": int(float(gross_amount) * 100),
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
        
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
    if not key_secret:
        return jsonify({"success": False, "error": "Razorpay not configured"}), 500
        
    msg = f"{order_id}|{payment_id}"
    expected_sig = hmac.new(
        key_secret.encode('utf-8'),
        msg.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_sig, signature):
        return jsonify({"success": False, "error": "Invalid signature"}), 400
        
    payment = Payment.query.filter_by(gateway_ref=order_id).first()
    if not payment:
        return jsonify({"success": False, "error": "Payment not found"}), 404
        
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
    webhook_secret = os.environ.get('RAZORPAY_WEBHOOK_SECRET')
    if not webhook_secret:
        return jsonify({"status": "error"}), 500
        
    signature = request.headers.get("X-Razorpay-Signature")
    if not signature:
        return jsonify({"status": "missing signature"}), 400
        
    body = request.get_data()
    
    expected_sig = hmac.new(
        webhook_secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_sig, signature):
        return jsonify({"status": "invalid signature"}), 400
        
    data = request.get_json() or {}
    event = data.get('event')
    payload = data.get('payload')
    
    if event == "payment.captured":
        try:
            payment_entity = payload['payment']['entity']
            order_id = payment_entity.get('order_id')
            payment_id = payment_entity.get('id')
            
            payment = Payment.query.filter_by(gateway_ref=order_id).first()
            if payment and payment.payment_status != 'success':
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
        except Exception:
            db.session.rollback()
            
    elif event == "payment.failed":
        try:
            payment_entity = payload['payment']['entity']
            order_id = payment_entity.get('order_id')
            
            payment = Payment.query.filter_by(gateway_ref=order_id).first()
            if payment:
                payment.payment_status = 'failed'
                db.session.commit()
        except Exception:
            db.session.rollback()
            
    return jsonify({"status": "ok"}), 200
