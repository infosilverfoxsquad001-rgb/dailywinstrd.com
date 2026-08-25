
from flask import Blueprint, render_template, session

from auth_utils import login_required
from models.user import User

dashboard_bp = Blueprint("dashboard", __name__)

def current_user():
    return User.query.get(session["user_id"])

@dashboard_bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user())

@dashboard_bp.get("/profile")
@login_required
def profile():
    return render_template("profile.html", user=current_user())

@dashboard_bp.get("/settings")
@login_required
def settings():
    return render_template("settings.html", user=current_user())

@dashboard_bp.get("/notifications")
@login_required
def notifications():
    return render_template("notifications.html", user=current_user())

@dashboard_bp.get("/referrals")
@login_required
def referrals():
    user = current_user()
    referral_url = f"{request_base_url()}/auth/register?ref={user.referral_code}"
    return render_template("referrals.html", user=user, referral_url=referral_url)

@dashboard_bp.get("/kyc")
@login_required
def kyc():
    return render_template("kyc.html", user=current_user())

@dashboard_bp.get("/support")
@login_required
def support():
    return render_template("support.html", user=current_user())

def request_base_url():
    from flask import request
    return request.url_root.rstrip("/")
