"""E-Ink-Renderer: Screenshot der /#/eink-Route → Quantisierung/Dithering → Treiber.

Zeichnet nur neu, wenn sich der Bild-Hash geändert hat (schont das Panel).
"""


class EInkRenderer:
    async def render_once(self) -> bool:
        """Liefert True, wenn das Panel aktualisiert wurde."""
        raise NotImplementedError

    async def run_forever(self) -> None:
        raise NotImplementedError
