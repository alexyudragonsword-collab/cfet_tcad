"""Small shared GUI helpers."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel


class ElidedLabel(QLabel):
    """A QLabel that middle-elides its text instead of demanding the
    full text width.

    A plain QLabel's (minimum) size hint equals the text width, so a
    long path shown in one both inflates the initial splitter layout
    and blocks the pane from being dragged narrower.  This label paints
    ``C:\\Users\\…\\configs`` style elision and keeps the full text in
    the tooltip.
    """

    def setText(self, text: str) -> None:  # noqa: N802 - Qt override
        super().setText(text)
        self.setToolTip(text)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(40, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(160, super().sizeHint().height())

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        rect = self.contentsRect()
        elided = self.fontMetrics().elidedText(self.text(), Qt.ElideMiddle,
                                               rect.width())
        painter.drawText(rect, self.alignment() | Qt.AlignVCenter, elided)


def fit_to_screen(widget, width: int, height: int) -> None:
    """Resize ``widget`` to the requested size, clamped to 90% of the
    available screen (fixed dialog sizes overflow small displays)."""
    screen = widget.screen()
    if screen is not None:
        avail = screen.availableGeometry()
        width = min(width, int(avail.width() * 0.9))
        height = min(height, int(avail.height() * 0.9))
    widget.resize(width, height)
