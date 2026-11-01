"""Offline tests only: no Canvas, Penn, or real browser connections."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet, InvalidToken
from starlette.testclient import TestClient

from src.penn_server.app import create_app
from src.penn_server.config import Settings
from src.penn_server.oauth import challenge
from src.penn_server.session import SessionManager, SessionUnavailable
from src.penn_server.tools import TOOLS, CanvasTools
from src.penn_server.vault import Vault


@pytest.fixture
def setup(tmp_path):
    key = tmp_path / "master"
    key.write_bytes(Fernet.generate_key())
    key.chmod(0o600)
    owner = tmp_path / "owner"
    owner.write_text("a-very-long-owner-password-for-testing-only")
    owner.chmod(0o600)
    settings = Settings(
        "https://penn.example.test",
        "/abcdefghijklmnopqrstuvwxyz",
        tmp_path / "data",
        tmp_path / "runtime",
        key,
        owner,
        ("https://client.example.test/callback",),
    )
    vault = Vault(settings.state_dir, key)
    return settings, vault


def fake_browser():
    return SimpleNamespace(
        settings=SimpleNamespace(
            public_url="https://penn.example.test", prefix="/abcdefghijklmnopqrstuvwxyz"
        ),
        probe=AsyncMock(return_value=200),
        checkpoint=AsyncMock(),
        relogin=AsyncMock(return_value="healthy"),
        request=AsyncMock(return_value=({"id": "123"}, {})),
        start=AsyncMock(),
        close=AsyncMock(),
    )


def test_vault_encrypts_and_rejects_tampering(setup):
    _, vault = setup
    vault.write("credentials", {"password": "sensitive-value"})
    path = vault.root / "credentials.enc"
    assert b"sensitive-value" not in path.read_bytes()
    path.write_bytes(path.read_bytes()[:-10] + b"corruption")
    with pytest.raises(InvalidToken):
        vault.read("credentials")


def test_vault_refuses_colocated_key_and_path_traversal(setup):
    settings, vault = setup
    with pytest.raises(ValueError):
        vault.read("../escape")
    local = vault.root / "key"
    local.write_bytes(Fernet.generate_key())
    local.chmod(0o600)
    with pytest.raises(ValueError):
        Vault(vault.root, local)


@pytest.mark.asyncio
async def test_second_401_recovers_without_interaction(setup):
    _, vault = setup
    browser = fake_browser()
    browser.probe.side_effect = [401, 401, 200]
    manager = SessionManager(browser, vault)
    await manager.ensure()
    assert browser.probe.await_count == 3
    assert browser.relogin.await_count == 1
    assert manager.status()["phase"] == "healthy"


@pytest.mark.asyncio
async def test_one_login_attempt_per_incident_across_restart(setup):
    _, vault = setup
    browser = fake_browser()
    browser.probe.return_value = 401
    browser.relogin.return_value = "mfa_required"
    for _ in range(3):
        manager = SessionManager(browser, vault)
        with pytest.raises(SessionUnavailable):
            await manager.ensure()
    assert browser.relogin.await_count == 1
    assert manager.status()["push_reserved"] is True
    assert vault.read("outbox") is None


@pytest.mark.asyncio
async def test_crash_reservation_never_repeats_login(setup):
    _, vault = setup
    browser = fake_browser()
    browser.probe.return_value = 401
    vault.write(
        "session",
        {"incident": "existing", "phase": "recovering", "push_reserved": True},
    )
    with pytest.raises(SessionUnavailable):
        await SessionManager(browser, vault).ensure()
    browser.relogin.assert_not_awaited()


@pytest.mark.asyncio
async def test_network_failure_does_not_trigger_login(setup):
    _, vault = setup
    browser = fake_browser()
    browser.probe.return_value = 503
    with pytest.raises(SessionUnavailable):
        await SessionManager(browser, vault).ensure()
    browser.relogin.assert_not_awaited()


@pytest.mark.asyncio
async def test_every_write_blocked_before_browser_or_login(setup):
    settings, vault = setup
    browser = fake_browser()
    session = SimpleNamespace(ensure=AsyncMock())
    tools = CanvasTools(browser, session, settings, vault)
    for spec in TOOLS:
        if spec.method == "GET":
            continue
        args = {
            key: ["123"] if key == "recipient_ids" else "123" for key in spec.fields
        }
        with pytest.raises(PermissionError):
            await tools.execute(spec.name, args)
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        with pytest.raises(PermissionError):
            await tools.request(method, "/api/v1/users/self")
    browser.request.assert_not_awaited()
    session.ensure.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreign_pagination_blocked(setup):
    settings, vault = setup
    browser = fake_browser()
    browser.request.return_value = (
        [],
        {"link": '<https://evil.example/api/v1/courses?page=2>; rel="next"'},
    )
    tools = CanvasTools(browser, SimpleNamespace(ensure=AsyncMock()), settings, vault)
    with pytest.raises(ValueError):
        await tools.execute("list_courses", {})
    assert browser.request.await_count == 1


@pytest.mark.asyncio
async def test_inbox_read_never_marks_read(setup):
    settings, vault = setup
    browser = fake_browser()
    tools = CanvasTools(browser, SimpleNamespace(ensure=AsyncMock()), settings, vault)
    await tools.execute("get_conversation_details", {"conversation_id": "12"})
    assert browser.request.call_args.kwargs["params"]["auto_mark_as_read"] == "false"


def oauth_client(setup):
    settings, _ = setup
    return TestClient(
        create_app(settings, fake_browser()), base_url=settings.public_url
    ), settings


def test_mcp_requires_real_auth_even_at_secret_url(setup):
    client, settings = oauth_client(setup)
    response = client.post(
        settings.prefix + "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
    )
    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]
    assert response.headers["cache-control"] == "no-store"


def test_registration_rejects_unknown_redirect(setup):
    client, _ = oauth_client(setup)
    assert (
        client.post(
            "/register", json={"redirect_uris": ["https://evil.example/callback"]}
        ).status_code
        == 400
    )


def test_oauth_pkce_replay_rotation_and_revocation(setup):
    client, settings = oauth_client(setup)
    identifier = client.post(
        "/register", json={"redirect_uris": list(settings.redirects)}
    ).json()["client_id"]
    verifier = "v" * 64
    params = dict(
        client_id=identifier,
        redirect_uri=settings.redirects[0],
        response_type="code",
        code_challenge_method="S256",
        code_challenge=challenge(verifier),
        scope="canvas:read canvas:write",
        state="client-state",
    )
    page = client.get("/authorize", params=params)
    import re

    ticket = re.search(r'name="ticket" value="([^"]+)"', page.text).group(1)
    redirect = client.post(
        "/authorize",
        data={"ticket": ticket, "password": settings.owner_file.read_text()},
        follow_redirects=False,
    )
    assert redirect.status_code == 303
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(redirect.headers["location"]).query)
    assert query["state"] == ["client-state"]
    data = dict(
        grant_type="authorization_code",
        client_id=identifier,
        redirect_uri=settings.redirects[0],
        code=query["code"][0],
        code_verifier=verifier,
    )
    assert (
        client.post("/token", data=dict(data, code_verifier="x" * 64)).status_code
        == 400
    )
    issued = client.post("/token", data=data)
    assert issued.status_code == 200
    assert client.post("/token", data=data).status_code == 400
    token = issued.json()
    rotated = client.post(
        "/token",
        data=dict(
            grant_type="refresh_token",
            client_id=identifier,
            refresh_token=token["refresh_token"],
        ),
    ).json()
    assert "access_token" in rotated
    assert (
        client.post(
            "/token",
            data=dict(
                grant_type="refresh_token",
                client_id=identifier,
                refresh_token=token["refresh_token"],
            ),
        ).status_code
        == 400
    )
    client.post("/revoke", data={"token": rotated["refresh_token"]})
    response = client.post(
        settings.prefix + "/mcp",
        headers={"Authorization": "Bearer " + rotated["access_token"]},
        json={},
    )
    assert response.status_code == 401


def test_owner_signin_csrf_and_origin(setup):
    client, settings = oauth_client(setup)
    assert (
        client.post(
            settings.prefix + "/login",
            data={"password": settings.owner_file.read_text()},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/register", headers={"Origin": "https://evil.example"}, json={}
        ).status_code
        == 403
    )
    assert client.get("/authorize", headers={"Host": "evil.example"}).status_code == 400


def test_viewer_is_private(setup):
    client, settings = oauth_client(setup)
    for path in ("/view", "/screen", "/viewer.js"):
        assert client.get(settings.prefix + "/login" + path).status_code == 403
    assert (
        client.post(
            settings.prefix + "/login/action", json={"kind": "key", "key": "Enter"}
        ).status_code
        == 403
    )


def test_heartbeat_config_rejects_long_intervals(setup):
    settings, _ = setup
    from dataclasses import replace

    with pytest.raises(ValueError):
        replace(settings, heartbeat_seconds=1000)


def test_real_mcp_protocol_with_simulated_canvas(setup):
    settings, vault = setup
    browser = fake_browser()
    import time

    from src.penn_server.oauth import digest

    vault.write(
        "oauth",
        dict(
            clients={},
            codes={},
            refresh={},
            tokens={
                digest("test-access-token"): dict(
                    client="test-client",
                    scopes=["canvas:read"],
                    resource=settings.public_url + settings.prefix + "/mcp",
                    expires=time.time() + 3600,
                )
            },
        ),
    )
    with TestClient(
        create_app(settings, browser), base_url=settings.public_url
    ) as client:
        headers = {
            "Authorization": "Bearer test-access-token",
            "Accept": "application/json, text/event-stream",
        }
        init = client.post(
            settings.prefix + "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "offline-test", "version": "1"},
                },
            },
        )
        assert init.status_code == 200, init.text
        listed = client.post(
            settings.prefix + "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert listed.status_code == 200, listed.text
        tools = {t["name"]: t for t in listed.json()["result"]["tools"]}
        assert "scan_canvas" in tools and "calculate_grade_scenarios" in tools
        assert tools["get_assignment_details"]["inputSchema"]["required"] == [
            "course_id",
            "assignment_id",
        ]
        called = client.post(
            settings.prefix + "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_self", "arguments": {}},
            },
        )
        assert called.status_code == 200, called.text
        assert not called.json()["result"].get("isError")
        blocked = client.post(
            settings.prefix + "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "submit_assignment",
                    "arguments": {
                        "course_id": "1",
                        "assignment_id": "2",
                        "body": "test",
                    },
                },
            },
        )
        assert blocked.json()["result"]["isError"] is True
        assert all(call.args[0] == "GET" for call in browser.request.call_args_list)


def test_grade_scenarios_weighting_drops_and_excused():
    from src.penn_server.grades import calculate

    groups = [
        {
            "id": 1,
            "group_weight": 40,
            "rules": {"drop_lowest": 1},
            "assignments": [
                {"id": 1, "points_possible": 10, "submission": {"score": 2}},
                {"id": 2, "points_possible": 10, "submission": {"score": 10}},
                {
                    "id": 3,
                    "points_possible": 10,
                    "submission": {"score": 0, "excused": True},
                },
            ],
        },
        {
            "id": 2,
            "group_weight": 60,
            "assignments": [
                {"id": 4, "points_possible": 100, "submission": {"score": 50}},
            ],
        },
    ]
    result = calculate(groups, {}, True)
    assert result["estimated_percent"] == 70
    assert result["groups"][0]["dropped"] == ["1"]
    assert calculate(groups, {"4": 100}, True)["estimated_percent"] == 100


@pytest.mark.asyncio
async def test_daily_scan_schedule_deduplicates_after_restart(setup):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from src.penn_server.schedule import ReadOnlySchedule

    settings, vault = setup
    tools = SimpleNamespace(scan=AsyncMock(return_value={"courses": []}))
    now = datetime(2026, 11, 1, 9, 5, tzinfo=ZoneInfo("America/New_York"))
    await ReadOnlySchedule(tools, vault).tick(now)
    await ReadOnlySchedule(tools, vault).tick(now)
    assert tools.scan.await_count == 1
    assert vault.read("schedule")["last_scan_day"] == "2026-11-01"


@pytest.mark.asyncio
async def test_download_strips_canvas_cookies_on_external_storage(setup):
    import base64

    import httpx

    from src.penn_server.files import download

    settings, _ = setup
    context = SimpleNamespace(
        cookies=AsyncMock(
            return_value=[
                dict(
                    name="session",
                    value="fake-cookie",
                    domain="penn.instructure.com",
                    path="/",
                )
            ]
        )
    )
    browser = SimpleNamespace(settings=settings, context=context)
    seen = []

    def transport(request):
        seen.append(request)
        if request.url.host == "penn.instructure.com":
            return httpx.Response(
                302, headers={"location": "https://bucket.s3.amazonaws.com/file"}
            )
        return httpx.Response(200, content=b"example file")

    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(transport), **kwargs)

    result = await download(
        browser,
        {"url": "https://penn.instructure.com/files/1/download", "size": 12},
        factory,
    )
    assert base64.b64decode(result["content"]) == b"example file"
    assert "fake-cookie" in seen[0].headers["cookie"]
    assert "cookie" not in seen[1].headers
    assert "authorization" not in seen[1].headers


def test_download_rejects_untrusted_hosts():
    from src.penn_server.files import allowed

    for url in (
        "http://penn.instructure.com/file",
        "https://127.0.0.1/file",
        "https://evil.example/file",
        "https://penn.instructure.com.evil.example/file",
        "https://penn.instructure.com:8443/file",
    ):
        assert not allowed(url, "https://penn.instructure.com")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,args,expected",
    [
        (
            "submit_assignment",
            {"course_id": "1", "assignment_id": "2", "body": "Simulated draft"},
            {
                "submission": {
                    "submission_type": "online_text_entry",
                    "body": "Simulated draft",
                }
            },
        ),
        (
            "send_message",
            {
                "recipient_ids": ["123"],
                "subject": "Simulated subject",
                "body": "Simulated message",
            },
            {
                "recipients": ["123"],
                "subject": "Simulated subject",
                "body": "Simulated message",
            },
        ),
        (
            "comment_on_my_submission",
            {
                "course_id": "1",
                "assignment_id": "2",
                "text_comment": "Simulated comment",
            },
            {"comment": {"text_comment": "Simulated comment"}},
        ),
    ],
)
async def test_write_encoding_and_one_use_confirmation_simulated(
    setup, name, args, expected
):
    from dataclasses import replace

    from src.penn_server.tools import principal

    settings, vault = setup
    browser = fake_browser()
    tools = CanvasTools(
        browser,
        SimpleNamespace(ensure=AsyncMock()),
        replace(settings, testing_read_only=False),
        vault,
    )
    context = principal.set(
        {"client": "simulated-client", "scopes": ["canvas:read", "canvas:write"]}
    )
    try:
        preview = await tools.execute(name, args)
        browser.request.assert_not_awaited()
        await tools.execute(name, args, preview["confirmation"])
        mutations = [
            call for call in browser.request.call_args_list if call.args[0] != "GET"
        ]
        assert len(mutations) == 1
        assert mutations[0].kwargs["data"] == expected
        count = browser.request.await_count
        with pytest.raises(PermissionError):
            await tools.execute(name, args, preview["confirmation"])
        assert browser.request.await_count == count
    finally:
        principal.reset(context)


@pytest.mark.asyncio
async def test_ambiguous_write_is_not_replayed(setup):
    from dataclasses import replace

    from src.penn_server.tools import principal

    settings, vault = setup
    browser = fake_browser()
    browser.request.side_effect = TimeoutError("Simulated timeout")
    tools = CanvasTools(
        browser,
        SimpleNamespace(ensure=AsyncMock()),
        replace(settings, testing_read_only=False),
        vault,
    )
    token = principal.set(
        {"client": "simulated-client", "scopes": ["canvas:read", "canvas:write"]}
    )
    args = {"course_id": "1", "assignment_id": "2", "body": "Simulated text"}
    try:
        preview = await tools.execute("submit_assignment", args)
        with pytest.raises(RuntimeError, match="uncertain"):
            await tools.execute("submit_assignment", args, preview["confirmation"])
        assert browser.request.await_count == 1
        assert vault.read("last_mutation")["outcome"] == "unknown_do_not_retry"
    finally:
        principal.reset(token)


@pytest.mark.asyncio
async def test_browser_guard_blocks_writes_below_tool_layer(setup):
    from src.penn_server.browser import Browser

    settings, vault = setup
    browser = Browser(settings, vault)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        with pytest.raises(PermissionError):
            await browser.request(method, "/api/v1/courses/1/assignments/2/submissions")
    for method, path, blocked in [
        ("POST", "/api/v1/conversations", True),
        ("POST", "/login/saml", False),
        ("GET", "/api/v1/users/self", False),
    ]:
        request = SimpleNamespace(
            url=settings.canvas_origin + path,
            method=method,
            is_navigation_request=lambda: False,
        )
        route = SimpleNamespace(
            request=request, abort=AsyncMock(), continue_=AsyncMock()
        )
        await browser._route(route)
        assert route.abort.await_count == int(blocked)
        assert route.continue_.await_count == int(not blocked)


@pytest.mark.asyncio
async def test_password_capture_requires_verified_https_origin(setup):
    from dataclasses import replace
    from src.penn_server.browser import Browser

    settings, vault = setup
    browser = Browser(replace(settings, login_hosts=("login.upenn.example",)), vault)
    value = {"username": "simulated-user", "password": "simulated-password"}
    for url in ("http://login.upenn.example", "https://evil.example"):
        await browser._capture({"frame": SimpleNamespace(url=url)}, value)
        assert vault.read("pennkey_pending") is None
    await browser._capture(
        {"frame": SimpleNamespace(url="https://login.upenn.example")}, value
    )
    assert vault.read("pennkey_pending") == value


@pytest.mark.asyncio
async def test_supervisor_recovers_transient_failures_and_restarts_persistent_crash():
    import asyncio
    from unittest.mock import Mock
    from src.penn_server.maintenance import Maintenance

    tools = SimpleNamespace(lock=asyncio.Lock())
    session = SimpleNamespace(
        heartbeat=AsyncMock(
            return_value=True, side_effect=RuntimeError("simulated-sensitive-detail")
        ),
        status=lambda: {"phase": "healthy"},
    )
    schedule = SimpleNamespace(tick=AsyncMock())
    restart = Mock()
    clock = Mock(return_value=0)
    supervisor = Maintenance(
        tools, session, schedule, 720, restart=restart, clock=clock
    )
    await supervisor.tick()
    clock.return_value = 10
    session.heartbeat.side_effect = None
    await supervisor.tick()
    assert supervisor.failures == 0
    restart.assert_not_called()
    session.heartbeat.side_effect = RuntimeError("simulated-sensitive-detail")
    for now in (730, 740, 760):
        clock.return_value = now
        await supervisor.tick()
    restart.assert_called_once()
    schedule.tick.assert_awaited_once()


def test_local_logs_are_bounded_private_and_redact_exception_text(tmp_path):
    import logging
    from src.penn_server.local_logs import configure
    from src.penn_server.maintenance import log

    configure(tmp_path / "logs")
    try:
        log.error("maintenance_failed error_type=%s", "RuntimeError")
        text = (tmp_path / "logs/server.log").read_text()
        assert "maintenance_failed error_type=RuntimeError" in text
        assert (tmp_path / "logs/server.log").stat().st_mode & 0o077 == 0
    finally:
        logger = logging.getLogger("penn")
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
        logger.propagate = True


def test_penn_server_has_no_mail_transport_credentials_or_startup_requirement():
    import inspect
    import src.penn_server.app as app
    import src.penn_server.provision as provision
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    assert not (root / "src/penn_server/notifications.py").exists()
    assert "gws_email" not in inspect.getsource(app)
    assert "gmail" not in inspect.getsource(app)
    assert "gmail" not in inspect.getsource(provision)
    assert "PENN_GMAIL_ADDRESS" not in (root / "deploy/penn/compose.yaml").read_text()
    assert "restart: always" in (root / "deploy/penn/compose.yaml").read_text()
    assert "email" not in Settings.__dataclass_fields__


def test_retired_alert_records_are_removed_without_touching_auth(setup):
    from src.penn_server.migrations import remove_retired_alert_state

    _, vault = setup
    for name in ("gmail", "outbox", "browser", "pennkey", "oauth", "session"):
        vault.write(name, {"simulated": "value"})
    remove_retired_alert_state(vault)
    assert vault.read("gmail") is None
    assert vault.read("outbox") is None
    for name in ("browser", "pennkey", "oauth", "session"):
        assert vault.read(name) == {"simulated": "value"}


def test_production_override_enables_tools_but_keeps_test_default_read_only():
    from pathlib import Path
    import yaml

    root = Path(__file__).resolve().parents[2]
    base = yaml.safe_load((root / "deploy/penn/compose.yaml").read_text())
    production = yaml.safe_load(
        (root / "deploy/penn/compose.production.yaml").read_text()
    )
    assert base["services"]["penn"]["environment"]["PENN_TESTING_READ_ONLY"] == "true"
    assert (
        production["services"]["penn"]["environment"]["PENN_TESTING_READ_ONLY"]
        == "false"
    )
    assert base["services"]["penn"]["restart"] == "always"
