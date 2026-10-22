from __future__ import annotations

from pathlib import Path
import re
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / ".streamlit" / "config.toml"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "start_streamlit_lan.ps1"
RUNBOOK_PATH = PROJECT_ROOT / "docs" / "dashboard.md"


def test_default_streamlit_config_stays_local_and_protected() -> None:
    with CONFIG_PATH.open("rb") as file_handle:
        config = tomllib.load(file_handle)

    server = config["server"]
    assert server["address"] == "127.0.0.1"
    assert server["port"] == 8501
    assert server["enableCORS"] is True
    assert server["enableXsrfProtection"] is True


def test_lan_script_has_safe_single_process_preflight() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'Join-Path $RepoRoot ".venv\\Scripts\\python.exe"' in script
    assert 'Join-Path $RepoRoot "app\\main.py"' in script
    assert 'Join-Path $RepoRoot ".git"' in script
    assert "Get-NetTCPConnection -State Listen -LocalPort $Port" in script
    assert '$LanAddress = "0.0.0.0"' in script
    assert "$Port = 8501" in script
    assert len(re.findall(r"& \$Python -m streamlit run", script)) == 1
    assert "Start-Process" not in script
    assert "-Verb RunAs" not in script


def test_lan_script_does_not_mutate_firewall_data_or_models() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8").casefold()

    forbidden = (
        "new-netfirewallrule",
        "set-netconnectionprofile",
        "duckdb",
        "sqlite",
        "init_duckdb",
        "ingest_landing",
        "refresh",
        "model runner",
    )
    assert all(term not in script for term in forbidden)
    assert "password" not in script
    assert "secret" not in script


def test_runbook_scopes_firewall_and_manual_lan_verification() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    required = (
        "http://<HOST_IPV4>:8501",
        "New-NetFirewallRule",
        "-Protocol TCP",
        "-LocalPort 8501",
        "-Profile Private",
        "-RemoteAddress LocalSubnet",
        "Disable-NetFirewallRule",
        "MANUAL_VERIFY",
        "AP isolation",
        "DHCP",
        "HTTPS",
        "reverse proxy",
    )
    assert all(term in runbook for term in required)
