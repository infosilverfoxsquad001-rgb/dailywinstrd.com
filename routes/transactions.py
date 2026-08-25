
from flask import Blueprint, render_template, session

from auth_utils import login_required
from models.transaction import Transaction
from models.user import User

transactions_bp = Blueprint("transactions", __name__)

@transactions_bp.get("/transactions")
@login_required
def transactions():
    user = User.query.get(session["user_id"])
    rows = (
        Transaction.query.filter_by(user_id=user.id)
        .order_by(Transaction.created_at.desc())
        .all()
    )
    return render_template("transactions.html", user=user, transactions=rows)

@transactions_bp.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    user = User.query.get(session["user_id"])
    if request_method_is_post():
        from flask import flash, request
        amount = request.form.get("amount", "").strip()
        flash(
            "Deposit requests are not enabled in this starter build. "
            "No payment was processed or charged.",
            "info",
        )
        return render_template("deposit.html", user=user)
    return render_template("deposit.html", user=user)

@transactions_bp.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    user = User.query.get(session["user_id"])
    if request_method_is_post():
        from flask import flash
        flash(
            "Withdrawal processing is not enabled in this starter build.",
            "info",
        )
    return render_template("withdraw.html", user=user)

def request_method_is_post():
    from flask import request
    return request.method == "POST"
