from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.matching.models import Match, Session
from backend.skills.models import Skill
from backend.auth.models import User
from backend.payments.models import Payment
from sqlalchemy import or_
from datetime import datetime, timezone, timedelta
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
        
        session = Session.query.filter_by(match_id=match.id).first()
        
        is_paid = False
        if session and match.session_type == 'paid':
            payment = Payment.query.filter_by(session_id=session.id, payment_status='success').first()
            if payment:
                is_paid = True
        
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
            "session": {
                "sessionId": str(session.id),
                "status": session.status,
                "videoCallUrl": session.video_call_url,
                "creditsTransferred": session.credits_used,
                "isPaid": is_paid,
                "createdAt": session.created_at.isoformat() if hasattr(session, 'created_at') and session.created_at else None,
                "completedAt": session.completed_at.isoformat() if session.completed_at else None
            } if session else None,
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
        
    # Step 1: Mark session complete
    session.status = 'completed'
    session.completed_at = datetime.now(timezone.utc)
    
    if session.session_type == 'credit':
        # Step 2: Credit sessions — transfer credits immediately; rollback on failure
        try:
            transfer_credits(session.id)
        except ValueError as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)}), 400
            
    elif session.session_type == 'paid':
        # Step 3: Phase 3: trigger Razorpay Route transfer here
        pass
        
    # Step 4: Mark parent match as completed
    match = Match.query.get(session.match_id)
    if match:
        match.status = 'completed'
        
    # Step 5: Update teacher stats and recalculate score (cap at 5.0)
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
        return jsonify({"success": False, "error": "Not authorized for this session"}), 403

    if session.status not in ('scheduled', 'in_session'):
        return jsonify({"success": False, "error": "Session is not currently active"}), 400

    room_name = f"skillxchange-{session_id}"
    if not session.video_call_url:
        session.video_call_url = f"https://meet.jit.si/{room_name}"
        db.session.commit()

    role = 'teacher' if str(session.teacher_id) == str(user_id) else 'learner'
    user = User.query.get(user_id)

    return jsonify({
        "success": True,
        "data": {
            "sessionId": session_id,
            "roomName": room_name,
            "videoCallUrl": session.video_call_url,
            "participant": {
                "displayName": user.name if user else "Participant",
                "role": role
            }
        }
    }), 200


@sessions_bp.route('/<string:session_id>/join', methods=['POST'])
@jwt_required()
def session_join(session_id):
    """Record that a participant has entered the Jitsi room.

    - Transitions status: "scheduled" → "in_session" (idempotent if already in_session).
    - 403 if caller is neither teacher nor learner of this session.
    """
    user_id = get_jwt_identity()
    session = Session.query.get(session_id)

    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404

    if str(session.teacher_id) != str(user_id) and str(session.learner_id) != str(user_id):
        return jsonify({"success": False, "error": "Not authorized for this session"}), 403

    # Idempotent status transition: scheduled → in_session
    if session.status == 'scheduled':
        session.status = 'in_session'
        db.session.commit()
    # If already 'in_session' or 'completed', no-op (idempotent)

    return jsonify({
        "success": True,
        "data": {
            "sessionId": session_id,
            "status": session.status
        }
    }), 200


@sessions_bp.route('/<string:session_id>/leave', methods=['POST'])
@jwt_required()
def session_leave(session_id):
    """Record that a participant has left the Jitsi room.

    - Does NOT change session status (only /complete does that).
    - 403 if caller is neither teacher nor learner of this session.
    """
    user_id = get_jwt_identity()
    session = Session.query.get(session_id)

    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404

    if str(session.teacher_id) != str(user_id) and str(session.learner_id) != str(user_id):
        return jsonify({"success": False, "error": "Not authorized for this session"}), 403

    role = 'teacher' if str(session.teacher_id) == str(user_id) else 'learner'

    # Best-effort log — no status change; status moves only via /complete
    print(f"[session_leave] session={session_id} user={user_id} role={role} left at {datetime.now(timezone.utc).isoformat()}")

    return jsonify({
        "success": True,
        "data": {
            "sessionId": session_id,
            "message": "Leave recorded"
        }
    }), 200


@sessions_bp.route('/<string:session_id>/no-show', methods=['POST'])
@jwt_required()
def session_no_show(session_id):
    """Learner reports a teacher no-show after the 15-minute grace period.

    - Learner only — teacher calling this endpoint receives 403.
    - Session must be 'scheduled' or 'in_session'.
    - Must be at least 15 minutes past session.scheduled_at.
    - Cancels the session and flags any successful payment for refund.

    Phase 3: trigger Razorpay refund via client.payment.refund(payment_id)
    """
    user_id = get_jwt_identity()
    session = Session.query.get(session_id)

    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404

    # Learner-only endpoint — teachers are not permitted
    if str(session.learner_id) != str(user_id):
        return jsonify({"success": False, "error": "Only the learner can report a no-show"}), 403

    # Session must still be active to be reportable
    if session.status not in ('scheduled', 'in_session'):
        return jsonify({"success": False, "error": "Session is not in a reportable state"}), 400

    # Enforce 15-minute grace period from scheduled_at
    if session.scheduled_at is None:
        return jsonify({"success": False, "error": "Session has no scheduled time — cannot validate no-show"}), 400

    # scheduled_at is TIMESTAMP WITH TIME ZONE — ORM always returns an aware datetime
    grace_deadline = session.scheduled_at + timedelta(minutes=15)
    now_utc = datetime.now(timezone.utc)

    if now_utc < grace_deadline:
        return jsonify({"success": False, "error": "Too early to report no-show"}), 400

    # Cancel the session
    session.status = 'cancelled'

    # Find the successful payment for this session (paid sessions only)
    payment = Payment.query.filter_by(
        session_id=session.id,
        payment_status='success'
    ).first()

    if payment:
        # Phase 3: trigger Razorpay refund via client.payment.refund(payment_id)
        payment.payment_status = 'refund_requested'

    db.session.commit()

    return jsonify({
        "success": True,
        "data": {
            "message": "No-show reported. Refund will be processed."
        }
    }), 200
