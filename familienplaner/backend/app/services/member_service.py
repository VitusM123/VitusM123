"""Familienmitglieder und Zuordnung Termin → Person.

Auflösung: EventMember (explizit) → Calendar.default_member_id (Fallback) → Regeln (später).
"""


class MemberService:
    def list_members(self) -> list:
        raise NotImplementedError

    def resolve_members(self, event) -> list[int]:
        raise NotImplementedError
