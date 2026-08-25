
from datetime import datetime, timezone
from database import db

class InvestmentPlan(db.Model):
    __tablename__ = "investment_plans"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    roi_percent = db.Column(db.Numeric(8, 2), nullable=False, default=0)
    duration_days = db.Column(db.Integer, nullable=False, default=0)
    minimum_amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    maximum_amount = db.Column(db.Numeric(18, 2), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)

    investments = db.relationship("Investment", back_populates="plan")

class Investment(db.Model):
    __tablename__ = "investments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("investment_plans.id"), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    status = db.Column(db.String(30), default="pending", nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user = db.relationship("User", back_populates="investments")
    plan = db.relationship("InvestmentPlan", back_populates="investments")
