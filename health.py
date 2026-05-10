"""Minimal HTTP endpoints for load balancers and platform health checks (e.g. Railway)."""

from __future__ import annotations

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    """Liveness: process is up and routing works; does not touch Redis or the database."""
    return jsonify(status="ok"), 200
