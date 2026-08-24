import os
import random
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, url_for, jsonify
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.utils import secure_filename

from models import AuditLog, Transaction, User, SupportMessage, db


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "kyc")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "change-this-secret-key-in-production"
)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(BASE_DIR, "dailywins.db"),
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB uploads

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def allowed_file(filename):
    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            flash("Unauthorized access.", "danger")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped


def parse_positive_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def get_currency_symbol(currency):
    symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
    }
    return symbols.get((currency or "USD").upper(), "$")


def create_default_admin():
    if not User.query.filter_by(is_admin=True).first():
        admin = User(
            first_name="Admin",
            last_name="System",
            email=os.environ.get("ADMIN_EMAIL", "admin@dailywins.com").lower(),
            country="US",
            currency="USD",
            currency_symbol="$",
            is_verified=True,
            is_admin=True,
        )
        admin.set_password(
            os.environ.get("ADMIN_PASSWORD", "AdminSecure2026!")
        )
        db.session.add(admin)
        db.session.commit()


with app.app_context():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    db.create_all()
    create_default_admin()


# ---------------------------------------------------------------------------
# Authentication / registration
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        country = request.form.get("country", "").strip()
        currency = "USD"
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        if not first_name or not last_name or not email or not password:
            flash("Please complete all required fields.", "danger")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("Email address already registered.", "danger")
            return render_template("register.html")

        code = f"{random.randint(0, 99999):05d}"
        referral_code = f"DW{random.randint(100000, 999999)}"
        while User.query.filter_by(referral_code=referral_code).first():
            referral_code = f"DW{random.randint(100000, 999999)}"
        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            country=country,
            currency=currency,
            currency_symbol=get_currency_symbol(currency),
            verification_code=code,
            code_expiry=utc_now() + timedelta(minutes=10),
            is_verified=False,
            referral_code=referral_code,
            referred_by=request.form.get("ref", "").strip() or None,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        # Development fallback. Replace with a real mail provider in production.
        app.logger.info("Verification code for %s: %s", email, code)

        login_user(user)
        flash(
            "Registration successful. Enter the 5-digit verification code.",
            "success",
        )
        return redirect(url_for("verify_email"))

    return render_template("register.html")


@app.route("/verify-email", methods=["GET", "POST"])
@login_required
def verify_email():
    if current_user.is_verified:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        entered_code = "".join(
            request.form.get(f"code_{i}", "").strip()
            for i in range(1, 6)
        )

        if len(entered_code) != 5 or not entered_code.isdigit():
            flash("Enter the complete 5-digit verification code.", "danger")
            return render_template("verify_email.html")

        if (
            not current_user.verification_code
            or not current_user.code_expiry
            or utc_now() > current_user.code_expiry
        ):
            flash("Verification code has expired. Request a new code.", "danger")
            return render_template("verify_email.html")

        if entered_code != current_user.verification_code:
            flash("Invalid verification code.", "danger")
            return render_template("verify_email.html")

        current_user.is_verified = True
        current_user.verification_code = None
        current_user.code_expiry = None
        db.session.commit()

        flash("Email verified successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("verify_email.html")


@app.route("/resend-code", methods=["POST", "GET"])
@login_required
def resend_code():
    if current_user.is_verified:
        return redirect(url_for("dashboard"))

    code = f"{random.randint(0, 99999):05d}"
    current_user.verification_code = code
    current_user.code_expiry = utc_now() + timedelta(minutes=10)
    db.session.commit()

    app.logger.info(
        "Resent verification code for %s: %s",
        current_user.email,
        code,
    )
    flash("A new verification code has been generated.", "info")
    return redirect(url_for("verify_email"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if hasattr(user, "is_active_status") and not user.is_active_status:
                flash("Your account is currently suspended.", "danger")
                return render_template("login.html")

            login_user(user)

            if not user.is_verified:
                return redirect(url_for("verify_email"))

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# User dashboard / transactions
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    if not current_user.is_verified:
        return redirect(url_for("verify_email"))

    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))

    return render_template("dashboard(1).html", user=current_user)


@app.route("/deposit", methods=["POST"])
@login_required
def create_deposit():
    if not current_user.is_verified:
        return redirect(url_for("verify_email"))

    amount = parse_positive_amount(request.form.get("amount"))
    method = request.form.get("method", "").strip()

    if amount is None:
        flash("Invalid deposit amount.", "danger")
        return redirect(url_for("dashboard"))

    if not method:
        flash("Please select a deposit method.", "danger")
        return redirect(url_for("dashboard"))

    transaction = Transaction(
        user_id=current_user.id,
        type="Deposit",
        amount=amount,
        method=method,
        status="Pending",
    )
    db.session.add(transaction)
    db.session.commit()

    flash(
        "Deposit request submitted successfully and is awaiting admin review.",
        "success",
    )
    return redirect(url_for("dashboard"))


@app.route("/withdraw", methods=["POST"])
@login_required
def create_withdrawal():
    if not current_user.is_verified:
        return redirect(url_for("verify_email"))

    amount = parse_positive_amount(request.form.get("amount"))
    method = request.form.get("method", "").strip()
    destination_details = request.form.get("destination_details", "").strip()

    if amount is None:
        flash("Invalid withdrawal amount.", "danger")
        return redirect(url_for("dashboard"))

    if not method or not destination_details:
        flash("Please provide the withdrawal method and destination.", "danger")
        return redirect(url_for("dashboard"))

    if amount > float(current_user.available_balance or 0):
        flash("Insufficient available balance.", "danger")
        return redirect(url_for("dashboard"))

    # Hold the amount while the withdrawal is pending.
    current_user.available_balance -= amount

    transaction = Transaction(
        user_id=current_user.id,
        type="Withdrawal",
        amount=amount,
        method=method,
        destination_details=destination_details,
        status="Pending",
    )
    db.session.add(transaction)
    db.session.commit()

    flash(
        "Withdrawal request submitted successfully and is under review.",
        "success",
    )
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# User settings / KYC / payout details
# ---------------------------------------------------------------------------

@app.route("/settings/update", methods=["POST"])
@login_required
def update_settings():
    phone = request.form.get("phone", "").strip()
    if phone:
        current_user.phone = phone
        db.session.commit()
        flash("Settings updated successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/settings/update-profile", methods=["POST"])
@login_required
def update_profile():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    currency = request.form.get("currency", "").strip().upper()

    if first_name:
        current_user.first_name = first_name
    if last_name:
        current_user.last_name = last_name
    if phone:
        current_user.phone = phone

    if email and email != current_user.email:
        existing = User.query.filter(
            User.email == email, User.id != current_user.id
        ).first()
        if existing:
            flash("That email address is already in use.", "danger")
            return redirect(url_for("dashboard"))
        current_user.email = email

    current_user.currency = "USD"
    current_user.currency_symbol = "$"

    db.session.commit()
    flash("Profile details updated successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/settings/submit-kyc", methods=["POST"])
@login_required
def submit_kyc():
    document_type = request.form.get("document_type", "").strip()
    file = request.files.get("kyc_file")

    if not file or not file.filename:
        flash("Please select a KYC document.", "danger")
        return redirect(url_for("dashboard"))

    if not allowed_file(file.filename):
        flash("Invalid file format. Use JPG, JPEG, PNG, or PDF.", "danger")
        return redirect(url_for("dashboard"))

    filename = secure_filename(
        f"user_{current_user.id}_{file.filename}"
    )
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    current_user.kyc_document_type = document_type
    current_user.kyc_document_path = filepath
    current_user.kyc_status = "Pending"
    db.session.commit()

    flash(
        "KYC document submitted successfully. Awaiting admin review.",
        "success",
    )
    return redirect(url_for("dashboard"))


@app.route("/settings/update-finance", methods=["POST"])
@login_required
def update_finance():
    current_user.crypto_payout_address = request.form.get(
        "crypto_payout_address", ""
    ).strip()
    current_user.bank_account_name = request.form.get(
        "bank_account_name", ""
    ).strip()
    current_user.bank_account_number = request.form.get(
        "bank_account_number", ""
    ).strip()
    current_user.bank_name = request.form.get("bank_name", "").strip()
    current_user.bank_swift_iban = request.form.get(
        "bank_swift_iban", ""
    ).strip()

    db.session.commit()
    flash("Financial payout details saved successfully.", "success")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Admin authentication, password reset and support
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email, is_admin=True).first()
        if user and user.check_password(password) and user.is_active_status:
            login_user(user)
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin email or password.", "danger")
    return render_template("admin-login.html")

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email, is_admin=False).first()
        if user:
            token = os.urandom(32).hex()
            import hashlib
            user.reset_token_hash = hashlib.sha256(token.encode()).hexdigest()
            user.reset_token_expiry = utc_now() + timedelta(minutes=30)
            db.session.commit()
            # Development-safe fallback: log the reset URL instead of exposing it in the UI.
            app.logger.info("Password reset URL for %s: %s", email, url_for("reset_password", token=token, _external=True))
        flash("If that email is registered, password-reset instructions have been generated.", "info")
        return redirect(url_for("forgot_password"))
    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user = User.query.filter_by(reset_token_hash=token_hash).first()
    if not user or not user.reset_token_expiry or user.reset_token_expiry < utc_now():
        flash("This password reset link is invalid or expired.", "danger")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 8 or password != confirm:
            flash("Passwords must match and contain at least 8 characters.", "danger")
            return render_template("reset_password.html")
        user.set_password(password)
        user.reset_token_hash = None
        user.reset_token_expiry = None
        db.session.commit()
        flash("Password updated successfully. Please sign in.", "success")
        return redirect(url_for("login"))
    return render_template("reset_password.html")

@app.route("/support/message", methods=["POST"])
def support_message():
    data = request.get_json(silent=True) or request.form
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    message = str(data.get("message", "")).strip()
    if not name or not email or not message:
        return jsonify(message="Name, email and message are required."), 400
    db.session.add(SupportMessage(name=name, email=email, message=message))
    db.session.commit()
    return jsonify(message="Your support message has been sent."), 201

@app.route("/support/recent")
def support_recent():
    rows = SupportMessage.query.order_by(SupportMessage.created_at.desc()).limit(20).all()
    return jsonify([{ "id":x.id, "name":x.name, "email":x.email, "message":x.message, "reply":x.reply, "status":x.status } for x in rows])

@app.route("/support/reply/<int:message_id>", methods=["POST"])
@admin_required
def support_reply(message_id):
    msg = db.session.get(SupportMessage, message_id)
    if not msg:
        flash("Support message not found.", "danger")
        return redirect(url_for("admin_dashboard"))
    msg.reply = request.form.get("reply", "").strip()
    msg.status = "Replied"
    db.session.commit()
    flash("Support reply saved.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/market/crypto")
def crypto_market():
    # Browser-side market fetch is used on the original homepage; this endpoint is a stable fallback.
    return jsonify({"currency":"USD", "assets":["BTC","ETH","USDT","BNB","SOL","XRP"]})

@app.route("/withdrawals/recent")
def recent_withdrawals():
    rows = Transaction.query.filter_by(type="Withdrawal", status="Approved").order_by(Transaction.timestamp.desc()).limit(20).all()
    result=[]
    for tx in rows:
        first=(tx.user.first_name or "User") if tx.user else "User"
        masked=(first[:1] + "••••")
        result.append({"name":masked,"amount":float(tx.amount)})
    return jsonify(result)


@app.route("/admin/payment-settings", methods=["POST"])
@admin_required
def update_payment_settings():
    flash("Payment settings update received. Store provider addresses in environment variables for production.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/impersonate/<int:user_id>")
@admin_required
def admin_impersonate(user_id):
    flash("Impersonation is disabled in this build for account-safety reasons.", "warning")
    return redirect(url_for("admin_user_details", user_id=user_id))

# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    users = User.query.filter_by(is_admin=False).all()
    pending_transactions = Transaction.query.filter_by(
        status="Pending"
    ).all()
    pending_kyc = User.query.filter_by(kyc_status="Pending").all()
    audit_logs = AuditLog.query.order_by(
        AuditLog.timestamp.desc()
    ).limit(20).all()

    return render_template(
        "admin-dashboard.html",
        admin=current_user,
        users=users,
        pending_transactions=pending_transactions,
        pending_kyc=pending_kyc,
        audit_logs=audit_logs,
    )


@app.route("/admin/dashboard-home")
@admin_required
def admin_dashboard_home():
    total_users = User.query.filter_by(is_admin=False).count()
    pending_deposits = Transaction.query.filter_by(
        type="Deposit", status="Pending"
    ).count()
    pending_withdrawals = Transaction.query.filter_by(
        type="Withdrawal", status="Pending"
    ).count()
    pending_kyc = User.query.filter_by(kyc_status="Pending").count()
    recent_audit = AuditLog.query.order_by(
        AuditLog.timestamp.desc()
    ).limit(10).all()

    return render_template(
        "dashboard(2).html",
        total_users=total_users,
        pending_deposits=pending_deposits,
        pending_withdrawals=pending_withdrawals,
        pending_kyc=pending_kyc,
        recent_audit=recent_audit,
    )


@app.route("/admin/users")
@admin_required
def admin_users_list():
    users = User.query.filter_by(is_admin=False).all()
    return render_template("admin-users.html", users=users)


@app.route("/admin/user/<int:user_id>")
@admin_required
def admin_user_details(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin_users_list"))

    transactions = Transaction.query.filter_by(
        user_id=user.id
    ).order_by(Transaction.timestamp.desc()).all()

    return render_template(
        "user-details(1).html",
        user=user,
        transactions=transactions,
    )


@app.route("/admin/transaction/<int:tx_id>/<action>", methods=["POST", "GET"])
@admin_required
def review_transaction(tx_id, action):
    tx = db.session.get(Transaction, tx_id)

    if not tx:
        flash("Transaction not found.", "danger")
        return redirect(url_for("admin_dashboard"))

    user = db.session.get(User, tx.user_id)

    if not user:
        flash("Transaction owner no longer exists.", "danger")
        return redirect(url_for("admin_dashboard"))

    if tx.status != "Pending":
        flash("Transaction has already been processed.", "warning")
        return redirect(url_for("admin_dashboard"))

    if action == "approve":
        tx.status = "Approved"

        if tx.type == "Deposit":
            user.available_balance = float(user.available_balance or 0) + tx.amount
            user.total_deposits = float(user.total_deposits or 0) + tx.amount

        elif tx.type == "Withdrawal":
            user.total_withdrawals = (
                float(user.total_withdrawals or 0) + tx.amount
            )

        log = AuditLog(
            admin_id=current_user.id,
            action=f"Approved {tx.type} of {tx.amount} for {user.email}",
        )
        db.session.add(log)
        flash(f"Approved {tx.type} for {user.email}.", "success")

    elif action == "reject":
        tx.status = "Rejected"

        if tx.type == "Withdrawal":
            user.available_balance = (
                float(user.available_balance or 0) + tx.amount
            )

        log = AuditLog(
            admin_id=current_user.id,
            action=f"Rejected {tx.type} of {tx.amount} for {user.email}",
        )
        db.session.add(log)
        flash(f"Rejected {tx.type} for {user.email}.", "info")

    else:
        flash("Invalid transaction action.", "danger")
        return redirect(url_for("admin_dashboard"))

    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/kyc/<int:user_id>/<action>", methods=["POST", "GET"])
@admin_required
def review_kyc(user_id, action):
    target_user = db.session.get(User, user_id)

    if not target_user:
        flash("User not found.", "danger")
        return redirect(url_for("admin_dashboard"))

    if action == "approve":
        target_user.kyc_status = "Verified"
        log = AuditLog(
            admin_id=current_user.id,
            action=f"Approved KYC for {target_user.email}",
        )
        flash(f"KYC verified for {target_user.email}.", "success")

    elif action == "reject":
        target_user.kyc_status = "Rejected"
        log = AuditLog(
            admin_id=current_user.id,
            action=f"Rejected KYC for {target_user.email}",
        )
        flash(f"KYC rejected for {target_user.email}.", "warning")

    else:
        flash("Invalid KYC action.", "danger")
        return redirect(url_for("admin_dashboard"))

    db.session.add(log)
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/user/<int:user_id>/adjust-balance", methods=["POST"])
@admin_required
def admin_adjust_balance(user_id):
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash("User not found.", "danger")
        return redirect(url_for("admin_users_list"))

    adjustment = parse_positive_amount(request.form.get("amount"))
    direction = request.form.get("direction", "credit")

    if adjustment is None:
        flash("Invalid adjustment amount.", "danger")
        return redirect(url_for("admin_user_details", user_id=user_id))

    if direction == "debit":
        adjustment = -adjustment

    target_user.available_balance = max(
        0.0, float(target_user.available_balance or 0) + adjustment
    )

    log = AuditLog(
        admin_id=current_user.id,
        action=(
            f"Adjusted balance for {target_user.email} by "
            f"{adjustment}. New balance: {target_user.available_balance}"
        ),
    )
    db.session.add(log)
    db.session.commit()

    flash("User balance updated successfully.", "success")
    return redirect(url_for("admin_user_details", user_id=user_id))


@app.route("/admin/email-all", methods=["POST"])
@admin_required
def admin_email_all():
    subject = request.form.get("email_subject", "").strip()
    body = request.form.get("email_body", "").strip()

    if not subject or not body:
        flash("Subject and message are required.", "danger")
        return redirect(url_for("admin_dashboard_home"))

    recipient_count = User.query.filter_by(is_admin=False).count()

    # Email provider integration should be added here.
    log = AuditLog(
        admin_id=current_user.id,
        action=(
            f"Prepared broadcast announcement for {recipient_count} "
            f"investors: '{subject}'"
        ),
    )
    db.session.add(log)
    db.session.commit()

    flash(
        f"Announcement recorded for {recipient_count} registered users.",
        "success",
    )
    return redirect(url_for("admin_dashboard_home"))


@app.route("/admin/user/<int:user_id>/action", methods=["POST"])
@admin_required
def admin_user_action(user_id):
    target_user = db.session.get(User, user_id)

    if not target_user:
        flash("User not found.", "danger")
        return redirect(url_for("admin_users_list"))

    action_type = request.form.get("action_type")

    if action_type == "credit_debit":
        amount = parse_positive_amount(request.form.get("amount"))
        op_type = request.form.get("op_type", "Credit")
        source = request.form.get("source", "Profit")

        if amount is None or op_type not in {"Credit", "Debit"}:
            flash("Invalid balance operation.", "danger")
            return redirect(url_for("admin_user_details", user_id=user_id))

        change = amount if op_type == "Credit" else -amount

        if source == "Profit":
            target_user.profit_balance = max(
                0.0, float(target_user.profit_balance or 0) + change
            )
        elif source == "Deposit":
            target_user.total_deposits = max(
                0.0, float(target_user.total_deposits or 0) + change
            )
        elif source == "Referral":
            target_user.referral_bonus = max(
                0.0, float(target_user.referral_bonus or 0) + change
            )
        else:
            flash("Invalid balance source.", "danger")
            return redirect(url_for("admin_user_details", user_id=user_id))

        target_user.available_balance = max(
            0.0, float(target_user.available_balance or 0) + change
        )

        log = AuditLog(
            admin_id=current_user.id,
            action=(
                f"{op_type}ed {amount} ({source}) for "
                f"user {target_user.email}"
            ),
        )
        db.session.add(log)
        db.session.commit()

        flash(
            f"{op_type} operation completed for {target_user.email}.",
            "success",
        )

    elif action_type == "clear_account":
        target_user.available_balance = 0.0
        target_user.profit_balance = 0.0
        target_user.total_deposits = 0.0
        target_user.total_withdrawals = 0.0
        target_user.referral_bonus = 0.0

        log = AuditLog(
            admin_id=current_user.id,
            action=f"Cleared balances for {target_user.email}",
        )
        db.session.add(log)
        db.session.commit()
        flash("Account balances cleared.", "warning")

    elif action_type == "suspend_account":
        current_status = getattr(target_user, "is_active_status", True)
        target_user.is_active_status = not current_status

        label = (
            "Suspended"
            if not target_user.is_active_status
            else "Activated"
        )
        log = AuditLog(
            admin_id=current_user.id,
            action=f"{label} account for {target_user.email}",
        )
        db.session.add(log)
        db.session.commit()
        flash(f"User account {label.lower()}.", "info")

    elif action_type == "verify_kyc":
        target_user.kyc_status = "Verified"
        log = AuditLog(
            admin_id=current_user.id,
            action=f"Manually verified KYC for {target_user.email}",
        )
        db.session.add(log)
        db.session.commit()
        flash("KYC successfully verified.", "success")

    elif action_type == "delete_account":
        confirm_name = request.form.get(
            "confirm_first_name", ""
        ).strip().lower()

        if confirm_name != target_user.first_name.strip().lower():
            flash("First name confirmation did not match.", "danger")
            return redirect(
                url_for("admin_user_details", user_id=user_id)
            )

        email_ref = target_user.email

        log = AuditLog(
            admin_id=current_user.id,
            action=f"Deleted user account {email_ref}",
        )
        db.session.add(log)

        # Delete transactions first when no cascade is configured.
        Transaction.query.filter_by(user_id=target_user.id).delete(
            synchronize_session=False
        )
        db.session.delete(target_user)
        db.session.commit()

        flash(f"User {email_ref} has been deleted.", "success")
        return redirect(url_for("admin_users_list"))

    else:
        flash("Unknown admin action.", "danger")

    return redirect(url_for("admin_user_details", user_id=user_id))


if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "1") == "1",
    )
