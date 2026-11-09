"""Offline Panopto reference extraction and Canvas/dashboard reconciliation."""

import re
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import UUID


def nested_urls(url):
    """Yield decoded URLs, including Canvas's nested LTI URL parameter."""
    pending, seen = [unescape(url)], set()
    while pending and len(seen) < 20:
        value = pending.pop(0)
        if value in seen:
            continue
        seen.add(value)
        yield value
        decoded = unquote(value)
        if decoded != value:
            pending.append(decoded)
        pending.extend(parse_qs(urlsplit(value).query).get("url", []))


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.entries = []
        self.link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "iframe" and attrs.get("src"):
            self.entries.append([attrs["src"], attrs.get("title") or None])
        elif tag == "a" and attrs.get("href"):
            self.link = [attrs["href"], ""]
            self.entries.append(self.link)

    def handle_data(self, data):
        if self.link is not None:
            self.link[1] += data

    def handle_endtag(self, tag):
        if tag == "a":
            self.link = None


def references(html):
    parser = References()
    parser.feed(unescape(html or ""))
    return parser.entries


def extract_panopto_refs(html):
    result = []
    for url, name in references(html):
        for value in nested_urls(url):
            parsed = urlsplit(value)
            if parsed.hostname != "upenn.hosted.panopto.com":
                continue
            for key, values in parse_qs(parsed.query).items():
                if key.lower() not in ("custom_context_delivery", "id", "tid", "sid"):
                    continue
                for candidate in values:
                    try:
                        session_id = str(UUID(candidate))
                    except ValueError:
                        continue
                    row = {"session_id": session_id, "session_name": name.strip() if name else None}
                    if row not in result:
                        result.append(row)
    return result


async def canvas_content(tools, course):
    modules, _ = await tools.request("GET", f"/api/v1/courses/{course}/modules",
                                     {"include[]": "items", "per_page": 100})
    for module in modules:
        items = module.get("items")
        if items is None:  # Canvas omits inline items for large courses
            items, _ = await tools.request("GET", f"/api/v1/courses/{course}/modules/{module['id']}/items",
                                           {"per_page": 100})
        for item in items:
            kind = item.get("type")
            html = item.get("description") or item.get("body") or ""
            if kind == "Assignment":
                data, _ = await tools.request("GET", f"/api/v1/courses/{course}/assignments/{item['content_id']}")
                html += data.get("description") or ""
            elif kind == "Page":
                data, _ = await tools.request("GET", f"/api/v1/courses/{course}/pages/{item['page_url']}")
                html += data.get("body") or ""
            elif kind == "Quiz" and item.get("content_id"):
                data, _ = await tools.request("GET", f"/api/v1/courses/{course}/quizzes/{item['content_id']}")
                html += data.get("description") or ""
            elif kind == "Discussion" and item.get("content_id"):
                data, _ = await tools.request("GET", f"/api/v1/courses/{course}/discussion_topics/{item['content_id']}")
                html += data.get("message") or ""
            elif kind in ("ExternalUrl", "ExternalTool"):
                url = item.get("external_url") or item.get("url") or ""
                html += f'<a href="{escape(url, quote=True)}">{escape(item.get("title") or "")}</a>'
            yield module, item, html


async def find_lti_url(tools, course):
    async for _, _, html in canvas_content(tools, course):
        for url, _ in references(html):
            for value in nested_urls(url):
                parsed = urlsplit(value)
                if (parsed.scheme == "https" and parsed.netloc == "upenn.hosted.panopto.com"
                        and parsed.path.lower().startswith("/panopto/lti/")):
                    return value
    return None


def delivery_urls(html, session_id):
    """Panopto LTI URLs in Canvas HTML that deliver one session.

    Only the public LTI launch link is returned. Direct viewer links are not
    delivery context: Penn hides those sessions until Canvas launches them.
    """
    try:
        want = str(UUID(str(session_id)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("A Panopto UUID is required") from None
    found = []
    for url, name in references(html):
        for value in nested_urls(url):
            parsed = urlsplit(value)
            if (parsed.scheme != "https" or parsed.hostname != "upenn.hosted.panopto.com"
                    or not parsed.path.lower().startswith("/panopto/lti/")):
                continue
            matched = False
            for key, values in parse_qs(parsed.query).items():
                if key.lower() not in ("custom_context_delivery", "id", "tid", "sid"):
                    continue
                for candidate in values:
                    try:
                        matched = str(UUID(candidate)) == want
                    except ValueError:
                        continue
                    if matched:
                        break
                if matched:
                    break
            row = {"lti_url": value, "session_name": name.strip() if name and name.strip() else None}
            if matched and row not in found:
                found.append(row)
    return found


async def find_assignment_delivery(tools, course, assignment_id, session_id):
    data, _ = await tools.request(
        "GET", f"/api/v1/courses/{course}/assignments/{assignment_id}")
    if not isinstance(data, dict):
        raise RuntimeError("Canvas assignment could not be read")
    found = delivery_urls(data.get("description") or "", session_id)
    if not found:
        return None
    return {"course_id": str(course), "lti_url": found[0]["lti_url"],
            "session_name": found[0].get("session_name"),
            "canvas_item_title": data.get("name"),
            "canvas_item_url": data.get("html_url")}


async def find_session_delivery(tools, course, session_id):
    async for module, item, html in canvas_content(tools, course):
        found = delivery_urls(html, session_id)
        if not found:
            continue
        return {"course_id": str(course), "lti_url": found[0]["lti_url"],
                "session_name": found[0].get("session_name"),
                "canvas_module": module.get("name"),
                "canvas_item_title": item.get("title"),
                "canvas_item_url": item.get("html_url") or item.get("url")}
    return None


async def build_canvas_map(tools, course):
    rows, seen = [], set()
    async for module, item, html in canvas_content(tools, course):
        for ref in extract_panopto_refs(html):
            if ref["session_id"] in seen:
                continue
            seen.add(ref["session_id"])
            rows.append(dict(ref, canvas_module=module.get("name"),
                             canvas_item_title=item.get("title"),
                             canvas_item_url=item.get("html_url") or item.get("url")))
    return rows


def normalize_title(s):
    return " ".join(re.sub(r"[^\w\s]|_", " ", (s or "").lower()).split())


def completion_status(row, played):
    """completed = percent_completed 100 AND minutes delivered >= duration (0.1 min rounding tolerance)."""
    if not played:
        return "not played yet"
    minutes, duration, pct = row.get("minutes_delivered"), row.get("duration_minutes"), row.get("percent_completed")
    if pct is not None and float(str(pct).rstrip("%")) >= 100 and minutes is not None and duration and minutes >= duration - 0.1:
        return "completed"
    return "partially watched"


def match(canvas_rows, analytics_rows):
    lectures, used = [], set()
    for row in canvas_rows:
        index = next((i for i, a in enumerate(analytics_rows)
                      if a.get("session_id") and a["session_id"].lower() == row["session_id"].lower()), None)
        method = "session_id"
        if index is None:
            titles = {normalize_title(row.get(k)) for k in ("session_name", "canvas_item_title")} - {""}
            index = next((i for i, a in enumerate(analytics_rows)
                          if normalize_title(a.get("title")) in titles), None)
            method = "title" if index is not None else "none"
        if index is not None:
            used.add(index)
        lectures.append({k: row.get(k) for k in
                         ("session_id", "session_name", "canvas_module", "canvas_item_title")})
        hit = analytics_rows[index] if index is not None else {}
        lectures[-1].update({k: hit.get(k) for k in ("views", "minutes_delivered", "duration_minutes")})
        lectures[-1].update(percent_completed=hit.get("percent_completed")
                           if index is not None else None, match_method=method,
                           # Panopto omits never-played sessions from analytics.
                           status="played" if index is not None else "not played yet")
        lectures[-1]["completion_status"] = completion_status(lectures[-1], index is not None)
    summary = {}
    for label in ("completed", "partially watched", "not played yet"):
        rows = [f"{l.get('session_name') or l.get('canvas_item_title')} ({l.get('canvas_module')})"
                for l in lectures if l["completion_status"] == label]
        summary[label.replace(" ", "_")] = {"count": len(rows), "lectures": rows}
    summary["total_canvas_lectures"] = len(lectures)
    return {"summary": summary, "lectures": lectures,
            "unmatched_analytics": [a for i, a in enumerate(analytics_rows) if i not in used]}
