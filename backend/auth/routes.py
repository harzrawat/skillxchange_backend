from flask import Blueprint, request, jsonify
from backend.extensions import db
from backend.auth.models import User
from backend.auth.utils import hash_password, generate_token, verify_password
from flask_jwt_extended import jwt_required, get_jwt_identity

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    
    # Validate required fields
    if not name or not email or not password:
        return jsonify({
            "success": False,
            "error": "name, email, and password are required"
        }), 400
        
    # Validate password length
    if len(password) < 8:
        return jsonify({
            "success": False,
            "error": "password must be at least 8 characters"
        }), 400
        
    # Check email uniqueness
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({
            "success": False,
            "error": "Email already registered"
        }), 409
        
    # Hash password before saving
    hashed_pwd = hash_password(password)
    
    # Create new user
    new_user = User(
        name=name,
        email=email,
        password=hashed_pwd,
        credits=50
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    # Generate token
    token = generate_token(new_user.id, new_user.email)
    
    # Return response in standard format
    return jsonify({
        "success": True,
        "data": {
            "token": token,
            "user": {
                "id": str(new_user.id),
                "name": new_user.name,
                "email": new_user.email,
                "credits": new_user.credits
            }
        }
    }), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({
            "success": False,
            "error": "email and password are required"
        }), 400
        
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({
            "success": False,
            "error": "User not found"
        }), 404
        
    if not verify_password(password, user.password):
        return jsonify({
            "success": False,
            "error": "Invalid credentials"
        }), 401
        
    token = generate_token(user.id, user.email)
    
    return jsonify({
        "success": True,
        "data": {
            "token": token,
            "user": {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "credits": user.credits
            }
        }
    }), 200

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    user_id = get_jwt_identity()
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
            "email": user.email,
            "bio": user.bio,
            "avatar_url": user.avatar_url,
            "college": user.college,
            "city": user.city,
            "credits": user.credits,
            "is_premium": user.is_premium,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
    }), 200
