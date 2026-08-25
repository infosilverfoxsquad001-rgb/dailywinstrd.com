
from functools import wraps
from flask import flash, redirect, session, url_for

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "error")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            flash("Admin sign-in required.", "error")
            return redirect(url_for("admin.index"))
        return view(*args, **kwargs)
    return wrapped
