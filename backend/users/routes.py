from flask import Blueprint, request, jsonify
from backend.extensions import db
from backend.auth.models import User
from backend.skills.models import Skill
from flask_jwt_extended import jwt_required, get_jwt_identity

users_bp = Blueprint('users', __name__, url_prefix='/api/users')

@users_bp.route('/<string:user_id>', methods=['GET'])
def get_public_profile(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({
            "success": False, 
            "error": "User not found"
        }), 404
        
    return jsonify({
        "success": True,
        "data": {
            "id": str(user.id),
            "name": user.name,
            "bio": user.bio,
            "avatar_url": user.avatar_url,
            "college": user.college,
            "city": user.city,
            "credits": user.credits,
            "is_premium": user.is_premium,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
    }), 200

@users_bp.route('/<string:user_id>', methods=['PUT'])
@jwt_required()
def update_profile(user_id):
    current_user_id = get_jwt_identity()
    
    if str(current_user_id) != str(user_id):
        return jsonify({
            "success": False, 
            "error": "Forbidden"
        }), 403
        
    user = User.query.get(user_id)
    if not user:
        return jsonify({
            "success": False, 
            "error": "User not found"
        }), 404
        
    data = request.get_json() or {}
    
    # Partial update: only update allowed fields
    allowed_fields = ['name', 'bio', 'avatar_url', 'college', 'city']
    
    updated = False
    for field in allowed_fields:
        if field in data:
            setattr(user, field, data[field])
            updated = True
            
    if updated:
        db.session.commit()
        
    return jsonify({
        "success": True,
        "data": {
            "id": str(user.id),
            "name": user.name,
            "bio": user.bio,
            "avatar_url": user.avatar_url,
            "college": user.college,
            "city": user.city,
            "credits": user.credits,
            "is_premium": user.is_premium,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
    }), 200

@users_bp.route('/<string:user_id>/skills', methods=['GET'])
def get_user_skills(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({
            "success": False, 
            "error": "User not found"
        }), 404

    skills = Skill.query.filter_by(user_id=user_id, is_active=True).order_by(Skill.created_at.desc()).all()
    
    data = []
    for skill in skills:
        data.append({
            "id": str(skill.id),
            "user_id": str(skill.user_id),
            "title": skill.title,
            "description": skill.description,
            "category": skill.category,
            "mode": skill.mode,
            "credits_per_session": skill.credits_per_session,
            "price_per_session": float(skill.price_per_session) if skill.price_per_session is not None else None,
            "is_active": skill.is_active,
            "created_at": skill.created_at.isoformat() if skill.created_at else None
        })
        
    return jsonify({
        "success": True,
        "data": data
    }), 200
