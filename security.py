from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

# Use bcrypt with proper settings
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,  # Explicitly set rounds
)

class Security:
    def __init__(self):
        self.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 60 * 24 * 7  # 7 days
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        # Truncate password to 72 bytes if needed (bcrypt limit)
        if len(password.encode('utf-8')) > 72:
            password = password[:72]
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        # Truncate password to 72 bytes if needed
        if len(plain_password.encode('utf-8')) > 72:
            plain_password = plain_password[:72]
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except ValueError as e:
            if "password cannot be longer than 72 bytes" in str(e):
                # Try with truncated password
                return pwd_context.verify(plain_password[:72], hashed_password)
            raise e
    
    def create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
    
    def decode_token(self, token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError:
            return None
    
    def get_current_user(self, token: str) -> Optional[dict]:
        payload = self.decode_token(token)
        if payload:
            return {
                "user_id": payload.get("sub"),
                "user_category": payload.get("user_category"),
                "email": payload.get("email")
            }
        return None

security = Security()