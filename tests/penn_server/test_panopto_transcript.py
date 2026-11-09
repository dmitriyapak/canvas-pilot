"""Offline transcript tests. No Canvas, Panopto, or browser connections."""
import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest

from src.penn_server.panopto import (
    Panopto, allowed_caption_url, caption_target, render_transcript)
from src.penn_server.panopto_map import delivery_urls

SID = "11111111-2222-3333-4444-555555555555"
OTHER = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
COURSE = "123"
ASSIGNMENT = "456"
CAPTION = "https://upenn.hosted.panopto.com/Panopto/api/v1/sessions/" + SID + "/captions"
SRT = "1\n00:00:01,000 --> 00:00:04,000\nAlpha sentence one.\n\n2\n00:56:58,000 --> 00:57:01,000\nOmega sentence two.\n"
IFRAME = (
    '<iframe class="lti-embed" title="Lecture eight" '
    'src="https://canvas.upenn.edu/courses/123/external_tools/retrieve?'
    'display=borderless&amp;url=https%3A%2F%2Fupenn.hosted.panopto.com%2FPanopto%2FLTI%2FLTI.aspx'
    '%3Fcustom_context_delivery%3D11111111-2222-3333-4444-555555555555"></iframe>'
    '<iframe title="other lecture" src="https://canvas.upenn.edu/courses/123/external_tools/retrieve?'
    'display=borderless&amp;url=https%3A%2F%2Fupenn.hosted.panopto.com%2FPanopto%2FLTI%2FLTI.aspx'
    '%3Fcustom_context_delivery%3Daaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"></iframe>'
)
ROOT = Path(__file__).resolve().parents[2]


def run(coro):
    return asyncio.run(coro)


def response(status=200, text="", url="https://upenn.hosted.panopto.com/Panopto/LTI/LTI.aspx",
             headers=None, json_body=None):
    obj = SimpleNamespace(
        status=status, headers=headers or {}, url=url,
        text=AsyncMock(return_value=text))
    obj.json = AsyncMock(return_value=json_body)
    return obj


def client(responses):
    records = {"panopto_courses": {COURSE: {"folder_id": "11111111-2222-3333-4444-555555555555"}}}
    calls = []

    async def canvas_request(method, path, params=None, data=None):
        calls.append((method, path))
        assert method == "GET"
        assert "/submissions" not in path and not path.endswith("/done")
        if path == f"/api/v1/courses/{COURSE}/assignments/{ASSIGNMENT}":
            return ({"name": "Week eight lecture", "description": IFRAME,
                     "html_url": f"https://canvas.upenn.edu/courses/{COURSE}/assignments/{ASSIGNMENT}"}, {})
        if path == "/api/v1/courses":
            return ([{"id": int(COURSE), "name": "Sample Course", "course_code": "SAMPLE-1"}], {})
        if path == f"/api/v1/courses/{COURSE}/modules":
            return ([{"id": 1, "name": "Week eight", "items": [{
                "type": "Assignment", "content_id": int(ASSIGNMENT),
                "title": "Week eight lecture",
                "html_url": f"https://canvas.upenn.edu/courses/{COURSE}/assignments/{ASSIGNMENT}"}]}], {})
        if path == f"/api/v1/courses/{COURSE}/external_tools":
            return ([{"id": 4, "name": "Panopto"}], {})
        if path.endswith("/modules") and path != f"/api/v1/courses/{COURSE}/modules":
            return ([], {})
        raise AssertionError(path)

    context = SimpleNamespace(
        add_cookies=AsyncMock(), cookies=AsyncMock(return_value=[]),
        request=SimpleNamespace(fetch=AsyncMock(side_effect=responses), post=AsyncMock()))
    tools = SimpleNamespace(
        browser=SimpleNamespace(context=context), vault=SimpleNamespace(
            read=lambda key, default=None: records.get(key, default),
            write=lambda key, value: records.__setitem__(key, value)),
        session=SimpleNamespace(ensure=AsyncMock()), lock=asyncio.Lock(),
        request=AsyncMock(side_effect=canvas_request))
    return Panopto(tools), records, calls


def lti_form(url):
    return response(
        text='<form method="post" action="https://upenn.hosted.panopto.com/Panopto/LTI/LTI.aspx">'
             '<input type="hidden" name="oauth" value="test"></form>',
        url=url)


def landed():
    return response(text="panopto", url="https://upenn.hosted.panopto.com/Panopto/Pages/Embed.aspx")


def session(body, status=200):
    headers = {"content-type": "application/json"} if status == 200 else {}
    return response(status=status, json_body=body, headers=headers,
                    url="https://upenn.hosted.panopto.com/Panopto/api/v1/sessions/" + SID)


def urls_of(obj):
    return [call.args[0] for call in obj.context.request.fetch.await_args_list]


def test_delivery_url_comes_from_the_assignment_embed_for_that_session():
    found = delivery_urls(IFRAME, SID)
    assert len(found) == 1
    assert found[0]["session_name"] == "Lecture eight"
    assert parse_qs(urlsplit(found[0]["lti_url"]).query)["custom_context_delivery"] == [SID]
    assert delivery_urls(IFRAME, OTHER)[0]["session_name"] == "other lecture"
    assert delivery_urls("<iframe src='https://upenn.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=" + SID + "'></iframe>", SID) == []


def test_caption_target_uses_only_the_documented_field():
    assert caption_target({"Urls": {"CaptionDownloadUrl": " https://upenn.hosted.panopto.com/Panopto/a "}}) == "https://upenn.hosted.panopto.com/Panopto/a"
    assert caption_target({"urls": {"captionDownloadUrl": ""}}) is None
    assert caption_target({"Urls": {"ViewerUrl": "https://upenn.hosted.panopto.com/Panopto/Pages/Viewer.aspx"}}) is None
    assert not allowed_caption_url("https://evil.test/Panopto/captions.srt")
    rendered = render_transcript(SRT)
    assert rendered["captions"][0]["text"] == "Alpha sentence one."
    assert "Omega sentence two." in rendered["text"]
    assert render_transcript("WEBVTT\n\n") is None
    assert render_transcript("Alpha sentence one.\n\nOmega sentence two.")["format"] == "text"


def test_transcript_launches_the_matching_delivery_link_and_downloads_caption_url():
    launch = "https://canvas.upenn.edu/courses/123/external_tools/retrieve?display=borderless"
    obj, records, calls = client([
        lti_form(launch), landed(),
        session({"Urls": {"CaptionDownloadUrl": CAPTION}}),
        response(text=SRT, url=CAPTION, headers={"content-type": "text/plain"}),
    ])
    result = run(obj.transcript(SID, course=COURSE, assignment_id=ASSIGNMENT))
    fetched = urls_of(obj)
    assert "external_tools/retrieve" in fetched[0]
    assert SID in fetched[0] and OTHER not in fetched[0]
    assert fetched[2] == "https://upenn.hosted.panopto.com/Panopto/api/v1/sessions/" + SID
    assert fetched[3] == CAPTION
    assert all("GenerateSRT" not in url for url in fetched)
    assert obj.context.request.fetch.await_args_list[1].kwargs["method"] == "POST"
    assert result["untrusted"] is True
    assert result["data"]["captions"][1]["text"] == "Omega sentence two."
    assert result["data"]["session_name"] == "Lecture eight"
    assert result["data"]["canvas_item_title"] == "Week eight lecture"
    assert records["panopto_courses"][COURSE]["folder_id"] == "11111111-2222-3333-4444-555555555555"
    assert calls == [("GET", f"/api/v1/courses/{COURSE}/assignments/{ASSIGNMENT}")]
    obj.context.request.post.assert_not_called()


def test_session_id_alone_still_finds_the_embedded_lecture():
    obj, _, calls = client([
        lti_form("https://canvas.upenn.edu/courses/123/external_tools/retrieve"),
        landed(), session({"Urls": {"CaptionDownloadUrl": CAPTION}}),
        response(text=SRT, url=CAPTION),
    ])
    result = run(obj.transcript(SID))
    assert result["data"]["text"].startswith("Alpha sentence one.")
    assert calls[0] == ("GET", "/api/v1/courses")
    assert any(path.endswith("/assignments/" + ASSIGNMENT) for _, path in calls)
    assert SID in urls_of(obj)[0]


def test_course_name_selects_one_course():
    obj, _, calls = client([
        lti_form("https://canvas.upenn.edu/courses/123/external_tools/retrieve"),
        landed(), session({"urls": {"captionDownloadUrl": CAPTION}}),
        response(text=SRT, url=CAPTION),
    ])
    result = run(obj.transcript(SID, course="Sample Course"))
    assert result["data"]["format"] == "srt"
    assert calls[0] == ("GET", "/api/v1/courses")


def test_missing_caption_url_is_not_reported_as_access_denied():
    obj, _, _ = client([
        lti_form("https://canvas.upenn.edu/courses/123/external_tools/retrieve"),
        landed(), session({"Urls": {"CaptionDownloadUrl": None}}),
    ])
    with pytest.raises(RuntimeError, match="no CaptionDownloadUrl") as caught:
        run(obj.transcript(SID, COURSE, ASSIGNMENT))
    assert "access denied" not in str(caught.value).lower()
    assert "Viewer.aspx" not in "".join(urls_of(obj))


def test_access_denial_is_not_reported_as_missing_captions():
    obj, _, _ = client([
        lti_form("https://canvas.upenn.edu/courses/123/external_tools/retrieve"),
        landed(), session({}, status=403),
        response(status=200, text="This session is unavailable.", url="https://upenn.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=" + SID),
    ])
    with pytest.raises(RuntimeError, match="not treated as missing") as caught:
        run(obj.transcript(SID, COURSE, ASSIGNMENT))
    message = str(caught.value).lower()
    assert "captions unavailable or access denied" not in message
    assert "no captiondownloadurl" not in message
    assert all("GenerateSRT" not in url for url in urls_of(obj))


def test_viewer_retry_can_complete_session_api_access_without_playback():
    shell = "<html><body>" + ("player " * 400) + "</body></html>"
    obj, _, _ = client([
        lti_form("https://canvas.upenn.edu/courses/123/external_tools/retrieve"),
        landed(), session({}, status=401),
        response(text=shell, url="https://upenn.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=" + SID),
        session({"Urls": {"CaptionDownloadUrl": CAPTION}}),
        response(text=SRT, url=CAPTION),
    ])
    result = run(obj.transcript(SID, COURSE, ASSIGNMENT))
    fetched = urls_of(obj)
    assert fetched[3].startswith("https://upenn.hosted.panopto.com/Panopto/Pages/Viewer.aspx?id=" + SID)
    assert not any(url.endswith((".mp4", ".m3u8", ".mpd")) for url in fetched)
    assert result["data"]["captions"][0]["start"] == "00:00:01.000"


def test_html_caption_body_is_access_denial():
    obj, _, _ = client([
        lti_form("https://canvas.upenn.edu/courses/123/external_tools/retrieve"),
        landed(), session({"Urls": {"CaptionDownloadUrl": CAPTION}}),
        response(text="<!DOCTYPE html><html>Sign in</html>", url=CAPTION),
    ])
    with pytest.raises(RuntimeError, match="not treated as missing"):
        run(obj.transcript(SID, COURSE, ASSIGNMENT))


def test_empty_caption_file_is_not_an_access_error():
    obj, _, _ = client([
        lti_form("https://canvas.upenn.edu/courses/123/external_tools/retrieve"),
        landed(), session({"Urls": {"CaptionDownloadUrl": CAPTION}}),
        response(text="WEBVTT\n\n", url=CAPTION),
    ])
    with pytest.raises(RuntimeError, match="contained no text") as caught:
        run(obj.transcript(SID, COURSE, ASSIGNMENT))
    assert "access denied" not in str(caught.value).lower()


def test_foreign_caption_host_is_rejected_before_download():
    obj, _, _ = client([
        lti_form("https://canvas.upenn.edu/courses/123/external_tools/retrieve"),
        landed(), session({"Urls": {"CaptionDownloadUrl": "https://evil.test/captions.srt"}}),
    ])
    with pytest.raises(RuntimeError, match="not treated as missing"):
        run(obj.transcript(SID, COURSE, ASSIGNMENT))
    assert all("evil.test" not in url for url in urls_of(obj))


def test_plain_text_transcript_is_returned_without_invented_timestamps():
    prose = "Alpha sentence one.\n\nOmega sentence two."
    obj, _, _ = client([
        lti_form("https://canvas.upenn.edu/courses/123/external_tools/retrieve"),
        landed(), session({"Urls": {"CaptionDownloadUrl": CAPTION}}),
        response(text=prose, url=CAPTION),
    ])
    result = run(obj.transcript(SID, COURSE, ASSIGNMENT))
    assert result["data"]["format"] == "text"
    assert result["data"]["captions"] == [{"start": None, "end": None, "text": prose}]


def test_api_supplied_caption_path_is_followed_and_not_built_locally():
    supplied = "https://upenn.hosted.panopto.com/Panopto/Pages/Transcription/GenerateSRT.ashx?id=" + SID
    obj, _, _ = client([
        lti_form("https://canvas.upenn.edu/courses/123/external_tools/retrieve"),
        landed(), session({"Urls": {"CaptionDownloadUrl": supplied}}),
        response(text=SRT, url=supplied),
    ])
    run(obj.transcript(SID, COURSE, ASSIGNMENT))
    assert urls_of(obj)[3] == supplied
    assert "GenerateSRT" not in (ROOT / "src/penn_server/panopto.py").read_text()


def test_folder_session_without_an_embed_still_uses_course_launch():
    async def no_embed(method, path, params=None, data=None):
        assert method == "GET"
        if path == f"/api/v1/courses/{COURSE}/modules":
            return ([], {})
        if path == f"/api/v1/courses/{COURSE}/external_tools":
            return ([{"id": 4, "name": "Panopto"}], {})
        raise AssertionError(path)

    navigation = "https://canvas.upenn.edu/courses/123/external_tools/4?launch_type=course_navigation"
    obj, _, _ = client([
        lti_form(navigation),
        response(text='folderID="11111111-2222-3333-4444-555555555555"',
                 url="https://upenn.hosted.panopto.com/Panopto/Pages/Home.aspx"),
        session({"Urls": {"CaptionDownloadUrl": CAPTION}}),
        response(text=SRT, url=CAPTION),
    ])
    obj.tools.request.side_effect = no_embed
    result = run(obj.transcript(SID, course=COURSE))
    assert urls_of(obj)[0] == navigation
    assert "retrieve" not in urls_of(obj)[0]
    assert result["data"]["format"] == "srt"
    assert "canvas_item_title" not in result["data"]


def test_bad_identifiers_do_not_touch_the_network():
    obj, _, _ = client([])
    with pytest.raises(ValueError):
        run(obj.transcript("not-a-uuid"))
    with pytest.raises(ValueError):
        run(obj.transcript(SID, course=COURSE, assignment_id="../456"))
    obj.tools.session.ensure.assert_not_called()
    obj.context.request.fetch.assert_not_called()


def test_launch_still_stores_one_folder_and_blocks_view_events():
    obj, records, _ = client([
        lti_form("https://canvas.upenn.edu/courses/123/external_tools/4"),
        response(text='folderID="' + OTHER + '"', url="https://upenn.hosted.panopto.com/Panopto/Pages/Home.aspx"),
    ])
    obj.tools.request.side_effect = None
    obj.tools.request.return_value = ([{"id": 4, "name": "Panopto"}], {})
    run(obj.launch("123"))
    assert records["panopto_courses"]["123"]["folder_id"] == OTHER
    assert obj.context.request.fetch.await_args_list[1].kwargs["method"] == "POST"
    for endpoint in ("AddViewingEvent", "Heartbeat", "UpdateSession"):
        with pytest.raises(ValueError):
            run(obj.api(endpoint, {}))
    obj.context.request.post.assert_not_called()


def test_lectures_keep_canvas_map_when_the_folder_is_absent():
    obj, records, _ = client([])

    async def remember(course):
        records["panopto_courses"] = {str(course): {"folder_id": None}}

    obj.launch = AsyncMock(side_effect=remember)
    rows = [{"session_id": SID, "session_name": "Lecture eight", "canvas_item_title": "Week eight"}]
    with patch("src.penn_server.panopto.build_canvas_map", new=AsyncMock(return_value=rows)):
        result = run(obj.lectures(course=COURSE))
    assert result["data"]["folder_id"] is None
    assert result["data"]["lectures"] == [{"session_id": SID, "title": "Lecture eight"}]
    obj.context.request.post.assert_not_called()


def test_registered_transcript_tool_stays_compatible():
    from src.penn_server.panopto import register

    class MCP:
        def __init__(self):
            self.tools = {}

        def tool(self, **kwargs):
            def save(fn):
                self.tools[fn.__name__] = (fn, kwargs)
                return fn
            return save

    obj, _, _ = client([])
    mcp = MCP()
    register(obj.tools, mcp)
    assert set(mcp.tools) == {"list_panopto_lectures", "get_panopto_transcript", "get_panopto_progress"}
    fn, meta = mcp.tools["get_panopto_transcript"]
    signature = inspect.signature(fn)
    assert list(signature.parameters) == ["session_id", "course", "assignment_id"]
    assert signature.parameters["session_id"].default is inspect.Parameter.empty
    assert signature.parameters["course"].default is None
    assert meta["annotations"].readOnlyHint is True
    source = (ROOT / "src/penn_server/panopto.py").read_text()
    assert "completion_status" in source
    assert "/Panopto/Api/stats/viewing" in source
    assert "Captions unavailable or access denied" not in source
