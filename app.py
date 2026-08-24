import hashlib
import json
import time
import urllib.parse
import urllib.request
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for, jsonify, session
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from sqlalchemy import inspect, text
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from models import AuditLog, PaymentSetting, SupportMessage, Transaction, User, db

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "static" / "uploads" / "kyc"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
REFERRAL_BONUS_RATE = float(os.environ.get("REFERRAL_BONUS_RATE", "0.05"))
MARKET_CACHE_SECONDS = int(os.environ.get("MARKET_CACHE_SECONDS", "30"))
_market_cache = {"at": 0.0, "data": []}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{BASE_DIR / 'dailywins.db'}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "info"


@app.template_filter("money")
def money(value):
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_currency_symbol(currency):
    return {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "NGN": "₦",
        "AED": "AED ",
        "CAD": "CA$",
        "AUD": "A$",
    }.get((currency or "USD").upper(), "$")


def allowed_file(filename):
    return bool(filename and "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS)


def parse_positive_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def generate_referral_code():
    while True:
        code = "DW-" + secrets.token_hex(4).upper()
        if not User.query.filter_by(referral_code=code).first():
            return code


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def send_email(to_email, subject, body):
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("MAIL_FROM", username or "no-reply@dailywins.com")

    if not host:
        app.logger.info("Email fallback | to=%s | subject=%s | body=%s", to_email, subject, body)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to_email
    message.set_content(body)

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
    return True


def send_verification_email(user, code):
    return send_email(
        user.email,
        "DAILYWINS email verification code",
        f"Hello {user.first_name},\n\nYour DAILYWINS verification code is: {code}\n\nThis code expires in 10 minutes.",
    )


def send_password_reset_email(user, token):
    reset_url = url_for("reset_password", token=token, _external=True)
    return send_email(
        user.email,
        "Reset your DAILYWINS password",
        f"Hello {user.first_name},\n\nUse this link to reset your password:\n{reset_url}\n\nThe link expires in 30 minutes. If you did not request this, ignore this email.",
    )


def get_support_token():
    token = session.get("support_chat_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["support_chat_token"] = token
    return token


def support_display_name(user):
    if not user:
        return "Guest user"
    first = (user.first_name or "User").strip()
    return f"{first[:1].upper()}••••"


def fetch_crypto_prices():
    """Fetch public market prices from CoinGecko with a short server-side cache."""
    now = time.time()
    if _market_cache["data"] and now - _market_cache["at"] < MARKET_CACHE_SECONDS:
        return _market_cache["data"]

    ids = "bitcoin,ethereum,tether,binancecoin,solana,xrp"
    query = urllib.parse.urlencode({
        "ids": ids,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    })
    url = f"https://api.coingecko.com/api/v3/simple/price?{query}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DAILYWINS/1.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        symbols = [
            ("BTC", "bitcoin"), ("ETH", "ethereum"), ("USDT", "tether"),
            ("BNB", "binancecoin"), ("SOL", "solana"), ("XRP", "xrp"),
        ]
        data = []
        for symbol, key in symbols:
            item = payload.get(key, {})
            price = item.get("usd")
            change = item.get("usd_24h_change")
            if price is not None:
                data.append({"symbol": symbol, "price": price, "change": change})
        if data:
            _market_cache["at"] = now
            _market_cache["data"] = data
            return data
    except Exception:
        app.logger.exception("Crypto market request failed")
    return _market_cache["data"]


def migrate_existing_schema():
    """Add fields introduced by this version without destroying an existing SQLite database."""
    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("users")}
    additions = {
        "investment_balance": "FLOAT NOT NULL DEFAULT 0",
        "reset_token_hash": "VARCHAR(255)",
        "reset_token_expiry": "DATETIME",
        "referral_code": "VARCHAR(20)",
        "referred_by_id": "INTEGER",
        "referral_rewarded": "BOOLEAN NOT NULL DEFAULT 0",
    }
    for name, definition in additions.items():
        if name not in existing:
            db.session.execute(text(f"ALTER TABLE users ADD COLUMN {name} {definition}"))
    db.session.commit()

    # Populate referral codes for existing users.
    for user in User.query.filter(User.referral_code.is_(None)).all():
        user.referral_code = generate_referral_code()
    db.session.commit()
    try:
        db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_referral_code ON users (referral_code)"))
        db.session.commit()
    except Exception:
        db.session.rollback()


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
            referral_code=generate_referral_code(),
        )
        admin.set_password(os.environ.get("ADMIN_PASSWORD", "AdminSecure2026!"))
        db.session.add(admin)
        db.session.commit()


def get_or_create_payment_settings():
    settings = PaymentSetting.query.first()
    if not settings:
        settings = PaymentSetting(
            usdt_address=os.environ.get("USDT_TRC20_ADDRESS", ""),
            btc_address=os.environ.get("BTC_ADDRESS", ""),
            eth_address=os.environ.get("ETH_ADDRESS", ""),
            bank_info=os.environ.get("BANK_INFO", ""),
        )
        db.session.add(settings)
        db.session.commit()
    return settings


with app.app_context():
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    db.create_all()
    migrate_existing_schema()
    create_default_admin()
    get_or_create_payment_settings()


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            flash("Unauthorized access.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# Public pages and authentication
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    referral_prefill = request.args.get("ref", "").strip().upper()
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        country = request.form.get("country", "").strip()
        currency = request.form.get("currency", "USD").strip().upper()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        referral_code = request.form.get("referral_code", "").strip().upper()

        if not all([first_name, last_name, email, country, password, confirm_password]):
            flash("Please complete all required fields.", "danger")
            return render_template("register.html", referral_code=referral_code or referral_prefill)
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html", referral_code=referral_code or referral_prefill)
        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
            return render_template("register.html", referral_code=referral_code or referral_prefill)
        if User.query.filter_by(email=email).first():
            flash("That email address is already registered.", "danger")
            return render_template("register.html", referral_code=referral_code or referral_prefill)

        referrer = None
        if referral_code:
            referrer = User.query.filter_by(referral_code=referral_code).first()
            if not referrer:
                flash("The referral code is not valid.", "danger")
                return render_template("register.html", referral_code=referral_code)

        code = f"{secrets.randbelow(100000):05d}"
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
            referral_code=generate_referral_code(),
            referred_by_id=referrer.id if referrer else None,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        send_verification_email(user, code)
        login_user(user)
        flash("Account created. Enter the 5-digit verification code sent to your email.", "success")
        return redirect(url_for("verify_email"))

    return render_template("register.html", referral_code=referral_prefill)


@app.route("/verify-email", methods=["GET", "POST"])
@login_required
def verify_email():
    if current_user.is_verified:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        entered = "".join(request.form.get(f"code_{i}", "").strip() for i in range(1, 6))
        if len(entered) != 5 or not entered.isdigit():
            flash("Enter the complete 5-digit verification code.", "danger")
            return render_template("verify_email.html")
        if not current_user.verification_code or not current_user.code_expiry or utc_now() > current_user.code_expiry:
            flash("That code has expired. Request a new code.", "danger")
            return render_template("verify_email.html")
        if not secrets.compare_digest(entered, current_user.verification_code):
            flash("Invalid verification code.", "danger")
            return render_template("verify_email.html")

        current_user.is_verified = True
        current_user.verification_code = None
        current_user.code_expiry = None
        db.session.commit()
        flash("Email verified successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("verify_email.html")


@app.route("/resend-code")
@login_required
def resend_code():
    if current_user.is_verified:
        return redirect(url_for("dashboard"))
    code = f"{secrets.randbelow(100000):05d}"
    current_user.verification_code = code
    current_user.code_expiry = utc_now() + timedelta(minutes=10)
    db.session.commit()
    send_verification_email(current_user, code)
    flash("A new verification code has been sent.", "info")
    return redirect(url_for("verify_email"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember_me") == "on"
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if not user.is_active_status:
                flash("Your account is currently suspended.", "danger")
                return render_template("login.html")
            login_user(user, remember=remember)
            if user.is_admin:
                return redirect(url_for("admin_dashboard_home"))
            if not user.is_verified:
                return redirect(url_for("verify_email"))
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            raw_token = secrets.token_urlsafe(32)
            user.reset_token_hash = hash_token(raw_token)
            user.reset_token_expiry = utc_now() + timedelta(minutes=30)
            db.session.commit()
            send_password_reset_email(user, raw_token)
        # Deliberately identical response for known/unknown addresses.
        flash("If an account exists for that email, a password reset link has been sent.", "info")
        return redirect(url_for("forgot_password"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    token_hash = hash_token(token)
    user = User.query.filter_by(reset_token_hash=token_hash).first()
    if not user or not user.reset_token_expiry or utc_now() > user.reset_token_expiry:
        flash("That password reset link is invalid or expired.", "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
            return render_template("reset_password.html")
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("reset_password.html")
        user.set_password(password)
        user.reset_token_hash = None
        user.reset_token_expiry = None
        db.session.commit()
        flash("Your password has been changed. You can now sign in.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# User dashboard
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard_home"))
    if not current_user.is_verified:
        return redirect(url_for("verify_email"))

    referral_count = User.query.filter_by(referred_by_id=current_user.id).count()
    settings = get_or_create_payment_settings()
    deposit_wallets = {
        "USDT (TRC20)": settings.usdt_address or "Not configured",
        "Bitcoin (BTC)": settings.btc_address or "Not configured",
        "Ethereum (ETH)": settings.eth_address or "Not configured",
        "Local Bank Wire": settings.bank_info or "Contact support for bank instructions.",
    }
    return render_template("dashboard.html", user=current_user, referral_count=referral_count, deposit_wallets=deposit_wallets, referral_rate_percent=REFERRAL_BONUS_RATE * 100)


@app.route("/deposit", methods=["POST"])
@login_required
def create_deposit():
    if not current_user.is_verified:
        return redirect(url_for("verify_email"))
    amount = parse_positive_amount(request.form.get("amount"))
    method = request.form.get("method", "").strip()
    if amount is None or not method:
        flash("Enter a valid deposit amount and payment method.", "danger")
        return redirect(url_for("dashboard"))
    db.session.add(Transaction(user_id=current_user.id, type="Deposit", amount=amount, method=method, status="Pending"))
    db.session.commit()
    flash("Deposit request submitted for admin review.", "success")
    return redirect(url_for("dashboard"))


@app.route("/withdraw", methods=["POST"])
@login_required
def create_withdrawal():
    if not current_user.is_verified:
        return redirect(url_for("verify_email"))
    amount = parse_positive_amount(request.form.get("amount"))
    method = request.form.get("method", "").strip()
    destination = request.form.get("destination_details", "").strip()
    if amount is None or not method or not destination:
        flash("Complete all withdrawal fields with a valid amount.", "danger")
        return redirect(url_for("dashboard"))
    if amount > float(current_user.available_balance or 0):
        flash("Insufficient available balance.", "danger")
        return redirect(url_for("dashboard"))
    current_user.available_balance -= amount
    db.session.add(Transaction(user_id=current_user.id, type="Withdrawal", amount=amount, method=method, destination_details=destination, status="Pending"))
    db.session.commit()
    flash("Withdrawal request submitted for admin review.", "success")
    return redirect(url_for("dashboard"))


@app.route("/settings/update-profile", methods=["POST"])
@login_required
def update_profile():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    currency = request.form.get("currency", "USD").strip().upper()

    if email != current_user.email and User.query.filter(User.email == email, User.id != current_user.id).first():
        flash("That email address is already in use.", "danger")
        return redirect(url_for("dashboard"))
    current_user.first_name = first_name or current_user.first_name
    current_user.last_name = last_name or current_user.last_name
    current_user.email = email or current_user.email
    current_user.phone = phone
    if currency:
        current_user.currency = currency
        current_user.currency_symbol = get_currency_symbol(currency)
    db.session.commit()
    flash("Profile updated successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/settings/submit-kyc", methods=["POST"])
@login_required
def submit_kyc():
    document_type = request.form.get("document_type", "").strip()
    uploaded = request.files.get("kyc_file")
    if not document_type or not uploaded or not uploaded.filename:
        flash("Select a document type and file.", "danger")
        return redirect(url_for("dashboard"))
    if not allowed_file(uploaded.filename):
        flash("Invalid file format. Use JPG, JPEG, PNG or PDF.", "danger")
        return redirect(url_for("dashboard"))

    filename = secure_filename(f"user_{current_user.id}_{secrets.token_hex(4)}_{uploaded.filename}")
    uploaded.save(UPLOAD_FOLDER / filename)
    current_user.kyc_document_type = document_type
    current_user.kyc_document_path = f"uploads/kyc/{filename}"
    current_user.kyc_status = "Pending"
    db.session.commit()
    flash("KYC document submitted for review.", "success")
    return redirect(url_for("dashboard"))


@app.route("/settings/update-finance", methods=["POST"])
@login_required
def update_finance():
    current_user.crypto_payout_address = request.form.get("crypto_payout_address", "").strip()
    current_user.bank_account_name = request.form.get("bank_account_name", "").strip()
    current_user.bank_account_number = request.form.get("bank_account_number", "").strip()
    current_user.bank_name = request.form.get("bank_name", "").strip()
    current_user.bank_swift_iban = request.form.get("bank_swift_iban", "").strip()
    db.session.commit()
    flash("Payout details saved.", "success")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Live support chat + public market/activity widgets
# ---------------------------------------------------------------------------
@app.route("/support/chat/messages", methods=["GET"])
def support_chat_messages():
    token = get_support_token()
    messages = (SupportMessage.query
                .filter_by(conversation_token=token)
                .order_by(SupportMessage.timestamp.asc())
                .limit(100).all())
    # A user viewing their conversation has now seen all support replies.
    unread_support = [m for m in messages if m.sender == "support" and not m.is_read]
    for message in unread_support:
        message.is_read = True
    if unread_support:
        db.session.commit()
    return jsonify({"messages": [{
        "sender": m.sender,
        "message": m.message,
        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
    } for m in messages]})


@app.route("/support/chat/send", methods=["POST"])
def support_chat_send():
    payload = request.get_json(silent=True) or request.form
    message = str(payload.get("message", "")).strip()[:2000]
    if not message:
        return jsonify({"ok": False, "error": "Message is required."}), 400
    token = get_support_token()
    user_id = current_user.id if current_user.is_authenticated and not current_user.is_admin else None
    db.session.add(SupportMessage(
        conversation_token=token,
        user_id=user_id,
        sender="user",
        message=message,
    ))
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/crypto-prices")
def crypto_prices_api():
    return jsonify({"updated": utc_now().isoformat(), "prices": fetch_crypto_prices()})


@app.route("/api/recent-withdrawals")
def recent_withdrawals_api():
    rows = (Transaction.query
            .filter_by(type="Withdrawal", status="Approved")
            .order_by(Transaction.timestamp.desc())
            .limit(12).all())
    items = []
    for tx in rows:
        user = tx.user
        country = (user.country or "").strip()
        country_code = country[:2].upper() if country else ""
        items.append({
            "name": support_display_name(user),
            "country": country_code,
            "amount": round(float(tx.amount or 0), 2),
            "currency": user.currency or "USD",
            "symbol": user.currency_symbol or "$",
            "timestamp": tx.timestamp.isoformat() if tx.timestamp else None,
        })
    return jsonify({"withdrawals": items})


# ---------------------------------------------------------------------------
# Admin authentication and administration
# ---------------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("admin_dashboard_home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        admin = User.query.filter_by(email=email, is_admin=True).first()
        if admin and admin.check_password(password) and admin.is_active_status:
            login_user(admin)
            return redirect(url_for("admin_dashboard_home"))
        flash("Invalid administrator credentials.", "danger")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    logout_user()
    flash("Administrator signed out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return redirect(url_for("admin_dashboard_home"))


@app.route("/admin/dashboard-home")
@admin_required
def admin_dashboard_home():
    total_users_count = User.query.filter_by(is_admin=False).count()
    pending_deposits = Transaction.query.filter_by(type="Deposit", status="Pending").order_by(Transaction.timestamp.desc()).all()
    pending_withdrawals = Transaction.query.filter_by(type="Withdrawal", status="Pending").order_by(Transaction.timestamp.desc()).all()
    pending_kyc = User.query.filter_by(kyc_status="Pending").order_by(User.created_at.desc()).all()
    users = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).all()
    audit_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(30).all()
    support_messages = SupportMessage.query.order_by(SupportMessage.timestamp.desc()).limit(60).all()
    payment_settings = get_or_create_payment_settings()
    return render_template(
        "admin/dashboard.html",
        total_users_count=total_users_count,
        pending_deposits=pending_deposits,
        pending_withdrawals=pending_withdrawals,
        pending_kyc=pending_kyc,
        users=users,
        audit_logs=audit_logs,
        support_messages=support_messages,
        payment_settings=payment_settings,
        admin=current_user,
    )

@app.route("/admin/users")
@admin_required
def admin_users_list():
    users = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)


@app.route("/admin/user/<int:user_id>")
@admin_required
def admin_user_details(user_id):
    user = db.session.get(User, user_id)
    if not user or user.is_admin:
        flash("User not found.", "danger")
        return redirect(url_for("admin_users_list"))
    transactions = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.timestamp.desc()).all()
    referral_count = User.query.filter_by(referred_by_id=user.id).count()
    return render_template("admin/user-details.html", user=user, transactions=transactions, referral_count=referral_count)


@app.route("/admin/transaction/<int:tx_id>/<action>", methods=["GET", "POST"])
@admin_required
def review_transaction(tx_id, action):
    tx = db.session.get(Transaction, tx_id)
    if not tx or tx.status != "Pending":
        flash("Transaction not found or already processed.", "danger")
        return redirect(url_for("admin_dashboard_home"))
    user = db.session.get(User, tx.user_id)
    if not user:
        flash("Transaction owner not found.", "danger")
        return redirect(url_for("admin_dashboard_home"))

    if action == "approve":
        tx.status = "Approved"
        if tx.type == "Deposit":
            user.available_balance += tx.amount
            user.total_deposits += tx.amount
            # Reward the referrer once, after the first approved deposit.
            if user.referred_by_id and not user.referral_rewarded:
                referrer = db.session.get(User, user.referred_by_id)
                if referrer and referrer.id != user.id:
                    bonus = round(tx.amount * REFERRAL_BONUS_RATE, 2)
                    referrer.referral_bonus += bonus
                    referrer.available_balance += bonus
                    db.session.add(Transaction(
                        user_id=referrer.id,
                        type="Referral Bonus",
                        amount=bonus,
                        method=f"Referral: {user.email}",
                        status="Approved",
                    ))
                    user.referral_rewarded = True
                    db.session.add(AuditLog(admin_id=current_user.id, action=f"Awarded referral bonus {bonus} to {referrer.email}"))
        elif tx.type == "Withdrawal":
            user.total_withdrawals += tx.amount
        flash(f"{tx.type} approved.", "success")
    elif action == "reject":
        tx.status = "Rejected"
        if tx.type == "Withdrawal":
            user.available_balance += tx.amount
        flash(f"{tx.type} rejected.", "info")
    else:
        flash("Invalid transaction action.", "danger")
        return redirect(url_for("admin_dashboard_home"))

    db.session.add(AuditLog(admin_id=current_user.id, action=f"{'Approved' if action == 'approve' else 'Rejected'} {tx.type} {tx.amount} for {user.email}"))
    db.session.commit()
    return redirect(url_for("admin_dashboard_home"))


@app.route("/admin/kyc/<int:user_id>/<action>", methods=["GET", "POST"])
@admin_required
def review_kyc(user_id, action):
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin_dashboard_home"))
    if action == "approve":
        user.kyc_status = "Verified"
    elif action == "reject":
        user.kyc_status = "Rejected"
    else:
        flash("Invalid KYC action.", "danger")
        return redirect(url_for("admin_dashboard_home"))
    db.session.add(AuditLog(admin_id=current_user.id, action=f"{action.title()}d KYC for {user.email}"))
    db.session.commit()
    flash(f"KYC {action}d for {user.email}.", "success")
    return redirect(url_for("admin_user_details", user_id=user.id))


@app.route("/admin/user/<int:user_id>/action", methods=["POST"])
@admin_required
def admin_user_action(user_id):
    target = db.session.get(User, user_id)
    if not target or target.is_admin:
        flash("User not found.", "danger")
        return redirect(url_for("admin_users_list"))
    action_type = request.form.get("action_type")

    if action_type == "credit_debit":
        amount = parse_positive_amount(request.form.get("amount"))
        op = request.form.get("op_type", "Credit")
        source = request.form.get("source", "Profit")
        if amount is None or op not in {"Credit", "Debit"} or source not in {"Profit", "Deposit", "Referral"}:
            flash("Invalid balance operation.", "danger")
            return redirect(url_for("admin_user_details", user_id=user_id))
        change = amount if op == "Credit" else -amount
        if source == "Profit":
            target.profit_balance = max(0, target.profit_balance + change)
        elif source == "Deposit":
            target.total_deposits = max(0, target.total_deposits + change)
        else:
            target.referral_bonus = max(0, target.referral_bonus + change)
        target.available_balance = max(0, target.available_balance + change)
        db.session.add(AuditLog(admin_id=current_user.id, action=f"{op}ed {amount} ({source}) for {target.email}"))
        db.session.commit()
        flash("Balance updated.", "success")

    elif action_type == "clear_account":
        target.available_balance = 0
        target.investment_balance = 0
        target.profit_balance = 0
        target.total_deposits = 0
        target.total_withdrawals = 0
        target.referral_bonus = 0
        db.session.add(AuditLog(admin_id=current_user.id, action=f"Cleared balances for {target.email}"))
        db.session.commit()
        flash("Account balances cleared.", "warning")

    elif action_type == "suspend_account":
        target.is_active_status = not target.is_active_status
        label = "activated" if target.is_active_status else "suspended"
        db.session.add(AuditLog(admin_id=current_user.id, action=f"{label.title()} account for {target.email}"))
        db.session.commit()
        flash(f"User account {label}.", "info")

    elif action_type == "verify_kyc":
        target.kyc_status = "Verified"
        db.session.add(AuditLog(admin_id=current_user.id, action=f"Manually verified KYC for {target.email}"))
        db.session.commit()
        flash("KYC verified.", "success")

    elif action_type == "delete_account":
        confirm_name = request.form.get("confirm_first_name", "").strip().lower()
        if confirm_name != target.first_name.strip().lower():
            flash("Name confirmation did not match.", "danger")
            return redirect(url_for("admin_user_details", user_id=user_id))
        email_ref = target.email
        db.session.add(AuditLog(admin_id=current_user.id, action=f"Deleted user account {email_ref}"))
        db.session.delete(target)
        db.session.commit()
        flash("User account deleted.", "success")
        return redirect(url_for("admin_users_list"))

    else:
        flash("Unknown admin action.", "danger")

    return redirect(url_for("admin_user_details", user_id=user_id))


@app.route("/admin/payment-settings", methods=["POST"])
@admin_required
def update_payment_settings():
    settings = get_or_create_payment_settings()
    settings.usdt_address = request.form.get("usdt_address", "").strip()
    settings.btc_address = request.form.get("btc_address", "").strip()
    settings.eth_address = request.form.get("eth_address", "").strip()
    settings.bank_info = request.form.get("bank_info", "").strip()
    db.session.add(AuditLog(admin_id=current_user.id, action="Updated system payment settings"))
    db.session.commit()
    flash("Payment settings updated.", "success")
    return redirect(url_for("admin_dashboard_home"))


@app.route("/admin/user/<int:user_id>/balance", methods=["POST"])
@admin_required
def admin_adjust_balance(user_id):
    target = db.session.get(User, user_id)
    try:
        amount = float(request.form.get("amount", "0"))
    except (TypeError, ValueError):
        amount = 0
    if not target or target.is_admin or amount == 0:
        flash("Invalid user or balance amount.", "danger")
        return redirect(url_for("admin_dashboard_home"))
    target.available_balance = max(0, target.available_balance + amount)
    db.session.add(AuditLog(admin_id=current_user.id, action=f"Adjusted available balance by {amount} for {target.email}"))
    db.session.commit()
    flash("Available balance updated.", "success")
    return redirect(url_for("admin_dashboard_home"))


@app.route("/admin/impersonate/<int:user_id>")
@admin_required
def admin_impersonate(user_id):
    target = db.session.get(User, user_id)
    if not target or target.is_admin:
        flash("User not found.", "danger")
        return redirect(url_for("admin_users_list"))
    from flask import session
    session["impersonating_admin_id"] = current_user.id
    session["impersonated_user_id"] = target.id
    login_user(target)
    db.session.add(AuditLog(admin_id=session["impersonating_admin_id"], action=f"Started impersonation of {target.email}"))
    db.session.commit()
    flash("You are viewing the selected user account. Exit impersonation when finished.", "warning")
    return redirect(url_for("dashboard"))


@app.route("/stop-impersonation")
def stop_impersonation():
    from flask import session
    admin_id = session.pop("impersonating_admin_id", None)
    session.pop("impersonated_user_id", None)
    if admin_id:
        admin = db.session.get(User, admin_id)
        if admin and admin.is_admin:
            login_user(admin)
            db.session.add(AuditLog(admin_id=admin.id, action="Ended user impersonation"))
            db.session.commit()
            return redirect(url_for("admin_dashboard_home"))
    logout_user()
    return redirect(url_for("admin_login"))


@app.route("/admin/support/reply", methods=["POST"])
@admin_required
def admin_support_reply():
    token = request.form.get("conversation_token", "").strip()
    message = request.form.get("message", "").strip()[:2000]
    if not token or not message:
        flash("A conversation and reply message are required.", "danger")
        return redirect(url_for("admin_dashboard_home") + "#support")
    db.session.add(SupportMessage(
        conversation_token=token,
        user_id=None,
        sender="support",
        message=message,
    ))
    db.session.add(AuditLog(admin_id=current_user.id, action=f"Replied to support conversation {token[:10]}"))
    db.session.commit()
    flash("Support reply sent.", "success")
    return redirect(url_for("admin_dashboard_home") + "#support")


@app.route("/admin/email-all", methods=["POST"])
@admin_required
def admin_email_all():
    subject = request.form.get("email_subject", "").strip()
    body = request.form.get("email_body", "").strip()
    if not subject or not body:
        flash("Subject and message are required.", "danger")
        return redirect(url_for("admin_dashboard_home"))

    recipients = [u.email for u in User.query.filter_by(is_admin=False).all()]
    sent = 0
    for email in recipients:
        try:
            if send_email(email, subject, body):
                sent += 1
        except Exception:
            app.logger.exception("Broadcast failed for %s", email)
    db.session.add(AuditLog(admin_id=current_user.id, action=f"Broadcast '{subject}' to {len(recipients)} users; sent={sent}"))
    db.session.commit()
    flash(f"Broadcast processed for {len(recipients)} users.", "success")
    return redirect(url_for("admin_dashboard_home"))


if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
