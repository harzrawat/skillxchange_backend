from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.matching.models import Match, Session
from backend.skills.models import Skill
from backend.auth.models import User
from sqlalchemy import or_
from datetime import datetime, timezone
from backend.credits.utils import transfer_credits

matching_bp = Blueprint('matching', __name__, url_prefix='/api/matches')

@matching_bp.route('', methods=['POST'])
@jwt_required()
def create_match():
    learner_id = get_jwt_identity()
    data = request.get_json() or {}
    
    skill_id = data.get('skillId')
    session_type = data.get('sessionType')
    
    if not skill_id or not session_type:
        return jsonify({"success": False, "error": "skillId and sessionType are required"}), 400
        
    if session_type not in ['credit', 'paid']:
        return jsonify({"success": False, "error": "sessionType must be 'credit' or 'paid'"}), 400
        
    skill = Skill.query.get(skill_id)
    if not skill:
        return jsonify({"success": False, "error": "Skill not found"}), 404
        
    if session_type == 'credit' and not skill.credits_per_session:
        return jsonify({"success": False, "error": "Skill does not support credit sessions"}), 400
        
    if session_type == 'paid' and not skill.price_per_session:
        return jsonify({"success": False, "error": "Skill does not support paid sessions"}), 400
        
    teacher_id = str(skill.user_id)
    
    if str(learner_id) == teacher_id:
        return jsonify({"success": False, "error": "Cannot match with yourself"}), 400
        
    learner = User.query.get(learner_id)
    if not learner:
        return jsonify({"success": False, "error": "Learner not found"}), 404
        
    if not learner.is_premium:
        active_matches_count = Match.query.filter(
            or_(Match.learner_id == learner_id, Match.teacher_id == learner_id),
            Match.status.in_(['pending', 'accepted'])
        ).count()
        
        if active_matches_count >= 3:
            return jsonify({"success": False, "error": "Free users can have a maximum of 3 pending or accepted matches"}), 403
            
    existing_match = Match.query.filter_by(
        learner_id=learner_id,
        skill_id=skill_id,
        status='pending'
    ).first()
    
    if existing_match:
        return jsonify({"success": False, "error": "Duplicate match request"}), 409
        
    new_match = Match(
        teacher_id=teacher_id,
        learner_id=learner_id,
        skill_id=skill_id,
        session_type=session_type,
        status='pending'
    )
    
    db.session.add(new_match)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "data": {
            "matchId": str(new_match.id),
            "teacherId": str(new_match.teacher_id),
            "learnerId": str(new_match.learner_id),
            "skillId": str(new_match.skill_id),
            "sessionType": new_match.session_type,
            "status": new_match.status,
            "createdAt": new_match.created_at.isoformat() if new_match.created_at else None
        }
    }), 201

@matching_bp.route('/me', methods=['GET'])
@jwt_required()
def get_my_matches():
    user_id = get_jwt_identity()
    role = request.args.get('role')
    status = request.args.get('status')
    
    query = Match.query
    
    if role == 'teacher':
        query = query.filter_by(teacher_id=user_id)
    elif role == 'learner':
        query = query.filter_by(learner_id=user_id)
    else:
        query = query.filter(or_(Match.teacher_id == user_id, Match.learner_id == user_id))
        
    if status:
        query = query.filter_by(status=status)
        
    matches = query.order_by(Match.created_at.desc()).all()
    
    data = []
    for match in matches:
        skill = Skill.query.get(match.skill_id)
        teacher = User.query.get(match.teacher_id)
        learner = User.query.get(match.learner_id)
        
        data.append({
            "matchId": str(match.id),
            "status": match.status,
            "sessionType": match.session_type,
            "skill": {
                "skillId": str(skill.id),
                "title": skill.title,
                "creditsPerSession": skill.credits_per_session
            } if skill else None,
            "teacher": {
                "userId": str(teacher.id),
                "name": teacher.name,
                "avatarUrl": teacher.avatar_url
            } if teacher else None,
            "learner": {
                "userId": str(learner.id),
                "name": learner.name,
                "avatarUrl": learner.avatar_url
            } if learner else None,
            "createdAt": match.created_at.isoformat() if match.created_at else None
        })
        
    return jsonify({
        "success": True,
        "data": data,
        "total": len(data)
    }), 200

@matching_bp.route('/<string:match_id>/respond', methods=['PUT'])
@jwt_required()
def respond_to_match(match_id):
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    
    action = data.get('action')
    if action not in ['accepted', 'rejected']:
        return jsonify({"success": False, "error": "Invalid action value"}), 400
        
    match = Match.query.get(match_id)
    if not match:
        return jsonify({"success": False, "error": "Match not found"}), 404
        
    if str(match.teacher_id) != str(user_id):
        return jsonify({"success": False, "error": "Not the teacher"}), 403
        
    if match.status != 'pending':
        return jsonify({"success": False, "error": "Already responded"}), 400
        
    match.status = action
    
    session_data = None
    if action == 'accepted':
        skill = Skill.query.get(match.skill_id)
        credits_used = skill.credits_per_session if match.session_type == 'credit' else None
        
        amount_paid = None
        platform_fee = None
        if match.session_type == 'paid' and skill.price_per_session is not None:
            amount_paid = float(skill.price_per_session)
            platform_fee = amount_paid * 0.15
            
        new_session = Session(
            match_id=match.id,
            teacher_id=match.teacher_id,
            learner_id=match.learner_id,
            skill_id=match.skill_id,
            session_type=match.session_type,
            credits_used=credits_used,
            amount_paid=amount_paid,
            platform_fee=platform_fee,
            status='scheduled'
        )
        db.session.add(new_session)
        db.session.flush() # To get the new_session.id
        
        session_data = {
            "sessionId": str(new_session.id),
            "status": new_session.status,
            "createdAt": new_session.created_at.isoformat() if hasattr(new_session, 'created_at') and new_session.created_at else None
        }
        
    db.session.commit()
    
    response_data = {
        "matchId": str(match.id),
        "status": match.status
    }
    
    if session_data:
        response_data["session"] = session_data
        
    return jsonify({
        "success": True,
        "data": response_data
    }), 200

sessions_bp = Blueprint('sessions', __name__, url_prefix='/api/sessions')

@sessions_bp.route('/<string:session_id>/complete', methods=['PUT'])
@jwt_required()
def complete_session(session_id):
    user_id = get_jwt_identity()
    
    session = Session.query.get(session_id)
    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404
        
    if str(session.teacher_id) != str(user_id) and str(session.learner_id) != str(user_id):
        return jsonify({"success": False, "error": "Not authorized for session"}), 403
        
    if session.status == 'completed':
        return jsonify({"success": False, "error": "Session already completed"}), 400
        
    session.status = 'completed'
    session.completed_at = datetime.now(timezone.utc)
    
    if session.session_type == 'credit':
        try:
            transfer_credits(session.id)
        except ValueError as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)}), 400
            
    match = Match.query.get(session.match_id)
    if match:
        match.status = 'completed'
        
    teacher = User.query.get(session.teacher_id)
    if teacher:
        if teacher.sessions_taught is None:
            teacher.sessions_taught = 0
        teacher.sessions_taught += 1
        
        if teacher.teacher_score is None:
            teacher.teacher_score = 5.0
        # Simple recalculation logic for phase 2: increase slightly upon successful completion
        # Cap at 5.0
        new_score = float(teacher.teacher_score) + 0.05
        teacher.teacher_score = min(5.0, new_score)
        
    db.session.commit()
    
    return jsonify({
        "success": True,
        "data": {
            "sessionId": str(session.id),
            "status": session.status,
            "completedAt": session.completed_at.isoformat(),
            "creditsTransferred": session.credits_used if session.session_type == 'credit' else None
        }
    }), 200

@sessions_bp.route('/<string:session_id>/video-call', methods=['GET'])
@jwt_required()
def get_video_call(session_id):
    user_id = get_jwt_identity()
    session = Session.query.get(session_id)
    
    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404
        
    if str(session.teacher_id) != str(user_id) and str(session.learner_id) != str(user_id):
        return jsonify({"success": False, "error": "Not authorized for session"}), 403
        
    if not session.video_call_url:
        session.video_call_url = f"https://meet.jit.si/skillxchange-{session_id}"
        db.session.commit()
        
    return jsonify({
        "success": True,
        "data": {
            "videoCallUrl": session.video_call_url
        }
    }), 200
