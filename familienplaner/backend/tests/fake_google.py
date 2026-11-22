"""Simulierter Google-Calendar-Server für Tests (httpx.MockTransport)."""
import base64
import hashlib
import itertools
import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote

import httpx

PAGE_SIZE = 2   # klein, damit Paging getestet wird


class FakeGoogle:
    def __init__(self) -> None:
        self.seq = itertools.count(1)
        self.calendars: dict[str, dict] = {}
        self.events: dict[str, dict[str, dict]] = {}
        self.access_tokens: set[str] = set()
        self.refresh_tokens: set[str] = {"refresh-1"}
        self.codes: dict[str, str] = {}          # code -> code_challenge
        self.expired_sync_tokens = False
        self.requests: list[tuple[str, str]] = []
        self.token_counter = itertools.count(1)

    # --- Testhilfen -------------------------------------------------------------------------
    def add_calendar(self, cal_id: str, summary: str, role: str = "owner", primary: bool = False,
                     color: str = "#9fc6e7") -> None:
        self.calendars[cal_id] = {"id": cal_id, "summary": summary, "accessRole": role, "primary": primary,
                                  "backgroundColor": color, "selected": True, "timeZone": "Europe/Berlin"}
        self.events[cal_id] = {}

    def put_event(self, cal_id: str, item: dict) -> dict:
        item = dict(item)
        item.setdefault("status", "confirmed")
        n = next(self.seq)
        item["etag"] = f'"{n}"'
        item["updated"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        item["_seq"] = n
        self.events[cal_id][item["id"]] = item
        return item

    def remove_event(self, cal_id: str, event_id: str) -> None:
        item = self.events[cal_id][event_id]
        tomb = {"id": event_id, "status": "cancelled"}
        for key in ("recurringEventId", "originalStartTime"):
            if key in item:
                tomb[key] = item[key]
        self.put_event(cal_id, tomb)

    def authorize(self, code: str, challenge: str) -> None:
        self.codes[code] = challenge

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    # --- HTTP -------------------------------------------------------------------------------
    def handle(self, request: httpx.Request) -> httpx.Response:
        path = unquote(request.url.path)
        self.requests.append((request.method, path))
        if request.url.host == "oauth2.googleapis.com":
            return self._token(request)
        auth = request.headers.get("Authorization", "")
        if auth.removeprefix("Bearer ") not in self.access_tokens:
            return httpx.Response(401, json={"error": {"code": 401}})
        if path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(200, json={"items": list(self.calendars.values())})
        m = re.fullmatch(r"/calendar/v3/calendars/([^/]+)/events(?:/([^/]+))?", path)
        if not m:
            return httpx.Response(404)
        cal_id, event_id = m.group(1), m.group(2)
        if cal_id not in self.events:
            return httpx.Response(404)
        if request.method == "GET":
            return self._list(cal_id, request)
        if request.method == "POST":
            body = json.loads(request.content)
            body["id"] = f"g{next(self.seq)}"
            return httpx.Response(200, json=self._public(self.put_event(cal_id, body)))
        if request.method == "PUT":
            body = json.loads(request.content)
            existing = self.events[cal_id].get(event_id)
            master_id = event_id.rsplit("_", 1)[0] if "_" in event_id else None
            if existing is None and not (master_id and master_id in self.events[cal_id]):
                return httpx.Response(404)
            body["id"] = event_id
            return httpx.Response(200, json=self._public(self.put_event(cal_id, body)))
        if request.method == "DELETE":
            existing = self.events[cal_id].get(event_id)
            if existing is None:
                if "_" in event_id and event_id.rsplit("_", 1)[0] in self.events[cal_id]:
                    self.put_event(cal_id, {"id": event_id, "status": "cancelled",
                                            "recurringEventId": event_id.rsplit("_", 1)[0]})
                    return httpx.Response(204)
                return httpx.Response(404)
            if existing.get("status") == "cancelled":
                return httpx.Response(410)
            self.remove_event(cal_id, event_id)
            return httpx.Response(204)
        return httpx.Response(405)

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if form.get("grant_type") == "authorization_code":
            challenge = self.codes.pop(form.get("code", ""), None)
            computed = base64.urlsafe_b64encode(
                hashlib.sha256(form.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode()
            if challenge is None or challenge != computed:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json=self._issue(refresh="refresh-1"))
        if form.get("grant_type") == "refresh_token":
            if form.get("refresh_token") not in self.refresh_tokens:
                return httpx.Response(400, json={"error": "invalid_grant",
                                                 "error_description": "Token has been expired or revoked."})
            return httpx.Response(200, json=self._issue())
        return httpx.Response(400, json={"error": "unsupported_grant_type"})

    def _issue(self, refresh: str | None = None) -> dict:
        token = f"access-{next(self.token_counter)}"
        self.access_tokens.add(token)
        data = {"access_token": token, "expires_in": 3599, "scope": "calendar", "token_type": "Bearer"}
        if refresh:
            data["refresh_token"] = refresh
        return data

    @staticmethod
    def _public(item: dict) -> dict:
        return {k: v for k, v in item.items() if not k.startswith("_")}

    def _list(self, cal_id: str, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        sync_token = params.get("syncToken")
        if sync_token and self.expired_sync_tokens:
            return httpx.Response(410, json={"error": {"code": 410, "message": "Sync token is no longer valid"}})
        since = int(sync_token.split("-")[-1]) if sync_token else 0
        items = sorted(self.events[cal_id].values(), key=lambda e: e["_seq"])
        if sync_token:
            items = [e for e in items if e["_seq"] > since]
        else:
            items = [e for e in items if e.get("status") != "cancelled" or "recurringEventId" in e]
        start = int(params.get("pageToken", "0"))
        page = items[start:start + PAGE_SIZE]
        data: dict = {"items": [self._public(e) for e in page], "timeZone": "Europe/Berlin"}
        if start + PAGE_SIZE < len(items):
            data["nextPageToken"] = str(start + PAGE_SIZE)
        else:
            current = max([e["_seq"] for e in self.events[cal_id].values()] + [since])
            data["nextSyncToken"] = f"tok-{current}"
        return httpx.Response(200, json=data)
