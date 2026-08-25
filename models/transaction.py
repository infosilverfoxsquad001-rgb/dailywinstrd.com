
from datetime import datetime, timezone
from database import db

class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    transaction_type = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    status = db.Column(db.String(30), default="pending", nullable=False)
    reference = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user = db.relationship("User", back_populates="transactions")
