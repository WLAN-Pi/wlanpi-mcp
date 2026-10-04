"""Tests for get_profiler_reports (reads the profiler's files until core does)."""

import hashlib
import io
import json
import os
import shlex
import time
import zipfile
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from wlanpi_mcp import download_links
from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreAPIError
from wlanpi_mcp.config import Settings
from wlanpi_mcp.tools import profiler_reports

MAC = "ea-3c-46-d4-e3-b2"
OTHER = "aa-bb-cc-dd-ee-ff"

# Trimmed from a real wlanpi-profiler 2.1.6 schema v2 profile.
PROFILE = {
    "mac": MAC,
    "is_laa": True,
    "manuf": "Apple",
    "chipset": "",
    "capture_ssid": "deepdive-probe",
    "capture_bssid": "9c:04:b6:97:22:68",
    "capture_manuf": "QuectelWirel",
    "capture_band": "5",
    "capture_channel": 149,
    "features": {"dot11k": 1, "dot11ax": 1, "dot11be": 1, "dot11be_mle": -1},
    "pcapng": '"AAASAC5IAAAADHEWQAHJAAAAAAA8AJwEtpciaOo="',
    "schema_version": 2,
    "profiler_version": "2.1.6",
    "capture_source": "profiler",
}


def _write_client(root, mac, bands=("5GHz",), mtime=None):
    client_dir = root / "clients" / mac
    client_dir.mkdir(parents=True, exist_ok=True)
    for band in bands:
        # Not Path.with_suffix: the profiler's "2.4GHz" band has a dot in it.
        stem = f"{mac}_{band}"
        profile = {**PROFILE, "mac": mac}
        (client_dir / f"{stem}.json").write_text(json.dumps(profile))
        (client_dir / f"{stem}.txt").write_text(f"report for {mac} {band}\n")
        (client_dir / f"{stem}.pcap").write_bytes(b"\xd4\xc3\xb2\xa1" + mac.encode())
    if mtime is not None:
        for f in client_dir.iterdir():
            os.utime(f, (mtime, mtime))
    return client_dir


@pytest.fixture
def data(monkeypatch, tmp_path):
    """Point the tool at a profiler data dir laid out as the profiler writes it."""
    root = tmp_path / "profiler"
    (root / "clients").mkdir(parents=True)
    (root / "reports").mkdir()
    settings = Settings(PROFILER_DATA_DIR=str(root), _env_file=None)
    monkeypatch.setattr(profiler_reports, "get_settings", lambda: settings)
    return root


@pytest.fixture(autouse=True)
def _clean_tickets():
    profiler_reports._TICKETS.clear()
    yield
    profiler_reports._TICKETS.clear()


def _tool(core_get=None):
    client = MagicMock()
    client.get = core_get or AsyncMock(return_value={"hostname": "wlanpi-test"})
    mcp = FastMCP("test")
    profiler_reports.register(mcp, client)
    return mcp._tool_manager._tools["get_profiler_reports"], client


def _core_error(status, detail):
    request = httpx.Request("GET", "https://localhost:31415/api/v1/system/device/info")
    return CoreAPIError(
        httpx.Response(status, json={"detail": detail}, request=request)
    )


# ── json ─────────────────────────────────────────────────────────────────────


async def test_json_returns_parsed_profiles_without_the_frame(data):
    _write_client(data, MAC, bands=("5GHz", "2.4GHz"))
    tool, client = _tool()

    result = await tool.run({})

    client.get.assert_awaited_once_with("/api/v1/system/device/info")
    assert result["total_clients"] == 1
    assert result["truncated"] is False
    [entry] = result["clients"]
    assert entry["mac"] == MAC
    by_band = {p["band"]: p for p in entry["profiles"]}
    assert set(by_band) == {"5GHz", "2.4GHz"}
    profile = by_band["5GHz"]
    assert profile["manuf"] == "Apple"
    assert profile["features"]["dot11be"] == 1
    assert profile["file"] == f"clients/{MAC}/{MAC}_5GHz.json"
    assert "pcapng" not in profile


async def test_json_can_keep_the_frame(data):
    _write_client(data, MAC)
    tool, _ = _tool()

    result = await tool.run({"include_frame": True})

    assert result["clients"][0]["profiles"][0]["pcapng"] == PROFILE["pcapng"]


async def test_json_lists_session_reports_by_name_only(data):
    _write_client(data, MAC)
    (data / "reports" / "profiler-2026-10-04.csv").write_text("Client_Mac\n")
    (data / "reports" / "notes.txt").write_text("not a session report")
    tool, _ = _tool()

    result = await tool.run({})

    [report] = result["session_reports"]
    assert report["path"] == "reports/profiler-2026-10-04.csv"
    assert report["size_bytes"] == len("Client_Mac\n")
    assert not any(k.startswith("_") for k in report)


async def test_clients_are_newest_first_and_capped(data):
    _write_client(data, OTHER, mtime=1_000)
    _write_client(data, MAC, mtime=2_000)
    tool, _ = _tool()

    result = await tool.run({"max_clients": 1})

    assert [c["mac"] for c in result["clients"]] == [MAC]
    assert result["total_clients"] == 2
    assert result["returned_clients"] == 1
    assert result["truncated"] is True

    everything = await tool.run({"max_clients": 0})
    assert [c["mac"] for c in everything["clients"]] == [MAC, OTHER]
    assert everything["truncated"] is False


@pytest.mark.parametrize(
    "mac", ["EA:3C:46:D4:E3:B2", "ea-3c-46-d4-e3-b2", "ea3c.46d4.e3b2", "EA3C46D4E3B2"]
)
async def test_mac_filter_accepts_common_formats(data, mac):
    _write_client(data, MAC)
    _write_client(data, OTHER)
    tool, _ = _tool()

    result = await tool.run({"mac": mac})

    assert [c["mac"] for c in result["clients"]] == [MAC]
    assert result["total_clients"] == 1


@pytest.mark.parametrize("mac", ["../../etc", "ea:3c:46", "zz:zz:zz:zz:zz:zz"])
async def test_a_non_mac_filter_is_refused_before_core_is_called(data, mac):
    tool, client = _tool()

    result = await tool.run({"mac": mac})

    assert result["error"].startswith("not a MAC address")
    client.get.assert_not_awaited()


async def test_unknown_mac_says_so(data):
    _write_client(data, MAC)
    tool, _ = _tool()

    result = await tool.run({"mac": OTHER})

    assert result["clients"] == []
    assert result["note"] == f"no profile for {OTHER}"


async def test_empty_or_missing_data_dir_is_not_an_error(data, monkeypatch, tmp_path):
    tool, _ = _tool()
    result = await tool.run({})
    assert result["clients"] == [] and result["total_clients"] == 0
    assert "no client profiles" in result["note"]

    gone = Settings(PROFILER_DATA_DIR=str(tmp_path / "absent"), _env_file=None)
    monkeypatch.setattr(profiler_reports, "get_settings", lambda: gone)
    result = await tool.run({})
    assert result["clients"] == [] and result["session_reports"] == []


async def test_a_corrupt_profile_is_reported_not_fatal(data):
    client_dir = _write_client(data, MAC)
    (client_dir / f"{MAC}_6GHz.json").write_text("{truncated")
    tool, _ = _tool()

    result = await tool.run({})

    profiles = result["clients"][0]["profiles"]
    bad = [p for p in profiles if "error" in p]
    assert [p["file"] for p in bad] == [f"clients/{MAC}/{MAC}_6GHz.json"]
    assert any(p.get("manuf") == "Apple" for p in profiles)


async def test_symlinks_and_stray_entries_are_ignored(data, tmp_path):
    # Only regular files in clients/<mac>/ are read: a symlink must not let
    # the tool read outside the profiler's data directory.
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"mac": "stolen"}))
    client_dir = _write_client(data, MAC)
    (client_dir / f"{MAC}_6GHz.json").symlink_to(secret)
    (data / "clients" / OTHER).symlink_to(tmp_path, target_is_directory=True)
    (data / "clients" / "not-a-mac").mkdir()
    (data / "clients" / "not-a-mac" / "x.json").write_text("{}")
    (data / "clients" / "stray.json").write_text("{}")
    tool, _ = _tool()

    result = await tool.run({"max_clients": 0})

    assert [c["mac"] for c in result["clients"]] == [MAC]
    files = [p["file"] for p in result["clients"][0]["profiles"]]
    assert files == [f"clients/{MAC}/{MAC}_5GHz.json"]
    assert "stolen" not in json.dumps(result)


# ── token check ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("output", ["json", "links", "zip"])
async def test_nothing_is_returned_when_core_refuses_the_token(data, output):
    # The files are read locally, so the core round trip is the only thing
    # that validates the caller's JWT.
    _write_client(data, MAC)
    tool, _ = _tool(AsyncMock(side_effect=_core_error(401, "Invalid token")))

    result = await tool.run({"output": output})

    assert set(result) == {"error"}
    assert "refused this token" in result["error"]
    assert "Invalid token" in result["error"]
    assert profiler_reports._TICKETS == {}


async def test_an_unreachable_core_is_not_blamed_on_the_token(data):
    _write_client(data, MAC)
    tool, _ = _tool(AsyncMock(side_effect=httpx.ConnectError("refused")))

    result = await tool.run({})

    assert result["error"].startswith("could not reach wlanpi-core")


# ── links / zip ──────────────────────────────────────────────────────────────


async def test_links_mint_one_ticket_per_file_with_snapshots(data):
    _write_client(data, MAC)
    csv = data / "reports" / "profiler-2026-10-04.csv"
    csv.write_text("Client_Mac,OUI_Manuf\n")
    tool, _ = _tool()

    result = await tool.run({"output": "links"})

    paths = {f["path"] for f in result["files"]}
    assert paths == {
        f"clients/{MAC}/{MAC}_5GHz.json",
        f"clients/{MAC}/{MAC}_5GHz.txt",
        f"clients/{MAC}/{MAC}_5GHz.pcap",
        "reports/profiler-2026-10-04.csv",
    }
    assert result["single_use"] is True
    assert result["expires_in_s"] == download_links.DOWNLOAD_TTL_S
    assert result["clients"] == [
        {"mac": MAC, "modified": result["clients"][0]["modified"]}
    ]
    # stdio: no request to build a URL from.
    assert all(
        f["download_path"].startswith("/profiler-report/") for f in result["files"]
    )
    assert "curl" not in result and "stdio" in result["note"]
    assert len(profiler_reports._TICKETS) == 4

    by_name = {d.filename: d for d in profiler_reports._TICKETS.values()}
    assert by_name["profiler-2026-10-04.csv"].data == b"Client_Mac,OUI_Manuf\n"
    assert by_name["profiler-2026-10-04.csv"].media_type.startswith("text/csv")
    assert by_name[f"{MAC}_5GHz.json"].media_type == "application/json"

    # The ticket holds a snapshot: later changes on disk do not leak through.
    csv.write_text("changed")
    assert by_name["profiler-2026-10-04.csv"].data == b"Client_Mac,OUI_Manuf\n"


async def test_links_can_leave_out_the_session_csvs(data):
    _write_client(data, MAC)
    (data / "reports" / "profiler-2026-10-04.csv").write_text("x\n")
    tool, _ = _tool()

    result = await tool.run({"output": "links", "include_session_csv": False})

    assert not any(f["path"].startswith("reports/") for f in result["files"])


async def test_links_build_urls_and_one_curl_from_the_request(data, monkeypatch):
    _write_client(data, MAC)
    monkeypatch.setattr(
        download_links, "request_base_url", lambda: "https://wlanpi-9be.local:8767"
    )
    tool, _ = _tool()

    result = await tool.run({"output": "links", "include_session_csv": False})

    urls = [f["download_url"] for f in result["files"]]
    assert all(
        u.startswith("https://wlanpi-9be.local:8767/profiler-report/") for u in urls
    )
    argv = shlex.split(result["curl"])
    assert argv[:3] == ["curl", "-gsSfk", "--create-dirs"]
    pairs = list(zip(argv[3::3], argv[4::3], argv[5::3], strict=True))
    assert {(o, p) for o, p, _ in pairs} == {
        ("-o", f"profiler/{f['path']}") for f in result["files"]
    }
    assert {u for *_, u in pairs} == set(urls)
    assert "note" not in result


async def test_zip_bundles_every_file_behind_one_ticket(data, monkeypatch):
    _write_client(data, MAC, mtime=1_700_000_000)
    _write_client(data, OTHER)
    (data / "reports" / "profiler-2026-10-04.csv").write_text("x\n")
    monkeypatch.setattr(download_links, "request_base_url", lambda: "https://h:8767")
    tool, _ = _tool()

    result = await tool.run({"output": "zip"})

    [download] = profiler_reports._TICKETS.values()
    assert download.media_type == "application/zip"
    assert download.filename == result["filename"]
    assert result["filename"].startswith("profiler-reports-")
    assert result["size_bytes"] == len(download.data)
    assert result["sha256"] == hashlib.sha256(download.data).hexdigest()
    names = zipfile.ZipFile(io.BytesIO(download.data)).namelist()
    assert sorted(names) == sorted(f"profiler/{p}" for p in result["files"])
    assert len(names) == 7  # 3 files x 2 clients + 1 csv
    assert f"profiler/clients/{MAC}/{MAC}_5GHz.pcap" in names
    # Entries carry the file's own mtime (when it was profiled), not "now".
    info = zipfile.ZipFile(io.BytesIO(download.data)).getinfo(
        f"profiler/clients/{MAC}/{MAC}_5GHz.json"
    )
    assert info.date_time == time.localtime(1_700_000_000)[:6]
    assert info.compress_type == zipfile.ZIP_DEFLATED
    assert result["download_url"].startswith("https://h:8767/profiler-report/")
    assert shlex.split(result["curl"])[-2:] == [
        result["filename"],
        result["download_url"],
    ]


async def test_zip_respects_the_mac_filter(data):
    _write_client(data, MAC)
    _write_client(data, OTHER)
    tool, _ = _tool()

    result = await tool.run(
        {"output": "zip", "mac": OTHER, "include_session_csv": False}
    )

    assert all(p.startswith(f"clients/{OTHER}/") for p in result["files"])
    assert len(result["files"]) == 3


async def test_an_oversized_request_is_refused_before_reading(data, monkeypatch):
    _write_client(data, MAC)
    monkeypatch.setattr(profiler_reports, "MAX_DOWNLOAD_BYTES", 10)
    tool, _ = _tool()

    result = await tool.run({"output": "zip"})

    assert "byte limit" in result["error"]
    assert profiler_reports._TICKETS == {}


async def test_invalid_output_is_rejected_by_the_schema(data):
    from mcp.server.fastmcp.exceptions import ToolError

    tool, client = _tool()

    with pytest.raises(ToolError):
        await tool.run({"output": "tarball"})
    client.get.assert_not_awaited()


async def test_expired_tickets_are_pruned_on_the_next_mint(data):
    _write_client(data, MAC)
    profiler_reports._TICKETS["stale"] = profiler_reports._Download(
        b"x", "x", "text/plain", expires=1.0
    )
    tool, _ = _tool()

    await tool.run({"output": "zip"})

    assert "stale" not in profiler_reports._TICKETS
    assert len(profiler_reports._TICKETS) == 1
