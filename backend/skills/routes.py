import os
import razorpay
from flask import Blueprint, request, jsonify
from backend.extensions import db
from backend.skills.models import Skill, SkillRequest
from backend.payments.models import Payment
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from sqlalchemy import and_, desc
from backend.auth.models import User
skills_bp = Blueprint('skills', __name__, url_prefix='/api/skills')
skill_requests_bp = Blueprint('skill_requests', __name__, url_prefix='/api/skill-requests')

VALID_CATEGORIES = ['Tech', 'Music', 'Design', 'Language', 'Fitness', 'Academic', 'Other']
VALID_MODES = ['online', 'offline', 'both']

def _serialize_skill(skill):
    return {
        "id": str(skill.id),
        "user_id": str(skill.user_id),
        "title": skill.title,
        "description": skill.description,
        "category": skill.category,
        "mode": skill.mode,
        "credits_per_session": skill.credits_per_session,
        "price_per_session": float(skill.price_per_session) if skill.price_per_session is not None else None,
        "is_active": skill.is_active,
        "is_featured": skill.is_featured,
        "featured_until": skill.featured_until.isoformat() if skill.featured_until else None,
        "created_at": skill.created_at.isoformat() if skill.created_at else None
    }

@skills_bp.route('', methods=['POST'])
@jwt_required()
def create_skill():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    
    title = data.get('title')
    category = data.get('category')
    mode = data.get('mode')
    
    if not title:
        return jsonify({"success": False, "error": "title is required"}), 400
        
    if category and category not in VALID_CATEGORIES:
        return jsonify({"success": False, "error": f"category must be one of: {', '.join(VALID_CATEGORIES)}"}), 400
        
    if mode and mode not in VALID_MODES:
        return jsonify({"success": False, "error": f"mode must be one of: {', '.join(VALID_MODES)}"}), 400
        
    new_skill = Skill(
        user_id=user_id,
        title=title,
        description=data.get('description'),
        category=category,
        mode=mode,
        credits_per_session=data.get('credits_per_session'),
        price_per_session=data.get('price_per_session')
    )
    
    db.session.add(new_skill)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "data": _serialize_skill(new_skill)
    }), 201

@skills_bp.route('', methods=['GET'])
def get_skills():
    category = request.args.get('category')
    mode = request.args.get('mode')
    q = request.args.get('q')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    
    query = Skill.query.join(User, Skill.user_id == User.id).filter(Skill.is_active == True)
    
    if category:
        query = query.filter(Skill.category == category)
    if mode:
        query = query.filter(Skill.mode == mode)
    if q:
        search_term = f"%{q}%"
        query = query.filter((Skill.title.ilike(search_term)) | (Skill.description.ilike(search_term)))
        
    active_featured = and_(Skill.is_featured == True, Skill.featured_until > datetime.utcnow())
    
    query = query.order_by(
        desc(active_featured),
        User.is_premium.desc(),
        User.teacher_score.desc(),
        User.sessions_taught.desc(),
        Skill.created_at.desc()
    )
    
    pagination = query.paginate(page=page, per_page=limit, error_out=False)
    
    return jsonify({
        "success": True,
        "data": [_serialize_skill(s) for s in pagination.items],
        "total": pagination.total,
        "page": page,
        "pages": pagination.pages
    }), 200

@skills_bp.route('/<string:skill_id>', methods=['GET'])
def get_skill(skill_id):
    skill = Skill.query.filter_by(id=skill_id, is_active=True).first()
    if not skill:
        return jsonify({"success": False, "error": "Skill not found"}), 404
        
    return jsonify({
        "success": True,
        "data": _serialize_skill(skill)
    }), 200

@skills_bp.route('/<string:skill_id>', methods=['PUT'])
@jwt_required()
def update_skill(skill_id):
    user_id = get_jwt_identity()
    skill = Skill.query.get(skill_id)
    
    if not skill or not skill.is_active:
        return jsonify({"success": False, "error": "Skill not found"}), 404
        
    if str(skill.user_id) != str(user_id):
        return jsonify({"success": False, "error": "Forbidden"}), 403
        
    data = request.get_json() or {}
    
    category = data.get('category')
    mode = data.get('mode')
    
    if category and category not in VALID_CATEGORIES:
        return jsonify({"success": False, "error": f"category must be one of: {', '.join(VALID_CATEGORIES)}"}), 400
        
    if mode and mode not in VALID_MODES:
        return jsonify({"success": False, "error": f"mode must be one of: {', '.join(VALID_MODES)}"}), 400
        
    allowed_fields = ['title', 'description', 'category', 'mode', 'credits_per_session', 'price_per_session']
    updated = False
    
    for field in allowed_fields:
        if field in data:
            setattr(skill, field, data[field])
            updated = True
            
    if updated:
        db.session.commit()
        
    return jsonify({
        "success": True,
        "data": _serialize_skill(skill)
    }), 200

@skills_bp.route('/<string:skill_id>', methods=['DELETE'])
@jwt_required()
def delete_skill(skill_id):
    user_id = get_jwt_identity()
    skill = Skill.query.get(skill_id)
    
    if not skill or not skill.is_active:
        return jsonify({"success": False, "error": "Skill not found"}), 404
        
    if str(skill.user_id) != str(user_id):
        return jsonify({"success": False, "error": "Forbidden"}), 403
        
    skill.is_active = False
    db.session.commit()
    
    return jsonify({
        "success": True,
        "data": None
    }), 200

@skills_bp.route('/<string:skill_id>/feature', methods=['POST'])
@jwt_required()
def feature_skill(skill_id):
    user_id = get_jwt_identity()
    skill = Skill.query.get(skill_id)
    
    if not skill or not skill.is_active:
        return jsonify({"success": False, "error": "Skill not found"}), 404
        
    if str(skill.user_id) != str(user_id):
        return jsonify({"success": False, "error": "Forbidden"}), 403
        
    data = request.get_json() or {}
    duration_days = data.get('durationDays', 7)
    
    gross_amount = 99.00
    
    key_id = os.environ.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
    
    if not key_id or not key_secret:
        return jsonify({"success": False, "error": "Razorpay not configured"}), 500
        
    client = razorpay.Client(auth=(key_id, key_secret))
    
    new_payment = Payment(
        payer_id=user_id,
        payee_id=None,
        session_id=None,
        payment_type="featured_listing",
        target_ref_id=skill.id,
        gross_amount=gross_amount,
        platform_fee=gross_amount,
        net_amount=0.00,
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

def _serialize_skill_request(req):
    return {
        "id": str(req.id),
        "user_id": str(req.user_id),
        "title": req.title,
        "description": req.description,
        "category": req.category,
        "created_at": req.created_at.isoformat() if req.created_at else None
    }

@skill_requests_bp.route('', methods=['POST'])
@jwt_required()
def create_skill_request():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    
    title = data.get('title')
    category = data.get('category')
    
    if not title:
        return jsonify({"success": False, "error": "title is required"}), 400
        
    if category and category not in VALID_CATEGORIES:
        return jsonify({"success": False, "error": f"category must be one of: {', '.join(VALID_CATEGORIES)}"}), 400
        
    new_request = SkillRequest(
        user_id=user_id,
        title=title,
        description=data.get('description'),
        category=category
    )
    
    db.session.add(new_request)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "data": _serialize_skill_request(new_request)
    }), 201

@skill_requests_bp.route('', methods=['GET'])
def get_skill_requests():
    category = request.args.get('category')
    q = request.args.get('q')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    
    query = SkillRequest.query
    
    if category:
        query = query.filter(SkillRequest.category == category)
    if q:
        search_term = f"%{q}%"
        query = query.filter((SkillRequest.title.ilike(search_term)) | (SkillRequest.description.ilike(search_term)))
        
    pagination = query.order_by(SkillRequest.created_at.desc()).paginate(page=page, per_page=limit, error_out=False)
    
    return jsonify({
        "success": True,
        "data": [_serialize_skill_request(r) for r in pagination.items],
        "total": pagination.total,
        "page": page,
        "pages": pagination.pages
    }), 200
