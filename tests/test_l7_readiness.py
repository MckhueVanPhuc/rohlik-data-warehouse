"""Regression tests for the L7 read-only readiness gate."""

from pathlib import Path

import pytest

from src.l7_readiness import _decisions, assess


def test_approval_gate_stays_pending():
    decisions = _decisions(Path("config/l7_decisions.yaml"))
    assert set(decisions) == {"D01", "D02", "D03", "D04", "D05"}
    assert all(value == "PENDING" for value in decisions.values())


def test_missing_database_does_not_get_created(tmp_path):
    target = tmp_path / "absent.duckdb"
    report = assess(target)
    assert report["status"] == "BLOCKED"
    assert report["database_exists"] is False
    assert not target.exists()


def test_invalid_decision_status_fails_closed(tmp_path):
    config = tmp_path / "decisions.yaml"
    config.write_text(
        "decisions:\n" + "".join(
            f"  D{i:02d}:\n    status: {'READY' if i == 1 else 'PENDING'}\n"
            for i in range(1, 6)
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid decision status"):
        assess(tmp_path / "absent.duckdb", decisions_path=config)


def test_empty_database_read_only_and_not_ready(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    target = tmp_path / "empty.duckdb"
    duckdb.connect(str(target)).close()
    report = assess(target)
    assert report["landing_tables"] == 0
    assert report["mart_views"] == 0
    assert report["status"] == "BLOCKED"
    with duckdb.connect(str(target), read_only=True) as conn:
        assert conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='core'").fetchone()[0] == 0
