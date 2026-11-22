"""Adapter: Waveshare-E-Ink-Panels (z. B. 13.3" Spectra 6, 7.5" S/W)."""


class WaveshareDriver:
    def __init__(self, model: str) -> None:
        self.model = model
        raise NotImplementedError
