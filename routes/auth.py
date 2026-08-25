
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from email_service import send_email
from models.user import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

def generate_code():
    return f"{secrets.randbelow(1_000_000):06d}"

def generate_referral_code():
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:12].upper()

def safe_user_id():
    return session.get("user_id")

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        full_name = f"{first_name} {last_name}".strip()
        email = request.form.get("email", "").strip().lower()
        country = request.form.get("country", "").strip()
        country_code = request.form.get("country_code", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        currency = request.form.get("currency", "USD").strip() or "USD"
        currency_symbol = request.form.get("currency_symbol", "$").strip() or "$"

        errors = []
        if not first_name or not last_name:
            errors.append("First and last name are required.")
        if not email or "@" not in email:
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if not country:
            errors.append("Please select your country.")
        if not phone:
            errors.append("Phone number is required.")

        if User.query.filter_by(email=email).first():
            errors.append("An account with this email already exists.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("register.html")

        referral_code = generate_referral_code()
        while User.query.filter_by(referral_code=referral_code).first():
            referral_code = generate_referral_code()

        user = User(
            full_name=full_name,
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=generate_password_hash(password),
            country=country,
            country_code=country_code,
            phone=phone,
            currency=currency,
            currency_symbol=currency_symbol,
            referral_code=referral_code,
            verified=False,
        )
        user.verification_code = generate_code()
        user.verification_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=current_app.config["VERIFICATION_MINUTES"]
        )

        db.session.add(user)
        db.session.commit()

        body = (
            f"Hello {user.full_name},\n\n"
            f"Your DAILYWINS verification code is: {user.verification_code}\n\n"
            f"This code expires in {current_app.config['VERIFICATION_MINUTES']} minutes.\n\n"
            "If you did not create this account, you can ignore this email."
        )
        sent = send_email(user.email, "DAILYWINS email verification code", body)

        session["pending_email"] = user.email
        if not sent and current_app.config["ALLOW_DEV_VERIFICATION_CODE"]:
            flash(
                f"Development mode: your verification code is {user.verification_code}.",
                "info",
            )
        elif not sent:
            flash(
                "Your account was created, but the verification email could not be sent. "
                "Configure SMTP and use resend code.",
                "error",
            )
        else:
            flash("Account created. Check your email for the verification code.", "success")
        return redirect(url_for("auth.verify_email"))

    return render_template("register.html")

@auth_bp.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    email = request.values.get("email", "").strip().lower() or session.get("pending_email", "")

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("We could not find that account.", "error")
            return render_template("verify-email.html", email=email)

        now = datetime.now(timezone.utc)
        expires = user.verification_expires_at
        if user.verified:
            flash("Your email is already verified. Please sign in.", "success")
            return redirect(url_for("auth.login"))
        if user.verification_code != code:
            flash("Invalid verification code.", "error")
        elif not expires or expires < now:
            flash("That verification code has expired. Request a new one.", "error")
        else:
            user.verified = True
            user.verification_code = None
            user.verification_expires_at = None
            db.session.commit()
            session.pop("pending_email", None)
            flash("Email verified successfully. You can now sign in.", "success")
            return redirect(url_for("auth.login"))

    return render_template("verify-email.html", email=email)

@auth_bp.post("/resend-code")
def resend_code():
    email = request.form.get("email", "").strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        flash("We could not find that account.", "error")
        return redirect(url_for("auth.verify_email", email=email))
    if user.verified:
        flash("This email is already verified.", "success")
        return redirect(url_for("auth.login"))

    user.verification_code = generate_code()
    user.verification_expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=current_app.config["VERIFICATION_MINUTES"]
    )
    db.session.commit()

    body = (
        f"Hello {user.full_name},\n\n"
        f"Your new DAILYWINS verification code is: {user.verification_code}\n\n"
        f"It expires in {current_app.config['VERIFICATION_MINUTES']} minutes."
    )
    sent = send_email(user.email, "DAILYWINS new verification code", body)
    session["pending_email"] = user.email

    if not sent and current_app.config["ALLOW_DEV_VERIFICATION_CODE"]:
        flash(f"Development mode: your new code is {user.verification_code}.", "info")
    elif not sent:
        flash("The verification email could not be sent. Check your SMTP configuration.", "error")
    else:
        flash("A new verification code has been sent.", "success")
    return redirect(url_for("auth.verify_email", email=email))

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        if not user.verified:
            session["pending_email"] = user.email
            flash("Please verify your email before signing in.", "error")
            return redirect(url_for("auth.verify_email", email=user.email))

        session.clear()
        session["user_id"] = user.id
        session["user_role"] = user.role
        return redirect(url_for("dashboard.dashboard"))

    return render_template("login.html")

@auth_bp.get("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()

        # Do not reveal whether an email is registered.
        if user:
            user.reset_token = secrets.token_urlsafe(32)
            user.reset_expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=current_app.config["RESET_MINUTES"]
            )
            db.session.commit()
            reset_url = url_for("auth.reset_password", token=user.reset_token, _external=True)
            body = (
                f"Hello {user.full_name},\n\n"
                f"Use this link to reset your DAILYWINS password:\n{reset_url}\n\n"
                f"The link expires in {current_app.config['RESET_MINUTES']} minutes."
            )
            send_email(user.email, "DAILYWINS password reset", body)

        flash("If an account exists for that email, reset instructions have been sent.", "success")
        return redirect(url_for("auth.login"))

    return render_template("forgot-password.html")

@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_expires_at or user.reset_expires_at < datetime.now(timezone.utc):
        flash("That password reset link is invalid or expired.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            user.password_hash = generate_password_hash(password)
            user.reset_token = None
            user.reset_expires_at = None
            db.session.commit()
            flash("Password updated. Please sign in.", "success")
            return redirect(url_for("auth.login"))

    return render_template("reset-password.html", token=token)
