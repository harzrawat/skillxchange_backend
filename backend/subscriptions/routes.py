import os
import razorpay
import hmac
import hashlib
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.auth.models import User
from backend.payments.models import Payment

subscriptions_bp = Blueprint('subscriptions', __name__)

@subscriptions_bp.route('/subscribe', methods=['POST'])
@jwt_required()
def subscribe():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    
    plan_type = data.get('planType')
    if plan_type not in ['monthly', 'annual']:
        return jsonify({"success": False, "error": "Invalid planType"}), 400
        
    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404
        
    if user.is_premium:
        return jsonify({"success": False, "error": "User is already a premium member"}), 400
        
    if plan_type == 'monthly':
        gross_amount = 299.00
    else:
        gross_amount = 2499.00
        
    key_id = os.environ.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
    
    if not key_id or not key_secret:
        return jsonify({"success": False, "error": "Razorpay not configured"}), 500
        
    client = razorpay.Client(auth=(key_id, key_secret))
    
    platform_fee = gross_amount
    net_amount = 0.00
    
    new_payment = Payment(
        payer_id=user.id,
        payee_id=None,
        session_id=None,
        payment_type="subscription",
        target_ref_id=None,
        gross_amount=gross_amount,
        platform_fee=platform_fee,
        net_amount=net_amount,
        payment_status='pending'
    )
    
    db.session.add(new_payment)
    db.session.flush()
    
    try:
        order = client.order.create({
            "amount": int(gross_amount * 100),
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
            "amount": gross_amount,
            "currency": "INR",
            "keyId": key_id
        }
    }), 200

@subscriptions_bp.route('/verify', methods=['POST'])
@jwt_required()
def verify_subscription():
    user_id = get_jwt_identity()
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
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404
        
    user.is_premium = True
    
    if payment.gross_amount == 2499.00:
        expiry_date = datetime.utcnow() + timedelta(days=365)
    else:
        expiry_date = datetime.utcnow() + timedelta(days=30)
        
    user.premium_expiry = expiry_date
    db.session.commit()
    
    expiry_str = expiry_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    return jsonify({
        "success": True,
        "data": {
            "message": "Premium subscription activated successfully!",
            "premiumExpiry": expiry_str
        }
    }), 200
