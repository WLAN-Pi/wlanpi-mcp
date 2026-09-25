"""The UFW first-boot unit and setup script (WLAN-Pi/wlanpi-mcp#45).

ufw reads its rule files before taking its lock, so a `ufw allow` racing
wlanpi-core's first-boot oneshot can exit 0 and still lose its rule. The unit
must be ordered after core's, and the script must only write its applied
marker once the rule is really there.

The script runs for real against a temp root (WLANPI_MCP_UFW_ROOT) with stub
`ufw`, `id` and `ischroot` commands first on PATH.
"""

import configparser
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
UNIT = REPO / "debian" / "wlanpi-mcp-ufw-first-boot.service"
UFW_SRC = REPO / "install" / "etc" / "wlanpi-mcp" / "ufw"
SCRIPT = UFW_SRC / "wlanpi-mcp-ufw-rules-setup.sh"

# Records `ufw allow <x>` in $UFW_STATE and prints it back for `ufw show
# added`, like ufw's user rules. UFW_LOSE_ALLOW=1 exits 0 without recording,
# which is what losing the race with a concurrent ufw call looks like.
FAKE_UFW = """#!/bin/bash
case "$1" in
    allow)
        [ "${UFW_LOSE_ALLOW:-0}" = 1 ] || echo "ufw allow $2" >> "$UFW_STATE"
        ;;
    show)
        echo "Added user rules (see 'ufw status' for running firewall):"
        cat "$UFW_STATE" 2>/dev/null
        ;;
esac
echo "$*" >> "$UFW_CALLS"
exit 0
"""


def _write_exe(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def device(tmp_path):
    root = tmp_path / "root"
    rules_dir = root / "etc" / "wlanpi-mcp" / "ufw"
    rules_dir.mkdir(parents=True)
    for name in ("current-rules-version", "wlanpi-mcp.rules"):
        (rules_dir / name).write_text((UFW_SRC / name).read_text())

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(bin_dir / "ufw", FAKE_UFW)
    _write_exe(bin_dir / "id", "#!/bin/sh\necho 0\n")
    _write_exe(bin_dir / "ischroot", "#!/bin/sh\nexit 1\n")

    class Device:
        marker = root / "etc" / "wlanpi-mcp" / "installed-rules-version"
        app_file = root / "etc" / "ufw" / "applications.d" / "wlanpi-mcp"
        state = tmp_path / "ufw-state"
        calls = tmp_path / "ufw-calls"
        version = (UFW_SRC / "current-rules-version").read_text()

        def run(self, **env):
            return subprocess.run(
                ["bash", str(SCRIPT)],
                env={
                    **os.environ,
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "WLANPI_MCP_UFW_ROOT": str(root),
                    "UFW_STATE": str(self.state),
                    "UFW_CALLS": str(self.calls),
                    **env,
                },
                capture_output=True,
                text=True,
                timeout=30,
            )

        def allow_calls(self):
            if not self.calls.exists():
                return []
            return [
                c for c in self.calls.read_text().splitlines() if c.startswith("allow")
            ]

    return Device()


def test_unit_ordered_after_core_ufw_first_boot():
    unit = configparser.ConfigParser(interpolation=None, strict=False)
    unit.optionxform = str
    unit.read(UNIT)
    after = unit["Unit"]["After"].split()
    assert "wlanpi-core-ufw-first-boot.service" in after
    # Still ordered after ufw itself and the image's own first-boot setup.
    assert {"ufw.service", "wlanpi-first-boot.service"} <= set(after)


def test_fresh_apply_installs_profile_and_writes_marker(device):
    result = device.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert device.allow_calls() == ["allow wlanpi-mcp"]
    assert device.app_file.exists()
    assert device.marker.read_text() == device.version


def test_lost_rule_fails_without_writing_marker(device):
    result = device.run(UFW_LOSE_ALLOW="1")

    assert result.returncode != 0
    assert "not marking applied" in result.stdout + result.stderr
    assert not device.marker.exists()


def test_lost_rule_is_retried_on_next_run(device):
    assert device.run(UFW_LOSE_ALLOW="1").returncode != 0

    result = device.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert device.marker.read_text() == device.version
    assert "ufw allow wlanpi-mcp" in device.state.read_text()


def test_up_to_date_with_rule_present_skips_ufw(device):
    assert device.run().returncode == 0
    device.calls.unlink()

    result = device.run()

    assert result.returncode == 0
    assert "up to date" in result.stdout
    assert device.allow_calls() == []


def test_marker_without_rule_reapplies(device):
    # A device that lost the race before this fix: marker written, rule gone.
    device.marker.parent.mkdir(parents=True, exist_ok=True)
    device.marker.write_text(device.version)

    result = device.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "missing, re-applying" in result.stdout
    assert device.allow_calls() == ["allow wlanpi-mcp"]
    assert "ufw allow wlanpi-mcp" in device.state.read_text()
