from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.auth.models import User
from backend.credits.models import CreditTransaction

credits_bp = Blueprint('credits', __name__, url_prefix='/api/credits')

@credits_bp.route('/balance', methods=['GET'])
@jwt_required()
def get_balance():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404
        
    return jsonify({
        "success": True,
        "data": {
            "userId": str(user.id),
            "credits": user.credits
        }
    }), 200

@credits_bp.route('/history', methods=['GET'])
@jwt_required()
def get_history():
    user_id = get_jwt_identity()
    
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    query = CreditTransaction.query.filter_by(user_id=user_id)
    total = query.count()
    
    transactions = query.order_by(CreditTransaction.created_at.desc())\
        .offset((page - 1) * limit)\
        .limit(limit)\
        .all()
        
    data = []
    for tx in transactions:
        data.append({
            "transactionId": str(tx.id),
            "delta": tx.delta,
            "reason": tx.reason,
            "refId": str(tx.ref_id) if tx.ref_id else None,
            "createdAt": tx.created_at.isoformat() if tx.created_at else None
        })
        
    return jsonify({
        "success": True,
        "data": data,
        "total": total,
        "page": page
    }), 200
