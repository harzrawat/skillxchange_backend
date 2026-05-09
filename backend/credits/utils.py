from backend.extensions import db
from backend.credits.models import CreditTransaction
from backend.auth.models import User
from backend.matching.models import Session

def log_transaction(user_id, delta, reason, ref_id=None):
    transaction = CreditTransaction(
        user_id=user_id,
        delta=delta,
        reason=reason,
        ref_id=ref_id
    )
    db.session.add(transaction)

def transfer_credits(session_id):
    session = Session.query.get(session_id)

    if not session:
        raise ValueError("Session not found")

    if session.session_type != "credit":
        return

    if session.status != "completed":
        raise ValueError("Session not completed")

    learner = User.query.get(session.learner_id)
    teacher = User.query.get(session.teacher_id)
    amount = session.credits_used

    if not learner or not teacher:
        raise ValueError("User not found")

    if learner.credits < amount:
        raise ValueError("Insufficient credits")

    learner.credits -= amount
    log_transaction(user_id=learner.id, delta=-amount, reason="session_taken", ref_id=session_id)

    teacher.credits += amount
    log_transaction(user_id=teacher.id, delta=amount, reason="session_taught", ref_id=session_id)

    db.session.commit()
