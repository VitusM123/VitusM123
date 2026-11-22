"""Einordnung von Veranstaltungen in Kategorien anhand deutscher Schlüsselwörter."""
import re

from app.domain.models import ActivityCategory as C

# Reihenfolge ist wichtig: spezifische Kategorien zuerst
RULES: list[tuple[C, list[str]]] = [
    (C.OPEN_DAY, ["tag der offenen tür", "tage der offenen tür", "offene tür", "open house", "infotag",
                  "informationstag", "schnuppertag", "schnupperstudium", "hochschulinformationstag", "infoabend",
                  "kennenlerntag"]),
    (C.FAIR, ["messe", "expo", "ausbildungsbörse", "jobbörse", "fachausstellung", "verbrauchermesse"]),
    (C.MARKET, ["flohmarkt", "trödelmarkt", "weihnachtsmarkt", "adventsmarkt", "bauernmarkt", "kunsthandwerkermarkt",
                "wochenmarkt", "basar", "christkindlmarkt", "markt"]),
    (C.EXHIBITION, ["ausstellung", "vernissage", "museum", "galerie", "sonderschau", "finissage"]),
    (C.WORKSHOP, ["workshop", "kurs", "seminar", "mitmach", "basteln", "werkstatt"]),
    (C.CONCERT, ["konzert", "orchester", "chor", "live-musik", "livemusik", "open air", "jazz"]),
    (C.THEATER, ["theater", "musical", "kabarett", "comedy", "puppenspiel", "oper", "lesung", "zirkus"]),
    (C.SPORTS, ["lauf", "marathon", "turnier", "radtour", "wanderung", "sportfest", "spieltag"]),
    (C.FESTIVAL, ["festival", "stadtfest", "volksfest", "kirmes", "kerwa", "dorffest", "sommerfest", "fest"]),
    (C.KIDS, ["kinder", "familie", "familien", "kids", "jugend", "ferienprogramm"]),
]

# Kategorien von Ticketmaster/iCal (englisch/deutsch) → eigene Kategorien
HINTS = {
    "music": C.CONCERT, "musik": C.CONCERT, "konzert": C.CONCERT, "sports": C.SPORTS, "sport": C.SPORTS,
    "arts & theatre": C.THEATER, "theater": C.THEATER, "family": C.KIDS, "familie": C.KIDS,
    "exhibition": C.EXHIBITION, "ausstellung": C.EXHIBITION, "fair": C.FAIR, "messe": C.FAIR,
    "market": C.MARKET, "markt": C.MARKET, "festival": C.FESTIVAL, "workshop": C.WORKSHOP,
}


def _contains(text: str, keyword: str) -> bool:
    """Wort oder Teil eines zusammengesetzten Worts am Anfang/Ende („Marktplatz“, „Ausbildungsmesse“)."""
    kw = re.escape(keyword)
    return re.search(rf"(?<![a-zäöüß]){kw}|{kw}(?![a-zäöüß])", text) is not None


def categorize(title: str, description: str | None = None, hints: list[str] | None = None,
               default: C | None = None) -> C:
    title_l = title.lower()
    # Titel zählt mehr als die Beschreibung
    for text in (title_l, f"{title_l} {(description or '').lower()[:500]}"):
        for category, keywords in RULES:
            if any(_contains(text, k) for k in keywords):
                return category
    for hint in hints or []:
        mapped = HINTS.get(hint.strip().lower())
        if mapped:
            return mapped
    return default or C.OTHER
