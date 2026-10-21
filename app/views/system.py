"""Read-only system status page."""

from app.common import render_system


def render() -> None:
    render_system()
