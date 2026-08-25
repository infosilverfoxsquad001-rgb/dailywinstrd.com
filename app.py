import os
import secrets
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(BASE_DIR, "database", "dailywins.db")
).replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_code = db.Column(db.String(6), nullable=True)
    verification_expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def public_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "verified": self.verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def token_for(email):
    return serializer.dumps({"email": email})


def email_from_token(token):
    data = serializer.loads(token, max_age=86400)
    return data["email"]

def generate_code():
    return str(secrets.randbelow(900000) + 100000)


@app.get("/")
def home():
    return jsonify({
        "name": "DAILY WINS Flask API",
        "status": "online",
        "mode": "demo",
        "message": "API is running."
    })


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/auth/register")
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

    user = User(
        full_name=full_name,
        email=email,
        password_hash=generate_password_hash(password),
        verified=False,
    )
    user.verification_code = generate_code()
    user.verification_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    db.session.add(user)
    db.session.commit()

    return jsonify({
        "message": "Registration successful. Verification code generated and ready to email.",
        "user": user.public_dict(),
        "verification_code": user.verification_code
    }), 201


@app.post("/api/auth/verify-email")
def verify_email():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    code = str(data.get("code", "")).strip()

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.verification_code != code:
        return jsonify({"error": "Invalid verification code"}), 400

    if not user.verification_expires_at or user.verification_expires_at < datetime.now(timezone.utc):
        return jsonify({"error": "Verification code expired"}), 400

    user.verified = True
    user.verification_code = None
    db.session.commit()

    return jsonify({"message": "Email verified successfully. You can now log in."})

@app.post("/api/auth/resend-code")
def resend_code():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error":"User not found"}),404
    user.verification_code = generate_code()
    user.verification_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.session.commit()
    return jsonify({"message":"New code generated","verification_code":user.verification_code})


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    if not user.verified:
        return jsonify({"error": "Please verify your email first"}), 403

    # This starter deliberately does not issue a production session/JWT.
    return jsonify({
        "message": "Login successful",
        "user": user.public_dict()
    })


@app.get("/api/users/<int:user_id>")
def get_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": user.public_dict()})


@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized.")


with app.app_context():
    os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
