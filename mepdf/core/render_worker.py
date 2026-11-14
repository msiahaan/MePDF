"""Background QRunnable workers for non-blocking page and thumbnail rendering."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtGui import QImage

from mepdf.core.mupdf_engine import MuPDFEngine


class RenderSignals(QObject):
    """Signals emitted when an asynchronous PDF page render finishes."""

    rendered = Signal(int, float, int, QImage)  # page_index, zoom, token, image


class PageRenderWorker(QRunnable):
    """Renders a single PDF page in the global QThreadPool."""

    def __init__(
        self,
        pdf_bytes: bytes,
        page_index: int,
        zoom: float,
        token: int = 0,
        dpr: float = 1.0,
    ) -> None:
        super().__init__()
        self.pdf_bytes = pdf_bytes
        self.page_index = page_index
        self.zoom = zoom
        self.token = token
        self.dpr = dpr
        self.signals = RenderSignals()

    def run(self) -> None:
        try:
            img = MuPDFEngine.render_page(
                self.pdf_bytes,
                self.page_index,
                zoom=self.zoom,
                dpr=self.dpr,
            )
            self.signals.rendered.emit(self.page_index, self.zoom, self.token, img)
        except Exception:
            pass
