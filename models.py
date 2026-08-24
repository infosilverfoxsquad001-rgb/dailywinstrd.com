from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(50), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    currency = db.Column(db.String(10), default="USD", nullable=False)
    currency_symbol = db.Column(db.String(10), default="$", nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)

    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active_status = db.Column(db.Boolean, default=True, nullable=False)

    verification_code = db.Column(db.String(5), nullable=True)
    code_expiry = db.Column(db.DateTime, nullable=True)

    available_balance = db.Column(db.Float, default=0.0, nullable=False)
    profit_balance = db.Column(db.Float, default=0.0, nullable=False)
    total_deposits = db.Column(db.Float, default=0.0, nullable=False)
    total_withdrawals = db.Column(db.Float, default=0.0, nullable=False)
    referral_bonus = db.Column(db.Float, default=0.0, nullable=False)
    referral_code = db.Column(db.String(32), unique=True, nullable=True, index=True)
    referred_by = db.Column(db.String(32), nullable=True, index=True)
    reset_token_hash = db.Column(db.String(128), nullable=True, index=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)

    kyc_status = db.Column(
        db.String(20), default="Not Submitted", nullable=False
    )
    kyc_document_type = db.Column(db.String(50), nullable=True)
    kyc_document_path = db.Column(db.String(255), nullable=True)

    crypto_payout_address = db.Column(db.String(255), nullable=True)
    bank_account_name = db.Column(db.String(100), nullable=True)
    bank_account_number = db.Column(db.String(50), nullable=True)
    bank_name = db.Column(db.String(100), nullable=True)
    bank_swift_iban = db.Column(db.String(100), nullable=True)

    created_at = db.Column(
        db.DateTime, server_default=db.func.now(), nullable=False
    )

    transactions = db.relationship(
        "Transaction",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    type = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(100), nullable=True)
    destination_details = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default="Pending", nullable=False)

    timestamp = db.Column(
        db.DateTime, server_default=db.func.now(), nullable=False
    )


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
    )
    action = db.Column(db.Text, nullable=False)
    timestamp = db.Column(
        db.DateTime, server_default=db.func.now(), nullable=False
    )


class SupportMessage(db.Model):
    __tablename__ = "support_messages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    reply = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="Open", nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
