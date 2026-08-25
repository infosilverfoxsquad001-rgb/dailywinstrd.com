
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from auth_utils import admin_required
from models.user import User
from models.investment import Investment, InvestmentPlan
from models.transaction import Transaction

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        from flask import current_app
        if username == current_app.config["ADMIN_USERNAME"] and password == current_app.config["ADMIN_PASSWORD"] and password:
            session["admin_authenticated"] = True
            return redirect(url_for("admin.dashboard"))
        flash("Invalid admin credentials.", "error")
    return render_template("admin/login.html")

@admin_bp.get("/dashboard")
@admin_required
def dashboard():
    return render_template(
        "admin/dashboard.html",
        user_count=User.query.count(),
        pending_deposits=Transaction.query.filter_by(transaction_type="deposit", status="pending").count(),
        pending_withdrawals=Transaction.query.filter_by(transaction_type="withdrawal", status="pending").count(),
        pending_investments=Investment.query.filter_by(status="pending").count(),
    )

@admin_bp.get("/users")
@admin_required
def users():
    return render_template("admin/users.html", users=User.query.order_by(User.created_at.desc()).all())

@admin_bp.get("/user-details/<int:user_id>")
@admin_required
def user_details(user_id):
    user = User.query.get_or_404(user_id)
    return render_template("admin/user-details.html", user=user)

@admin_bp.get("/deposits")
@admin_required
def deposits():
    rows = Transaction.query.filter_by(transaction_type="deposit").order_by(Transaction.created_at.desc()).all()
    return render_template("admin/deposits.html", transactions=rows)

@admin_bp.get("/withdrawals")
@admin_required
def withdrawals():
    rows = Transaction.query.filter_by(transaction_type="withdrawal").order_by(Transaction.created_at.desc()).all()
    return render_template("admin/withdrawals.html", transactions=rows)

@admin_bp.get("/investments")
@admin_required
def investments():
    rows = Investment.query.order_by(Investment.created_at.desc()).all()
    return render_template("admin/investments.html", investments=rows)

@admin_bp.get("/transactions")
@admin_required
def transactions():
    rows = Transaction.query.order_by(Transaction.created_at.desc()).all()
    return render_template("admin/transactions.html", transactions=rows)

@admin_bp.get("/plans")
@admin_required
def plans():
    return render_template("admin/plans.html", plans=InvestmentPlan.query.order_by(InvestmentPlan.minimum_amount).all())

@admin_bp.get("/kyc")
@admin_required
def kyc():
    return render_template("admin/kyc.html")

@admin_bp.get("/settings")
@admin_required
def settings():
    return render_template("admin/settings.html")

@admin_bp.get("/logout")
def logout():
    session.pop("admin_authenticated", None)
    flash("Admin signed out.", "success")
    return redirect(url_for("admin.index"))
