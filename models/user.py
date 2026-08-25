
from datetime import datetime, timezone
from database import db

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(80), nullable=False, default="")
    last_name = db.Column(db.String(80), nullable=False, default="")
    country = db.Column(db.String(80), nullable=True)
    country_code = db.Column(db.String(10), nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    currency = db.Column(db.String(10), nullable=False, default="USD")
    currency_symbol = db.Column(db.String(8), nullable=False, default="$")

    verified = db.Column(db.Boolean, default=False, nullable=False)
    role = db.Column(db.String(20), default="user", nullable=False)
    referral_code = db.Column(db.String(24), unique=True, nullable=False, index=True)

    balance = db.Column(db.Numeric(18, 2), default=0, nullable=False)
    profit = db.Column(db.Numeric(18, 2), default=0, nullable=False)
    referral_bonus = db.Column(db.Numeric(18, 2), default=0, nullable=False)
    total_referrals = db.Column(db.Integer, default=0, nullable=False)
    active_referrals = db.Column(db.Integer, default=0, nullable=False)

    verification_code = db.Column(db.String(6), nullable=True)
    verification_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)

    reset_token = db.Column(db.String(128), nullable=True, index=True)
    reset_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    investments = db.relationship("Investment", back_populates="user", cascade="all, delete-orphan")
    transactions = db.relationship("Transaction", back_populates="user", cascade="all, delete-orphan")

    def public_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "verified": self.verified,
            "country": self.country,
            "currency": self.currency,
            "currency_symbol": self.currency_symbol,
            "balance": float(self.balance or 0),
            "profit": float(self.profit or 0),
            "referral_bonus": float(self.referral_bonus or 0),
            "total_referrals": self.total_referrals or 0,
            "active_referrals": self.active_referrals or 0,
            "referral_code": self.referral_code,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
