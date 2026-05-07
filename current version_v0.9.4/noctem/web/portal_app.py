"""Standalone Cor Unum portal app runtime."""
from ..config import Config
from .app import create_app


def create_portal_app():
    return create_app(portal_mode=True, cor_unum_private_only=False)


def run_portal():
    app = create_portal_app()
    app.run(host=Config.portal_host(), port=Config.portal_port(), debug=False)
