"""Display-Steuerung: Bildschirm an/aus, Helligkeit, Nachtmodus.

Mit ``display.backlight_path`` (z. B. ``/sys/class/backlight/10-0045``) wird die Hardware-
Hintergrundbeleuchtung geschaltet. Ohne Pfad wird nur der Zustand per WebSocket verteilt.
Das Frontend legt dann eine schwarze Fläche über die Anzeige (funktioniert mit jedem HDMI-Display).

Der Nachtmodus schaltet nur an den Übergängen (z. B. 22:30 aus, 06:30 an). Ein manuelles
Aufwecken per Touch bleibt also bis zum nächsten Übergang bestehen.
"""
import logging
from datetime import datetime
from pathlib import Path

from app.config import NightMode
from app.core.timeutil import in_time_range, parse_hhmm
from app.schemas import DisplayState

log = logging.getLogger(__name__)


class DisplayService:
    def __init__(self, backlight_path: Path | None) -> None:
        self.backlight_path = backlight_path if backlight_path and backlight_path.is_dir() else None
        if backlight_path and not self.backlight_path:
            log.warning("Backlight-Pfad %s nicht gefunden – nur Software-Abdunklung", backlight_path)
        self.screen_on = True
        self.brightness = 100
        self.night_active = False
        self._last_night: bool | None = None

    def state(self) -> DisplayState:
        return DisplayState(
            screen_on=self.screen_on, brightness=self.brightness, night_active=self.night_active,
            hardware_backlight=self.backlight_path is not None,
        )

    def set(self, screen_on: bool | None = None, brightness: int | None = None) -> DisplayState:
        if screen_on is not None:
            self.screen_on = screen_on
        if brightness is not None:
            self.brightness = max(0, min(100, brightness))
        self._apply_hardware()
        return self.state()

    def tick(self, now_local: datetime, night: NightMode) -> bool:
        """Nachtmodus prüfen. Liefert True, wenn sich der Zustand geändert hat."""
        is_night = night.enabled and in_time_range(now_local.time(), parse_hhmm(night.off), parse_hhmm(night.on))
        if is_night == self._last_night:
            return False
        first_run = self._last_night is None
        self._last_night = is_night
        self.night_active = is_night
        if first_run and not is_night:
            return False
        self.set(screen_on=not is_night)
        return True

    def _apply_hardware(self) -> None:
        if not self.backlight_path:
            return
        try:
            max_b = int((self.backlight_path / "max_brightness").read_text().strip())
            (self.backlight_path / "brightness").write_text(str(round(max_b * self.brightness / 100)))
            (self.backlight_path / "bl_power").write_text("0" if self.screen_on else "1")
        except (OSError, ValueError) as exc:
            log.warning("Backlight konnte nicht gesetzt werden: %s", exc)
