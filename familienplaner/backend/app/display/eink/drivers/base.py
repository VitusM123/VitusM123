"""Port: EInkDriver – Hardware-Abstraktion für E-Ink-Panels."""
from typing import Protocol

from PIL import Image


class EInkDriver(Protocol):
    width: int
    height: int
    palette: list[tuple[int, int, int]]

    def display(self, image: Image.Image) -> None: ...
    def clear(self) -> None: ...
    def sleep(self) -> None: ...
