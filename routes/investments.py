
from flask import Blueprint, flash, redirect, render_template, session, url_for

from auth_utils import login_required
from models.investment import InvestmentPlan
from models.user import User

investments_bp = Blueprint("investments", __name__)

@investments_bp.get("/investments")
@login_required
def investments():
    user = User.query.get(session["user_id"])
    plans = InvestmentPlan.query.filter_by(active=True).order_by(InvestmentPlan.minimum_amount).all()
    return render_template("investments.html", user=user, plans=plans)

@investments_bp.post("/investments/request")
@login_required
def request_investment():
    flash(
        "Investment creation is not enabled in this starter build. "
        "Connect a reviewed payment/investment workflow before accepting funds.",
        "info",
    )
    return redirect(url_for("investments.investments"))
