
import os
from decimal import Decimal

from flask import Flask, flash, redirect, render_template, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from database import db
from models import InvestmentPlan
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.investments import investments_bp
from routes.transactions import transactions_bp
from routes.admin import admin_bp
from routes.api import api_bp

def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(Config)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(investments_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @app.context_processor
    def inject_globals():
        return {
            "current_user_id": session.get("user_id"),
            "admin_authenticated": session.get("admin_authenticated", False),
        }

    @app.get("/")
    def index():
        plans = InvestmentPlan.query.filter_by(active=True).order_by(InvestmentPlan.minimum_amount).all()
        return render_template("index.html", plans=plans)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/health")
    def api_health():
        return {"status": "ok"}

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    with app.app_context():
        os.makedirs(app.instance_path, exist_ok=True)
        os.makedirs(os.path.join(os.path.dirname(__file__), "database"), exist_ok=True)
        db.create_all()
        seed_plans()

    return app

def seed_plans():
    defaults = [
        ("Starter", Decimal("20.00"), 7, Decimal("100.00"), Decimal("999.00")),
        ("Silver", Decimal("35.00"), 14, Decimal("1000.00"), Decimal("4999.00")),
        ("Gold", Decimal("60.00"), 30, Decimal("5000.00"), Decimal("19999.00")),
        ("VIP Elite", Decimal("100.00"), 45, Decimal("20000.00"), None),
    ]
    for name, roi, days, minimum, maximum in defaults:
        if not InvestmentPlan.query.filter_by(name=name).first():
            db.session.add(
                InvestmentPlan(
                    name=name,
                    roi_percent=roi,
                    duration_days=days,
                    minimum_amount=minimum,
                    maximum_amount=maximum,
                    active=True,
                )
            )
    db.session.commit()

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
