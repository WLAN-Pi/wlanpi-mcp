"""Tests for get_profiler_reports (the profiler's results through wlanpi-core)."""

import hashlib
import io
import json
import os
import shlex
import time
import zipfile
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from urllib.parse import unquote

import httpx
import pytest

from wlanpi_mcp import download_links
from wlanpi_mcp._compat import FastMCP
from wlanpi_mcp.client.core_client import CoreAPIError
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


class FakeCore:
    """
    wlanpi-core's profiler file endpoints over an in-memory data directory.

    Mirrors core 2.4.8: the manifest lists clients by colon MAC with their
    files sorted by name, ?mac= takes the dash form, and a file that is not
    there is a 404.
    """

    def __init__(self):
        self.files: dict[str, tuple[bytes, float]] = {}
        self.get = AsyncMock(side_effect=self._get)
        self.get_bytes = AsyncMock(side_effect=self._get_bytes)

    def put(self, path, data, mtime=None):
        self.files[path] = (data, time.time() if mtime is None else mtime)

    def _entry(self, path):
        data, mtime = self.files[path]
        modified = datetime.fromtimestamp(mtime, UTC).isoformat().replace("+00:00", "Z")
        return {"path": path, "size": len(data), "modified": modified}

    async def _get(self, path, params=None):
        assert path == "/api/v1/profiler/files"
        mac = (params or {}).get("mac")
        dirs = sorted({p.split("/")[1] for p in self.files if p.startswith("clients/")})
        clients = [
            {
                "mac": d.replace("-", ":"),
                "files": [
                    self._entry(p)
                    for p in sorted(self.files)
                    if p.startswith(f"clients/{d}/")
                ],
            }
            for d in dirs
            if mac is None or d == mac
        ]
        reports = [
            self._entry(p) for p in sorted(self.files) if p.startswith("reports/")
        ]
        return {"clients": clients, "reports": reports}

    async def _get_bytes(self, path):
        prefix = "/api/v1/profiler/files/"
        assert path.startswith(prefix)
        rel = unquote(path.removeprefix(prefix))
        if rel not in self.files:
            raise _core_error(404, "Profiler file not found")
        media = {
            ".json": "application/json",
            ".txt": "text/plain; charset=utf-8",
            ".pcap": "application/vnd.tcpdump.pcap",
            ".csv": "text/csv; charset=utf-8",
        }.get(os.path.splitext(rel)[1], "application/octet-stream")
        return self.files[rel][0], media


def _write_client(core, mac, bands=("5GHz",), mtime=None):
    for band in bands:
        # Not Path.with_suffix: the profiler's "2.4GHz" band has a dot in it.
        stem = f"clients/{mac}/{mac}_{band}"
        profile = {**PROFILE, "mac": mac}
        core.put(f"{stem}.json", json.dumps(profile).encode(), mtime)
        core.put(f"{stem}.txt", f"report for {mac} {band}\n".encode(), mtime)
        core.put(f"{stem}.pcap", b"\xd4\xc3\xb2\xa1" + mac.encode(), mtime)


@pytest.fixture
def core():
    return FakeCore()


@pytest.fixture(autouse=True)
def _clean_tickets():
    profiler_reports._TICKETS.clear()
    yield
    profiler_reports._TICKETS.clear()


def _tool(core):
    mcp = FastMCP("test")
    profiler_reports.register(mcp, core)
    return mcp._tool_manager._tools["get_profiler_reports"]


def _core_error(status, detail):
    request = httpx.Request("GET", "https://localhost:31415/api/v1/profiler/files")
    return CoreAPIError(
        httpx.Response(status, json={"detail": detail}, request=request)
    )


# ── json ─────────────────────────────────────────────────────────────────────


async def test_json_returns_parsed_profiles_without_the_frame(core):
    _write_client(core, MAC, bands=("5GHz", "2.4GHz"))
    tool = _tool(core)

    result = await tool.run({})

    core.get.assert_awaited_once_with("/api/v1/profiler/files", params=None)
    # Only the JSON profiles are downloaded for the inline answer.
    fetched = {c.args[0] for c in core.get_bytes.await_args_list}
    assert fetched == {
        f"/api/v1/profiler/files/clients/{MAC}/{MAC}_5GHz.json",
        f"/api/v1/profiler/files/clients/{MAC}/{MAC}_2.4GHz.json",
    }
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


async def test_json_can_keep_the_frame(core):
    _write_client(core, MAC)
    tool = _tool(core)

    result = await tool.run({"include_frame": True})

    assert result["clients"][0]["profiles"][0]["pcapng"] == PROFILE["pcapng"]


async def test_json_lists_session_reports_by_name_only(core):
    _write_client(core, MAC)
    core.put("reports/profiler-2026-10-04.csv", b"Client_Mac\n", 1_700_000_000)
    core.put("reports/notes.txt", b"not a session report")
    tool = _tool(core)

    result = await tool.run({})

    assert result["session_reports"] == [
        {
            "name": "profiler-2026-10-04.csv",
            "path": "reports/profiler-2026-10-04.csv",
            "size_bytes": len("Client_Mac\n"),
            "modified": "2023-11-14T22:13:20+00:00",
        }
    ]


async def test_clients_are_newest_first_and_capped(core):
    _write_client(core, OTHER, mtime=1_000)
    _write_client(core, MAC, mtime=2_000)
    tool = _tool(core)

    result = await tool.run({"max_clients": 1})

    assert [c["mac"] for c in result["clients"]] == [MAC]
    assert result["clients"][0]["modified"] == "1970-01-01T00:33:20+00:00"
    assert result["total_clients"] == 2
    assert result["returned_clients"] == 1
    assert result["truncated"] is True

    everything = await tool.run({"max_clients": 0})
    assert [c["mac"] for c in everything["clients"]] == [MAC, OTHER]
    assert everything["truncated"] is False


@pytest.mark.parametrize(
    "mac", ["EA:3C:46:D4:E3:B2", "ea-3c-46-d4-e3-b2", "ea3c.46d4.e3b2", "EA3C46D4E3B2"]
)
async def test_mac_filter_accepts_common_formats(core, mac):
    _write_client(core, MAC)
    _write_client(core, OTHER)
    tool = _tool(core)

    result = await tool.run({"mac": mac})

    core.get.assert_awaited_once_with("/api/v1/profiler/files", params={"mac": MAC})
    assert [c["mac"] for c in result["clients"]] == [MAC]
    assert result["total_clients"] == 1


@pytest.mark.parametrize("mac", ["../../etc", "ea:3c:46", "zz:zz:zz:zz:zz:zz"])
async def test_a_non_mac_filter_is_refused_before_core_is_called(core, mac):
    tool = _tool(core)

    result = await tool.run({"mac": mac})

    assert result["error"].startswith("not a MAC address")
    core.get.assert_not_awaited()


async def test_unknown_mac_says_so(core):
    _write_client(core, MAC)
    tool = _tool(core)

    result = await tool.run({"mac": OTHER})

    assert result["clients"] == []
    assert result["note"] == f"no profile for {OTHER}"


async def test_no_profiles_is_not_an_error(core):
    tool = _tool(core)

    result = await tool.run({})

    assert result["clients"] == [] and result["total_clients"] == 0
    assert result["session_reports"] == []
    assert "no client profiles" in result["note"]


async def test_a_corrupt_profile_is_reported_not_fatal(core):
    _write_client(core, MAC)
    core.put(f"clients/{MAC}/{MAC}_6GHz.json", b"{truncated")
    tool = _tool(core)

    result = await tool.run({})

    profiles = result["clients"][0]["profiles"]
    bad = [p for p in profiles if "error" in p]
    assert [p["file"] for p in bad] == [f"clients/{MAC}/{MAC}_6GHz.json"]
    assert any(p.get("manuf") == "Apple" for p in profiles)


async def test_a_profile_purged_after_the_listing_is_reported_not_fatal(core):
    _write_client(core, MAC, bands=("5GHz", "6GHz"))
    gone = f"clients/{MAC}/{MAC}_6GHz.json"
    real_get = core._get

    async def list_then_purge(path, params=None):
        manifest = await real_get(path, params)
        del core.files[gone]
        return manifest

    core.get.side_effect = list_then_purge
    tool = _tool(core)

    result = await tool.run({})

    by_file = {p["file"]: p for p in result["clients"][0]["profiles"]}
    assert "404" in by_file[gone]["error"]
    assert by_file[f"clients/{MAC}/{MAC}_5GHz.json"]["manuf"] == "Apple"


async def test_a_client_directory_core_lists_that_is_not_a_mac_is_skipped(core):
    _write_client(core, MAC)
    core.put("clients/not-a-mac/x.json", b"{}")
    tool = _tool(core)

    result = await tool.run({"max_clients": 0})

    assert [c["mac"] for c in result["clients"]] == [MAC]


async def test_file_paths_are_quoted_into_the_core_url(core):
    core.put(f"clients/{MAC}/{MAC}_5GHz #1.json", json.dumps(PROFILE).encode())
    tool = _tool(core)

    await tool.run({})

    [call] = core.get_bytes.await_args_list
    assert call.args[0] == (
        f"/api/v1/profiler/files/clients/{MAC}/{MAC}_5GHz%20%231.json"
    )


# ── core errors ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("output", ["json", "links", "zip"])
async def test_a_token_core_refuses_is_a_tool_error_with_core_detail(core, output):
    from mcp.server.fastmcp.exceptions import ToolError

    _write_client(core, MAC)
    core.get.side_effect = _core_error(401, "Invalid token")
    tool = _tool(core)

    with pytest.raises(ToolError, match="401: Invalid token"):
        await tool.run({"output": output})
    core.get_bytes.assert_not_awaited()
    assert profiler_reports._TICKETS == {}


async def test_an_older_core_without_the_endpoint_says_to_upgrade(core):
    core.get.side_effect = _core_error(404, "Not Found")
    tool = _tool(core)

    result = await tool.run({})

    assert set(result) == {"error"}
    assert "2.4.8" in result["error"]


async def test_a_core_error_on_a_file_is_not_swallowed(core):
    from mcp.server.fastmcp.exceptions import ToolError

    _write_client(core, MAC)
    core.get_bytes.side_effect = _core_error(500, "Internal Server Error")
    tool = _tool(core)

    with pytest.raises(ToolError, match="500"):
        await tool.run({"output": "links"})
    assert profiler_reports._TICKETS == {}


# ── links / zip ──────────────────────────────────────────────────────────────


async def test_links_mint_one_ticket_per_file_with_snapshots(core):
    _write_client(core, MAC)
    core.put("reports/profiler-2026-10-04.csv", b"Client_Mac,OUI_Manuf\n")
    tool = _tool(core)

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
    # The media type is the one core served the file with.
    assert by_name["profiler-2026-10-04.csv"].media_type.startswith("text/csv")
    assert by_name[f"{MAC}_5GHz.json"].media_type == "application/json"
    assert by_name[f"{MAC}_5GHz.pcap"].media_type == "application/vnd.tcpdump.pcap"

    # The ticket holds a snapshot: later changes on the device do not leak through.
    core.put("reports/profiler-2026-10-04.csv", b"changed")
    assert by_name["profiler-2026-10-04.csv"].data == b"Client_Mac,OUI_Manuf\n"


async def test_links_skip_a_file_purged_after_the_listing(core):
    _write_client(core, MAC)
    gone = f"clients/{MAC}/{MAC}_5GHz.txt"
    real_get = core._get

    async def list_then_purge(path, params=None):
        manifest = await real_get(path, params)
        del core.files[gone]
        return manifest

    core.get.side_effect = list_then_purge
    tool = _tool(core)

    result = await tool.run({"output": "links"})

    assert gone not in {f["path"] for f in result["files"]}
    assert len(result["files"]) == 2


async def test_links_can_leave_out_the_session_csvs(core):
    _write_client(core, MAC)
    core.put("reports/profiler-2026-10-04.csv", b"x\n")
    tool = _tool(core)

    result = await tool.run({"output": "links", "include_session_csv": False})

    assert not any(f["path"].startswith("reports/") for f in result["files"])
    assert not any("reports/" in c.args[0] for c in core.get_bytes.await_args_list)


async def test_links_build_urls_and_one_curl_from_the_request(core, monkeypatch):
    _write_client(core, MAC)
    monkeypatch.setattr(
        download_links, "request_base_url", lambda: "https://wlanpi-9be.local:8767"
    )
    tool = _tool(core)

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


async def test_zip_bundles_every_file_behind_one_ticket(core, monkeypatch):
    _write_client(core, MAC, mtime=1_700_000_000)
    _write_client(core, OTHER)
    core.put("reports/profiler-2026-10-04.csv", b"x\n")
    monkeypatch.setattr(download_links, "request_base_url", lambda: "https://h:8767")
    tool = _tool(core)

    result = await tool.run({"output": "zip"})

    [download] = profiler_reports._TICKETS.values()
    assert download.media_type == "application/zip"
    assert download.filename == result["filename"]
    assert result["filename"].startswith("profiler-reports-")
    assert result["size_bytes"] == len(download.data)
    assert result["sha256"] == hashlib.sha256(download.data).hexdigest()
    archive = zipfile.ZipFile(io.BytesIO(download.data))
    names = archive.namelist()
    assert sorted(names) == sorted(f"profiler/{p}" for p in result["files"])
    assert len(names) == 7  # 3 files x 2 clients + 1 csv
    pcap = f"clients/{MAC}/{MAC}_5GHz.pcap"
    assert archive.read(f"profiler/{pcap}") == core.files[pcap][0]
    # Entries carry the file's own mtime (when it was profiled), not "now".
    info = archive.getinfo(f"profiler/clients/{MAC}/{MAC}_5GHz.json")
    assert info.date_time == time.localtime(1_700_000_000)[:6]
    assert info.compress_type == zipfile.ZIP_DEFLATED
    assert result["download_url"].startswith("https://h:8767/profiler-report/")
    assert shlex.split(result["curl"])[-2:] == [
        result["filename"],
        result["download_url"],
    ]


async def test_zip_respects_the_mac_filter(core):
    _write_client(core, MAC)
    _write_client(core, OTHER)
    tool = _tool(core)

    result = await tool.run(
        {"output": "zip", "mac": OTHER, "include_session_csv": False}
    )

    assert all(p.startswith(f"clients/{OTHER}/") for p in result["files"])
    assert len(result["files"]) == 3


async def test_an_oversized_request_is_refused_before_downloading(core, monkeypatch):
    _write_client(core, MAC)
    monkeypatch.setattr(profiler_reports, "MAX_DOWNLOAD_BYTES", 10)
    tool = _tool(core)

    result = await tool.run({"output": "zip"})

    assert "byte limit" in result["error"]
    core.get_bytes.assert_not_awaited()
    assert profiler_reports._TICKETS == {}


async def test_invalid_output_is_rejected_by_the_schema(core):
    from mcp.server.fastmcp.exceptions import ToolError

    tool = _tool(core)

    with pytest.raises(ToolError):
        await tool.run({"output": "tarball"})
    core.get.assert_not_awaited()


async def test_expired_tickets_are_pruned_on_the_next_mint(core):
    _write_client(core, MAC)
    profiler_reports._TICKETS["stale"] = profiler_reports._Download(
        b"x", "x", "text/plain", expires=1.0
    )
    tool = _tool(core)

    await tool.run({"output": "zip"})

    assert "stale" not in profiler_reports._TICKETS
    assert len(profiler_reports._TICKETS) == 1
