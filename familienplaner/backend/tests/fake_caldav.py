"""Simulierter iCloud-CalDAV-Server für Tests (httpx.MockTransport)."""
import base64
import itertools
import re
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET

import httpx

D, C = "DAV:", "urn:ietf:params:xml:ns:caldav"
HOME_HOST = "p42-caldav.icloud.com"
HOME = "/1234/calendars/"
CALS = {
    "home": {"name": "Zuhause", "color": "#FF2968FF", "write": True, "comp": "VEVENT"},
    "work": {"name": "Arbeit (geteilt)", "color": "#1BADF8FF", "write": False, "comp": "VEVENT"},
    "tasks": {"name": "Erinnerungen", "color": "#CC73E1FF", "write": True, "comp": "VTODO"},
}


def ics(*vevents: str) -> str:
    body = "\r\n".join(vevents)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Apple Inc.//iCloud//EN\r\n{body}\r\nEND:VCALENDAR\r\n"


def vevent(uid: str, summary: str, start: str, end: str, *extra: str) -> str:
    lines = ["BEGIN:VEVENT", f"UID:{uid}", "DTSTAMP:20261101T120000Z", f"SUMMARY:{summary}", start, end,
             *extra, "END:VEVENT"]
    return "\r\n".join(lines)


class FakeCalDAV:
    def __init__(self, user: str = "anna@icloud.com", password: str = "abcd-efgh-ijkl-mnop") -> None:
        self.user, self.password = user, password
        self.seq = itertools.count(1)
        self.res: dict[str, dict[str, dict]] = {c: {} for c in CALS}
        self.tombstones: dict[str, dict[str, int]] = {c: {} for c in CALS}
        self.invalid_tokens = False
        self.rejected_tokens = 0
        self.no_sync_collection = False
        self.requests: list[tuple[str, str]] = []

    # Testhilfen
    def put(self, cal: str, name: str, data: str) -> str:
        n = next(self.seq)
        self.res[cal][name] = {"data": data, "etag": f'"e{n}"', "seq": n}
        self.tombstones[cal].pop(name, None)
        return name

    def delete(self, cal: str, name: str) -> None:
        del self.res[cal][name]
        self.tombstones[cal][name] = next(self.seq)

    def data(self, cal: str, name: str) -> str:
        return self.res[cal][name]["data"]

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    # HTTP
    def handle(self, req: httpx.Request) -> httpx.Response:
        path = unquote(req.url.path)
        self.requests.append((req.method, path))
        expected = "Basic " + base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        if req.headers.get("Authorization") != expected:
            return httpx.Response(401)
        if req.method == "PROPFIND":
            m = re.fullmatch(rf"{HOME}(\w+)/", path)
            if m and m.group(1) in CALS and req.headers.get("Depth") == "1":
                cal = m.group(1)
                out = [self._resp(f"{HOME}{cal}/{n}", f"<d:getetag>{r['etag']}</d:getetag>")
                       for n, r in self.res[cal].items()]
                return self._ms("".join(out))
            return self._propfind(req, path)
        m = re.fullmatch(rf"{HOME}(\w+)/(?:(.+\.ics))?", path)
        if not m or m.group(1) not in CALS:
            return httpx.Response(404)
        cal, name = m.group(1), m.group(2)
        if req.method == "REPORT":
            root = ET.fromstring(req.content)
            if root.tag == f"{{{D}}}sync-collection":
                if self.no_sync_collection:
                    return httpx.Response(501)
                return self._sync(cal, root.findtext(f"{{{D}}}sync-token") or "")
            return self._multiget(cal, [unquote(h.text) for h in root.findall(f"{{{D}}}href")])
        if req.method == "PUT":
            if not CALS[cal]["write"]:
                return httpx.Response(403)
            if req.headers.get("If-None-Match") == "*" and name in self.res[cal]:
                return httpx.Response(412)
            self.put(cal, name, req.content.decode())
            return httpx.Response(201, headers={"ETag": self.res[cal][name]["etag"]})
        if req.method == "DELETE":
            if name not in self.res[cal]:
                return httpx.Response(404)
            self.delete(cal, name)
            return httpx.Response(204)
        return httpx.Response(405)

    @staticmethod
    def _ms(responses: str, extra: str = "") -> httpx.Response:
        xml = f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="{C}" ' \
              f'xmlns:ical="http://apple.com/ns/ical/">{responses}{extra}</d:multistatus>'
        return httpx.Response(207, content=xml.encode(), headers={"Content-Type": "application/xml"})

    @staticmethod
    def _resp(href: str, props: str) -> str:
        return (f"<d:response><d:href>{href}</d:href><d:propstat><d:prop>{props}</d:prop>"
                "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>")

    def _propfind(self, req: httpx.Request, path: str) -> httpx.Response:
        if path == "/" and req.url.host == "caldav.icloud.com":
            return self._ms(self._resp("/", "<d:current-user-principal><d:href>/1234/principal/</d:href>"
                                            "</d:current-user-principal>"))
        if path == "/1234/principal/":
            home = f"https://{HOME_HOST}:443{HOME}"
            return self._ms(self._resp(path, f"<c:calendar-home-set><d:href>{home}</d:href></c:calendar-home-set>"))
        if path == HOME and req.url.host == HOME_HOST:
            out = [self._resp(HOME, "<d:resourcetype><d:collection/></d:resourcetype>")]
            for key, c in CALS.items():
                priv = "<d:privilege><d:read/></d:privilege>" + (
                    "<d:privilege><d:write/></d:privilege>" if c["write"] else "")
                out.append(self._resp(f"{HOME}{key}/", (
                    "<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>"
                    f"<d:displayname>{c['name']}</d:displayname><ical:calendar-color>{c['color']}</ical:calendar-color>"
                    "<c:supported-calendar-component-set>"
                    f'<c:comp name="{c["comp"]}"/></c:supported-calendar-component-set>'
                    f"<d:current-user-privilege-set>{priv}</d:current-user-privilege-set>")))
            out.append(self._resp(f"{HOME}inbox/", "<d:resourcetype><d:collection/></d:resourcetype>"))
            return self._ms("".join(out))
        return httpx.Response(404)

    def _sync(self, cal: str, token: str) -> httpx.Response:
        if token and self.invalid_tokens:
            self.rejected_tokens += 1
            return httpx.Response(403, content=b'<d:error xmlns:d="DAV:"><d:valid-sync-token/></d:error>')
        since = int(token.rsplit("/", 1)[-1]) if token else 0
        out = [self._resp(f"{HOME}{cal}/", "")] if since == 0 else []
        for name, r in self.res[cal].items():
            if r["seq"] > since:
                out.append(self._resp(f"{HOME}{cal}/{name}", f"<d:getetag>{r['etag']}</d:getetag>"))
        if since:
            for name, n in self.tombstones[cal].items():
                if n > since:
                    out.append(f"<d:response><d:href>{HOME}{cal}/{name}</d:href>"
                               "<d:status>HTTP/1.1 404 Not Found</d:status></d:response>")
        current = max([r["seq"] for r in self.res[cal].values()] + list(self.tombstones[cal].values()) + [since])
        return self._ms("".join(out), f"<d:sync-token>http://fake/sync/{current}</d:sync-token>")

    def _multiget(self, cal: str, hrefs: list[str]) -> httpx.Response:
        out = []
        for href in hrefs:
            name = urlparse(href).path.rsplit("/", 1)[-1]
            r = self.res[cal].get(name)
            if r:
                data = r["data"].replace("&", "&amp;").replace("<", "&lt;")
                props = f"<d:getetag>{r['etag']}</d:getetag><c:calendar-data>{data}</c:calendar-data>"
                out.append(self._resp(href, props))
        return self._ms("".join(out))
