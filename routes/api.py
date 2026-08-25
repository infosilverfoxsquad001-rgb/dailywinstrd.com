
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from email_service import send_email
from models.user import User

api_bp = Blueprint("api", __name__, url_prefix="/api")

def code():
    return f"{secrets.randbelow(1_000_000):06d}"

def referral():
    value = secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:12].upper()
    while User.query.filter_by(referral_code=value).first():
        value = secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:12].upper()
    return value

@api_bp.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    full_name = str(data.get("full_name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if not full_name or not email or not password:
        return jsonify({"error": "full_name, email and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists"}), 409

    names = full_name.split()
    first_name = names[0]
    last_name = " ".join(names[1:]) or "User"
    user = User(
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=generate_password_hash(password),
        country=str(data.get("country", "")).strip() or None,
        country_code=str(data.get("country_code", "")).strip() or None,
        phone=str(data.get("phone", "")).strip() or None,
        currency=str(data.get("currency", "USD")).strip() or "USD",
        currency_symbol=str(data.get("currency_symbol", "$")).strip() or "$",
        referral_code=referral(),
        verified=False,
        verification_code=code(),
        verification_expires_at=datetime.now(timezone.utc) + timedelta(
            minutes=current_app.config["VERIFICATION_MINUTES"]
        ),
    )
    db.session.add(user)
    db.session.commit()

    send_email(
        user.email,
        "DAILYWINS email verification code",
        f"Your DAILYWINS verification code is: {user.verification_code}\n"
        f"It expires in {current_app.config['VERIFICATION_MINUTES']} minutes.",
    )
    response = {"message": "Registration successful. Check your email for the verification code."}
    if current_app.config["ALLOW_DEV_VERIFICATION_CODE"]:
        response["development_verification_code"] = user.verification_code
    return jsonify(response), 201

@api_bp.post("/auth/verify-email")
def verify():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    entered = str(data.get("code", "")).strip()
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.verification_code != entered:
        return jsonify({"error": "Invalid verification code"}), 400
    if not user.verification_expires_at or user.verification_expires_at < datetime.now(timezone.utc):
        return jsonify({"error": "Verification code expired"}), 400
    user.verified = True
    user.verification_code = None
    user.verification_expires_at = None
    db.session.commit()
    return jsonify({"message": "Email verified successfully"})

@api_bp.post("/auth/resend-code")
def resend():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.verified:
        return jsonify({"error": "Email already verified"}), 400
    user.verification_code = code()
    user.verification_expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=current_app.config["VERIFICATION_MINUTES"]
    )
    db.session.commit()
    send_email(
        user.email,
        "DAILYWINS new verification code",
        f"Your new verification code is: {user.verification_code}\n"
        f"It expires in {current_app.config['VERIFICATION_MINUTES']} minutes.",
    )
    return jsonify({"message": "New verification code sent"})

@api_bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401
    if not user.verified:
        return jsonify({"error": "Please verify your email first"}), 403
    session.clear()
    session["user_id"] = user.id
    session["user_role"] = user.role
    return jsonify({"message": "Login successful", "user": user.public_dict()})

@api_bp.get("/me")
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"authenticated": False})
    user = db.session.get(User, user_id)
    if not user:
        session.clear()
        return jsonify({"authenticated": False})
    return jsonify({"authenticated": True, "user": user.public_dict()})
