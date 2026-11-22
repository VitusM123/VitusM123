"""Familienmitglieder (CRUD, Reihenfolge)."""
from sqlmodel import Session, func, select

from app.domain.models import CalendarMember, EventMember, FamilyMember
from app.schemas import MemberCreate, MemberUpdate
from app.services.errors import NotFoundError


class MemberService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_members(self) -> list[FamilyMember]:
        return list(self.session.exec(select(FamilyMember).order_by(FamilyMember.sort_order, FamilyMember.id)))

    def get(self, member_id: int) -> FamilyMember:
        member = self.session.get(FamilyMember, member_id)
        if member is None:
            raise NotFoundError(f"Familienmitglied {member_id} nicht gefunden")
        return member

    def create(self, data: MemberCreate) -> FamilyMember:
        sort_order = data.sort_order
        if sort_order is None:
            current_max = self.session.exec(select(func.max(FamilyMember.sort_order))).one()
            sort_order = (current_max if current_max is not None else -1) + 1
        member = FamilyMember(name=data.name.strip(), color=data.color, avatar=data.avatar, sort_order=sort_order)
        self.session.add(member)
        self.session.commit()
        self.session.refresh(member)
        return member

    def update(self, member_id: int, data: MemberUpdate) -> FamilyMember:
        member = self.get(member_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            if key in ("name", "color", "sort_order") and value is None:
                continue  # Pflichtfelder nicht leeren
            setattr(member, key, value.strip() if key == "name" else value)
        self.session.add(member)
        self.session.commit()
        self.session.refresh(member)
        return member

    def reorder(self, member_ids: list[int]) -> list[FamilyMember]:
        members = {m.id: m for m in self.list_members()}
        for unknown in set(member_ids) - members.keys():
            raise NotFoundError(f"Familienmitglied {unknown} nicht gefunden")
        for index, member_id in enumerate(member_ids):
            members[member_id].sort_order = index
            self.session.add(members[member_id])
        self.session.commit()
        return self.list_members()

    def delete(self, member_id: int) -> None:
        member = self.get(member_id)
        for link in self.session.exec(select(EventMember).where(EventMember.member_id == member_id)):
            self.session.delete(link)
        for link in self.session.exec(select(CalendarMember).where(CalendarMember.member_id == member_id)):
            self.session.delete(link)
        self.session.delete(member)
        self.session.commit()

    def ensure_exist(self, member_ids: list[int]) -> None:
        if not member_ids:
            return
        found = set(self.session.exec(select(FamilyMember.id).where(FamilyMember.id.in_(member_ids))))
        missing = set(member_ids) - found
        if missing:
            raise NotFoundError(f"Familienmitglied(er) nicht gefunden: {sorted(missing)}")
