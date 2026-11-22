"""Zwei-Wege-Synchronisation lokaler Termine mit externen Kalendern.

Ablauf je Kalender: Pull (Delta via sync_token) → Upsert/Soft-Delete → Push der Outbox
(Events mit pending_push=True) → Event-Bus "events.changed".
Konfliktregel (MVP): last write wins (updated/ETag), bei Gleichstand gewinnt Remote.
"""


class SyncService:
    async def sync_all(self) -> None:
        raise NotImplementedError

    async def sync_account(self, account_id: int) -> None:
        raise NotImplementedError

    async def refresh_calendar_list(self, account_id: int) -> None:
        raise NotImplementedError
