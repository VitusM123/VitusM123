"""Beispieldaten für einen ersten Eindruck – ohne Google, iCloud oder Veranstaltungsquellen.

    python -m app.tools.demo           # nur, wenn noch keine Familienmitglieder existieren
    python -m app.tools.demo --force   # trotzdem hinzufügen

Termine werden relativ zur aktuellen Woche angelegt, Veranstaltungen für die nächsten drei Wochen
rund um den Wohnort (Standard: München Marienplatz).
"""
import argparse
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.config import load_settings
from app.core.db import init_db
from app.core.timeutil import UTC, date_to_utc
from app.domain.models import Activity, ActivityCategory, ActivitySource, ActivitySourceType, FamilyMember
from app.schemas import CalendarCreate, EventCreate, MemberCreate, UserSettingsUpdate
from app.services.activity_service import fingerprint
from app.services.calendar_service import CalendarService
from app.services.member_service import MemberService
from app.services.settings_service import SettingsService

DEMO_HOME = ("Marienplatz, München", 48.1374, 11.5755)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="auch hinzufügen, wenn schon Daten vorhanden sind")
    args = parser.parse_args()

    settings = load_settings()
    engine = init_db(settings)
    tz = ZoneInfo(settings.locale.timezone)
    with Session(engine) as session:
        if session.exec(select(FamilyMember)).first() and not args.force:
            print("Es gibt bereits Familienmitglieder – Beispieldaten übersprungen (--force zum Erzwingen).")
            return

        members = MemberService(session)
        ids = {name: members.create(MemberCreate(name=name, color=color, avatar=avatar)).id
               for name, color, avatar in [("Mama", "#E4572E", "👩"), ("Papa", "#29335C", "👨"),
                                           ("Lena", "#F3A712", "👧"), ("Tim", "#669BBC", "👦")]}
        cal = CalendarService(session, settings)
        school = cal.create_local_calendar(CalendarCreate(name="Schule", color="#7FB069",
                                                          member_ids=[ids["Lena"]]))

        today = datetime.now(tz).date()
        monday = today - timedelta(days=today.weekday())

        def at(day: int, hh: int, mm: int = 0) -> str:
            return datetime.combine(monday + timedelta(days=day), time(hh, mm)).isoformat()

        def d(day: int) -> date:
            return monday + timedelta(days=day)

        def add(**kw) -> None:
            cal.create_event(EventCreate(**kw))

        add(title="Schwimmtraining", start=at(0, 16), end=at(0, 17, 30), rrule="FREQ=WEEKLY;BYDAY=MO,TH",
            member_ids=[ids["Tim"]], location="Hallenbad")
        add(title="Klavier", start=at(2, 15), end=at(2, 15, 45), rrule="FREQ=WEEKLY", member_ids=[ids["Lena"]])
        add(title="Yoga", start=at(1, 19), end=at(1, 20), rrule="FREQ=WEEKLY", member_ids=[ids["Mama"]])
        add(title="Müllabfuhr (Papier)", start=d(2), all_day=True, rrule="FREQ=WEEKLY;INTERVAL=2")
        add(title="Mathearbeit", start=d(1), all_day=True, calendar_id=school.id)
        add(title="Elternabend 4b", start=at(3, 19, 30), end=at(3, 21), calendar_id=school.id,
            member_ids=[ids["Mama"], ids["Papa"]])
        add(title="Zahnarzt", start=at(4, 9), end=at(4, 9, 30), member_ids=[ids["Tim"], ids["Mama"]])
        add(title="Teammeeting", start=at(4, 9, 15), end=at(4, 10, 30), member_ids=[ids["Papa"]])
        add(title="Oma & Opa zu Besuch", start=d(5), end=d(7), all_day=True)
        add(title="Fußballturnier", start=at(6, 10), end=at(6, 14), member_ids=[ids["Tim"], ids["Papa"]])
        add(title="Kindergeburtstag Paul", start=at(9, 15), end=at(9, 18), member_ids=[ids["Tim"]])
        add(title="Skikurs-Anmeldung", start=d(11), all_day=True, member_ids=[ids["Lena"], ids["Tim"]])

        prefs = SettingsService(session, settings)
        home = prefs.get().home
        if home.lat is None:
            prefs.update(UserSettingsUpdate(home={"address": DEMO_HOME[0], "lat": DEMO_HOME[1], "lon": DEMO_HOME[2]}))
            home = prefs.get().home

        source = ActivitySource(type=ActivitySourceType.ICAL, name="Beispiel-Veranstaltungen",
                                config={"demo": True, "url": "https://example.invalid/demo.ics"})
        session.add(source)
        session.flush()
        samples = [
            ("Tag der offenen Tür bei der Feuerwehr", 5, 10, 16, ActivityCategory.OPEN_DAY, "Feuerwache 5", 1.2),
            ("Hochschulinformationstag", 8, 9, 15, ActivityCategory.OPEN_DAY, "Technische Universität", 2.0),
            ("Ausbildungsmesse 2026", 12, 10, 17, ActivityCategory.FAIR, "Messegelände", 9.5),
            ("Vernissage: Licht & Schatten", 4, 19, 21, ActivityCategory.EXHIBITION, "Kunsthalle", 0.4),
            ("Flohmarkt im Schulhof", 6, 9, 14, ActivityCategory.MARKET, "Grundschule an der Isar", 3.1),
            ("Kinderkonzert: Die Zauberflöte", 13, 15, 16, ActivityCategory.CONCERT, "Prinzregententheater", 2.6),
            ("Museumsführung für Familien", 12, 14, 15, ActivityCategory.EXHIBITION, "Stadtmuseum", 0.3),
            ("Laternenbasteln für Kinder", 9, 16, 18, ActivityCategory.WORKSHOP, "Stadtbibliothek", 1.8),
            ("Dinosaurier-Ausstellung", 19, 10, 18, ActivityCategory.EXHIBITION, "Naturkundemuseum", 4.4),
        ]
        for title, offset, h1, h2, cat_, venue, km in samples:
            day = today + timedelta(days=offset)
            start = datetime.combine(day, time(h1), tzinfo=tz).astimezone(UTC)
            session.add(Activity(
                source_id=source.id, title=title, category=cat_, start=start,
                end=datetime.combine(day, time(h2), tzinfo=tz).astimezone(UTC),
                venue=venue, address=f"{venue}, München", lat=home.lat + km / 111 * 0.7,
                lon=home.lon + km / 111 * 0.7, description="Beispielveranstaltung (Demo-Daten).",
                fingerprint=fingerprint(title, start, venue, tz),
            ))
        session.add(Activity(source_id=source.id, title="Christkindlmarkt", category=ActivityCategory.MARKET,
                             start=date_to_utc(today + timedelta(days=3)), end=date_to_utc(today + timedelta(days=30)),
                             all_day=True, venue="Marienplatz", lat=home.lat, lon=home.lon,
                             fingerprint=fingerprint("Christkindlmarkt", date_to_utc(today), "Marienplatz", tz)))
        source.last_count = len(samples) + 1
        session.add(source)
        session.commit()
    print("Beispieldaten angelegt: 4 Familienmitglieder, 12 Termine, 10 Veranstaltungen.")


if __name__ == "__main__":
    main()
