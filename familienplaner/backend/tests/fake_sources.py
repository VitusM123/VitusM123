"""Simulierte Veranstaltungsquellen und Nominatim (httpx.MockTransport)."""
import json

import httpx

CITY_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Stadt//DE
BEGIN:VEVENT
UID:tdot-1
SUMMARY:Tag der offenen Tür bei der Feuerwehr
DTSTART;TZID=Europe/Berlin:20261128T100000
DTEND;TZID=Europe/Berlin:20261128T160000
LOCATION:Feuerwache Nord, Hauptstraße 1, 80331 München
URL:https://stadt.example/tdot
DESCRIPTION:Fahrzeugschau und Mitmachaktionen für Kinder
END:VEVENT
BEGIN:VEVENT
UID:wm-1
SUMMARY:Weihnachtsmarkt am Rathaus
DTSTART;VALUE=DATE:20261127
DTEND;VALUE=DATE:20261224
LOCATION:Marienplatz, München
END:VEVENT
BEGIN:VEVENT
UID:fuehrung
SUMMARY:Museumsführung für Familien
DTSTART;TZID=Europe/Berlin:20261128T140000
DTEND;TZID=Europe/Berlin:20261128T153000
RRULE:FREQ=WEEKLY;BYDAY=SA;COUNT=4
GEO:48.1405;11.5800
LOCATION:Stadtmuseum
END:VEVENT
BEGIN:VEVENT
UID:hh
SUMMARY:Messe Hamburg
DTSTART;TZID=Europe/Berlin:20261129T090000
DTEND;TZID=Europe/Berlin:20261129T180000
LOCATION:Messeplatz 1, Hamburg
END:VEVENT
BEGIN:VEVENT
UID:abgesagt
SUMMARY:Abgesagtes Konzert
STATUS:CANCELLED
DTSTART;TZID=Europe/Berlin:20261130T190000
END:VEVENT
END:VCALENDAR
"""

MUSEUM_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:ev="http://purl.org/rss/1.0/modules/event/"><channel><title>Museum</title>
<item><title>Vernissage: Licht &amp; Schatten – 05.12.2026, 19 Uhr</title>
  <link>https://museum.example/vernissage</link><description>&lt;p&gt;Eröffnung der Ausstellung&lt;/p&gt;</description>
  <ev:location>Kunsthalle, Theatinerstraße 8, München</ev:location></item>
<item><title>Tag der offenen Tür bei der Feuerwehr</title><link>https://museum.example/dup</link>
  <ev:startdate>2026-11-28T10:00:00+01:00</ev:startdate><ev:location>Feuerwache Nord</ev:location></item>
<item><title>Newsletter abonnieren</title><link>https://museum.example/nl</link></item>
</channel></rss>"""

SCRAPE_HTML = """<html><body><div class="list">
<article class="ev"><h3>Flohmarkt im Schulhof</h3><span class="when">Sa, 5. Dezember 2026, 9:00 Uhr</span>
  <a href="/termine/floh">mehr</a><span class="ort">Grundschule Au, München</span></article>
<article class="ev"><h3>Laternenbasteln</h3><span class="when">03.12.</span><a href="/termine/later">mehr</a></article>
<article class="ev"><h3>Ohne Datum</h3><span class="when">demnächst</span></article>
</div></body></html>"""

TICKETMASTER = {
    "_embedded": {"events": [{
        "id": "tm1", "name": "Kinderkonzert: Die Zauberflöte", "url": "https://tm.example/tm1",
        "dates": {"start": {"localDate": "2026-12-06", "localTime": "15:00:00", "dateTime": "2026-12-06T14:00:00Z"}},
        "classifications": [{"family": True, "segment": {"name": "Music"}, "genre": {"name": "Classical"}}],
        "images": [{"url": "https://img/s.jpg", "width": 100}, {"url": "https://img/m.jpg", "width": 640}],
        "_embedded": {"venues": [{"name": "Prinzregententheater", "postalCode": "81675",
                                  "city": {"name": "München"}, "address": {"line1": "Prinzregentenplatz 12"},
                                  "location": {"latitude": "48.1395", "longitude": "11.6052"}}]},
    }]},
    "page": {"size": 100, "totalElements": 1, "totalPages": 1, "number": 0},
}

GEO = {
    "hauptstraße 1": (48.1400, 11.5760), "marienplatz": (48.1374, 11.5755), "hamburg": (53.5511, 9.9937),
    "theatinerstraße": (48.1418, 11.5770), "grundschule au": (48.1280, 11.5850), "feuerwache nord": (48.1400, 11.5760),
    "augsburg": (48.3705, 10.8978),
}


class FakeSources:
    def __init__(self) -> None:
        self.ics = CITY_ICS
        self.requests: list[httpx.Request] = []

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        url = str(req.url)
        if req.url.host == "nominatim.openstreetmap.org":
            q = req.url.params.get("q", "").lower()
            for key, (lat, lon) in GEO.items():
                if key in q:
                    return httpx.Response(200, json=[{"lat": str(lat), "lon": str(lon)}])
            return httpx.Response(200, json=[])
        if url == "https://stadt.example/events.ics":
            return httpx.Response(200, text=self.ics)
        if url == "https://museum.example/feed.rss":
            return httpx.Response(200, text=MUSEUM_RSS)
        if url == "https://verein.example/termine":
            return httpx.Response(200, text=SCRAPE_HTML)
        if req.url.host == "app.ticketmaster.com":
            if req.url.params.get("apikey") != "tm-secret-key":
                return httpx.Response(401, json={"fault": "invalid key"})
            return httpx.Response(200, content=json.dumps(TICKETMASTER))
        return httpx.Response(404)
