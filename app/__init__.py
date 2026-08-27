from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError

from app.extensions import csrf, db, migrate, oauth
from config import Config, validate_config


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    validate_config(app.config)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    oauth.init_app(app)

    from app import models  # noqa: F401
    from app.auth import auth_bp, register_auth
    from app.routes.api import api_bp
    from app.routes.dashboard import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp)

    register_error_handlers(app)
    register_auth(app)
    from app.checks.scheduler import register_scheduler_startup

    register_scheduler_startup(app)
    return app


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify({"data": None, "error": "Not found"}), 404
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        if request.path.startswith("/api/"):
            return jsonify({"data": None, "error": "Internal server error"}), 500
        return render_template("500.html"), 500

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        if request.path.startswith("/api/"):
            return (
                jsonify({"data": None, "error": {"csrf": error.description}}),
                400,
            )
        return render_template("400.html", message=error.description), 400
