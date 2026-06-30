from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
import jwt
import os

from app.data.db import get_db, User
from app.api.schemas import UserCreate, UserLogin, Token, ForgotPasswordRequest, ResetPasswordRequest
from sqlalchemy import text
import smtplib
from email.message import EmailMessage
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel
import uuid

class GoogleLogin(BaseModel):
    credential: str

GOOGLE_CLIENT_ID = "1090187417746-l0c0q3reb7hsfivsumcfbkahfu3jmfmr.apps.googleusercontent.com"




SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "super-secret-fallback-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/fix-db")
def fix_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR;"))
        db.commit()
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

@router.post("/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    try:
        db_user = db.query(User).filter(User.email == user.email).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        hashed_password = get_password_hash(user.password)
        new_user = User(email=user.email, full_name=user.full_name, password_hash=hashed_password)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": new_user.email}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")

@router.post("/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    try:
        db_user = db.query(User).filter(User.email == user.email).first()
        if not db_user or not verify_password(user.password, db_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": db_user.email}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")

@router.get("/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email, "full_name": current_user.full_name}

@router.post("/google", response_model=Token)
def google_login(login_data: GoogleLogin, db: Session = Depends(get_db)):
    try:
        import requests
        
        # Verify the Google access token
        response = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {login_data.credential}"}
        )
        if response.status_code != 200:
            raise ValueError("Invalid Google token")
            
        idinfo = response.json()

        email = idinfo.get("email")
        full_name = idinfo.get("name")
        
        if not email:
            raise HTTPException(status_code=400, detail="No email provided by Google")

        # Find or create user
        db_user = db.query(User).filter(User.email == email).first()
        if not db_user:
            # Create a user with a random unguessable password hash
            random_pw_hash = get_password_hash(f"google_oauth_{uuid.uuid4()}")
            db_user = User(
                email=email, 
                full_name=full_name, 
                password_hash=random_pw_hash
            )
            db.add(db_user)
            db.commit()
            db.refresh(db_user)

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": db_user.email}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Google token")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

def send_reset_email(to_email: str, token: str):
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    
    if not smtp_user or not smtp_pass:
        print(f"Warning: SMTP not configured. Reset link for {to_email}: https://ishimusa-psi.vercel.app/?reset_token={token}")
        return

    msg = EmailMessage()
    msg['Subject'] = 'AI Architect - Password Reset'
    msg['From'] = f"AI Architect <{smtp_user}>"
    msg['To'] = to_email

    reset_link = f"https://ishimusa-psi.vercel.app/?reset_token={token}"
    msg.set_content(f"You requested a password reset. Click the link below to reset your password:\n\n{reset_link}\n\nThis link will expire in 15 minutes.")
    
    msg.add_alternative(f"""
    <html>
      <body>
        <p>You requested a password reset for AI Architect.</p>
        <p><a href="{reset_link}">Click here to reset your password</a></p>
        <p>This link will expire in 15 minutes.</p>
      </body>
    </html>
    """, subtype='html')

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send email: {e}")

@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        # We still return success to prevent email enumeration
        return {"message": "If an account exists, a password reset link has been sent."}
    
    # Create reset token (valid for 15 mins)
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode = {"sub": user.email, "type": "reset", "exp": expire}
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    send_reset_email(user.email, token)
    return {"message": "If an account exists, a password reset link has been sent."}

@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(req.token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "reset":
            raise HTTPException(status_code=400, detail="Invalid token type")
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=400, detail="Invalid token payload")
            
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        user.password_hash = get_password_hash(req.new_password)
        db.commit()
        return {"message": "Password reset successfully"}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Reset token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid reset token")
