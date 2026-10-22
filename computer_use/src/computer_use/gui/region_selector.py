"""Simple region picker widget (drag on preview)."""

from __future__ import annotations

from computer_use.core.region import ScreenRegion

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QImage, QMouseEvent, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import QLabel

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class RegionSelectorWidget(QLabel):
        regionSelected = Signal(object)

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.setMinimumSize(320, 200)
            self._origin: tuple[int, int] | None = None
            self._current: tuple[int, int] | None = None
            self._scale = 1.0
            self._offset = (0, 0)
            self._source_size = (1, 1)
            self._pixmap: QPixmap | None = None
            self._selected: ScreenRegion | None = None

        def set_preview_image(self, image) -> None:
            """Accept PIL Image."""
            from PIL import Image

            if not isinstance(image, Image.Image):
                raise TypeError("expected PIL Image")
            rgb = image.convert("RGB")
            data = rgb.tobytes("raw", "RGB")
            qimg = QImage(
                data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888
            )
            self._source_size = (rgb.width, rgb.height)
            self._pixmap = QPixmap.fromImage(qimg)
            self._fit_pixmap()
            self.update()

        def _fit_pixmap(self) -> None:
            if not self._pixmap:
                return
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._scale = scaled.width() / self._pixmap.width()
            ox = (self.width() - scaled.width()) // 2
            oy = (self.height() - scaled.height()) // 2
            self._offset = (ox, oy)
            super().setPixmap(scaled)

        def resizeEvent(self, event) -> None:
            super().resizeEvent(event)
            self._fit_pixmap()

        def _to_source(self, x: int, y: int) -> tuple[int, int]:
            ox, oy = self._offset
            sx = int((x - ox) / self._scale) if self._scale else 0
            sy = int((y - oy) / self._scale) if self._scale else 0
            w, h = self._source_size
            sx = max(0, min(sx, w - 1))
            sy = max(0, min(sy, h - 1))
            return sx, sy

        def mousePressEvent(self, event: QMouseEvent) -> None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._origin = self._to_source(int(event.position().x()), int(event.position().y()))
                self._current = self._origin

        def mouseMoveEvent(self, event: QMouseEvent) -> None:
            if self._origin:
                self._current = self._to_source(int(event.position().x()), int(event.position().y()))
                self.update()

        def mouseReleaseEvent(self, event: QMouseEvent) -> None:
            if self._origin and self._current:
                x1, y1 = self._origin
                x2, y2 = self._current
                self._selected = ScreenRegion.from_drag(x1, y1, x2, y2)
                self.regionSelected.emit(self._selected)
            self._origin = None
            self._current = None
            self.update()

        def paintEvent(self, event) -> None:
            super().paintEvent(event)
            if not self._origin or not self._current or not self._pixmap:
                return
            painter = QPainter(self)
            pen = QPen(Qt.GlobalColor.red, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            ox, oy = self._offset
            x1 = int(self._origin[0] * self._scale) + ox
            y1 = int(self._origin[1] * self._scale) + oy
            x2 = int(self._current[0] * self._scale) + ox
            y2 = int(self._current[1] * self._scale) + oy
            painter.drawRect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
            painter.end()

        def selected_region(self) -> ScreenRegion | None:
            return self._selected

else:
    RegionSelectorWidget = None  # type: ignore[misc, assignment]
