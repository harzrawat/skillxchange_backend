import bcrypt
from datetime import timedelta
from flask_jwt_extended import create_access_token

def hash_password(plain_text: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_text.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain_text: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain_text.encode('utf-8'), hashed.encode('utf-8'))

def generate_token(user_id, email: str) -> str:
    expires = timedelta(days=7)
    return create_access_token(
        identity=str(user_id),
        additional_claims={"email": email},
        expires_delta=expires
    )
