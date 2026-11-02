"""Offline transport tests; no player, real course, or authentication calls."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.penn_server.panopto import Panopto, Forms, captions, guid

SID = "11111111-2222-3333-4444-555555555555"


def run(coro):
    return asyncio.run(coro)


def client(responses=()):
    records = {}
    vault = SimpleNamespace(read=lambda k, default=None: records.get(k, default),
                            write=lambda k, v: records.__setitem__(k, v))
    context = SimpleNamespace(add_cookies=AsyncMock(), cookies=AsyncMock(return_value=[]),
                              request=SimpleNamespace(fetch=AsyncMock(side_effect=responses), post=AsyncMock()))
    tools = SimpleNamespace(browser=SimpleNamespace(context=context), vault=vault,
                            session=SimpleNamespace(ensure=AsyncMock()), lock=asyncio.Lock(),
                            request=AsyncMock())
    return Panopto(tools), records


def response(status=200, text="", url="https://upenn.hosted.panopto.com/Panopto/LTI/LTI.aspx", headers=None):
    return SimpleNamespace(status=status, headers=headers or {}, url=url,
                           text=AsyncMock(return_value=text))


def test_captions_keep_multiline_and_times():
    assert captions("1\r\n00:00:01,200 --> 00:00:04,500\r\nFirst\r\nsecond\r\n\r\n") == [
        {"start": "00:00:01.200", "end": "00:00:04.500", "text": "First\nsecond"}]
    assert captions("<html>Sign in</html>") == []


def test_uuid_rejects_urls_and_paths():
    for value in ("../x", "https://evil.test", None):
        with pytest.raises(ValueError):
            guid(value)


def test_form_parser_only_collects_hidden_auth_fields():
    parser = Forms()
    parser.feed('<form action="/Panopto/LTI/LTI.aspx" method="post"><input type="hidden" name="a" value="b&amp;c"><input type="password" name="secret"></form>')
    assert parser.forms[0]["fields"] == {"a": "b&c"}


def test_redirects_reject_foreign_hosts_before_second_request():
    obj, _ = client([response(302, headers={"location": "https://evil.test/x"})])
    with pytest.raises(RuntimeError, match="destination"):
        run(obj.fetch("https://upenn.hosted.panopto.com/Panopto/LTI/LTI.aspx"))
    assert obj.context.request.fetch.await_count == 1


def test_307_preserves_auth_post_303_changes_to_get():
    obj, _ = client([response(307, headers={"location": "/Panopto/LTI/next"}),
                     response(303, headers={"location": "/Panopto/Pages/Sessions/List.aspx"}), response()])
    run(obj.fetch("https://upenn.hosted.panopto.com/Panopto/LTI/LTI.aspx", "POST", {"auth": "test"}))
    calls = obj.context.request.fetch.await_args_list
    assert [call.kwargs["method"] for call in calls] == ["POST", "POST", "GET"]
    assert calls[2].kwargs["form"] is None


def test_launch_posts_lti_without_loading_player_and_saves_cookies():
    obj, records = client([response(text='<form method="post" action="https://upenn.hosted.panopto.com/Panopto/LTI/LTI.aspx"><input type="hidden" name="oauth" value="test"></form>', url="https://penn.instructure.com/courses/123/external_tools/4"),
                           response(text='folderID="' + SID + '"')])
    obj.tools.request.return_value = ([{"id": 4, "name": "Panopto"}], {})
    run(obj.launch("123"))
    assert records["panopto_courses"]["123"]["folder_id"] == SID
    assert "panopto" in records
    assert obj.context.request.fetch.await_args_list[1].kwargs["method"] == "POST"


def test_missing_lti_never_saves_a_successful_session():
    obj, records = client([response(text="Canvas login", url="https://penn.instructure.com/login")])
    obj.tools.request.return_value = ([{"id": 4, "name": "Panopto"}], {})
    with pytest.raises(RuntimeError, match="did not expose"):
        run(obj.launch("123"))
    assert not records


def test_transport_does_not_allow_viewing_events():
    obj, _ = client()
    for endpoint in ("AddViewingEvent", "Heartbeat", "UpdateSession", "GetDeliveryInfo"):
        with pytest.raises(ValueError):
            run(obj.api(endpoint, {}))
    obj.context.request.post.assert_not_called()


def test_transcript_is_untrusted_and_never_requests_media():
    obj, _ = client([response(text="1\n00:00:01,000 --> 00:00:02,000\nHello\n")])
    result = run(obj.transcript(SID))
    assert result["untrusted"] is True
    assert result["data"]["captions"][0]["text"] == "Hello"
    assert "GenerateSRT.ashx" in obj.context.request.fetch.await_args.args[0]
    obj.context.request.post.assert_not_called()


def test_expired_session_retries_read_once():
    obj, _ = client()
    ok = response(headers={"content-type": "application/json"})
    ok.json = AsyncMock(return_value={"d": {"Results": []}})
    obj.context.request.post.side_effect = [response(401), ok]
    obj.launch = AsyncMock()
    assert run(obj.api("GetSessions", {}, "123")) == {"Results": []}
    obj.launch.assert_awaited_once_with("123")


def test_no_course_and_folder_is_rejected_before_network():
    obj, _ = client()
    for args in ({}, {"course": "123", "folder": SID}):
        with pytest.raises(ValueError):
            run(obj.lectures(**args))
    obj.tools.session.ensure.assert_not_called()


def test_cookie_restore_filters_foreign_domains():
    obj, records = client()
    records["panopto"] = {"cookies": [{"domain": "evil.test", "name": "x"},
                                          {"domain": "upenn.hosted.panopto.com", "name": "y"}]}
    run(obj.restore())
    assert obj.context.add_cookies.await_args.args[0] == [{"domain": "upenn.hosted.panopto.com", "name": "y"}]


def test_analytics_guard_blocks_playback_heartbeats_and_events():
    from src.penn_server.panopto import analytics_request_allowed
    root = "https://upenn.hosted.panopto.com"
    for path, method in (("/Panopto/Pages/Viewer.aspx?id=" + SID, "GET"),
                         ("/Panopto/Services/Data.svc/AddViewingEvent", "POST"),
                         ("/Panopto/Services/Analytics.svc/Heartbeat", "POST"),
                         ("/media/video.mp4", "GET"),
                         ("/Panopto/Services/Data.svc/UpdateSession", "POST")):
        assert not analytics_request_allowed(root + path, method)
    assert not analytics_request_allowed("https://evil.test/a.js", "GET")
    assert analytics_request_allowed(root + "/Panopto/Pages/Analytics.aspx", "GET")
    assert analytics_request_allowed(root + "/Panopto/Services/Analytics.svc/GetUserSessions", "POST")


def test_lectures_paginates_without_creating_view_events():
    obj, _ = client()
    first = {"Results": [{"ID": SID, "Name": "Lecture", "Date": "2026-11-01", "Duration": 50}] * 100}
    obj.api = AsyncMock(side_effect=[first, {"Results": []}])
    result = run(obj.lectures(folder=SID))
    assert result["untrusted"]
    assert len(result["data"]["lectures"]) == 100
    assert [call.args[1]["query"]["page"] for call in obj.api.await_args_list] == [0, 1]


def test_tool_registration_marks_all_panopto_reads():
    from src.penn_server.panopto import register
    class MCP:
        def __init__(self):
            self.tools = {}
        def tool(self, **kwargs):
            def save(fn):
                self.tools[fn.__name__] = kwargs
                return fn
            return save
    obj, _ = client()
    mcp = MCP()
    register(obj.tools, mcp)
    assert set(mcp.tools) == {"list_panopto_lectures", "get_panopto_transcript", "get_panopto_progress"}
    for meta in mcp.tools.values():
        assert meta["annotations"].readOnlyHint
        assert meta["annotations"].destructiveHint is False
