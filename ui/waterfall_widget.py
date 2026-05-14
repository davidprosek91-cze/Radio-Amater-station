import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QPen, QFont
from PyQt6.QtCore import Qt, QRectF


class SMeterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dbm: float = -120.0
        self.setFixedSize(200, 30)

    def set_dbm(self, dbm: float):
        self._dbm = dbm
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(10, 10, 20))
        painter.setPen(QPen(QColor(60, 60, 80), 1))
        painter.drawRect(0, 0, w - 1, h - 1)
        norm = (self._dbm + 130) / 140.0
        norm = max(0, min(1, norm))
        fill_w = int((w - 4) * norm)
        if fill_w > 0:
            grad = QLinearGradient(0, 0, fill_w, 0)
            grad.setColorAt(0, QColor(0, 180, 0, 120))
            grad.setColorAt(0.5, QColor(180, 180, 0, 120))
            grad.setColorAt(0.8, QColor(200, 80, 0, 120))
            grad.setColorAt(1, QColor(200, 0, 0, 120))
            painter.fillRect(2, 2, fill_w, h - 4, grad)
        painter.setPen(QColor(0, 255, 100))
        font = QFont("Courier", 9)
        painter.setFont(font)
        s_units = self._dbm_to_s(self._dbm)
        painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, f"{self._dbm:.0f} dBm  {s_units}")
        painter.end()

    def _dbm_to_s(self, dbm: float) -> str:
        levels = [('S9+40', -33), ('S9+20', -53), ('S9+10', -63),
                  ('S9', -73), ('S8', -79), ('S7', -85), ('S6', -91),
                  ('S5', -97), ('S4', -103), ('S3', -109), ('S2', -115), ('S1', -121)]
        for label, val in levels:
            if dbm >= val:
                return label
        return "S0"


class BandPlanOverlay:
    def __init__(self):
        self._bands = []

    def set_bands(self, bands: list[tuple]):
        self._bands = bands

    def draw(self, painter: QPainter, w: int, h: int, center: float, span: float):
        if not self._bands:
            return
        lo = center - span / 2
        hi = center + span / 2
        painter.setFont(QFont("Sans", 7))
        for name, b_lo, b_hi, color in self._bands:
            if b_hi < lo or b_lo > hi:
                continue
            x1 = int(w * (b_lo - lo) / (hi - lo))
            x2 = int(w * (b_hi - lo) / (hi - lo))
            c = QColor(*color, 30)
            painter.fillRect(x1, 0, x2 - x1, h, c)
            painter.setPen(QPen(QColor(*color, 150), 1))
            painter.drawLine(x1, 0, x1, h)
            painter.drawText(x1 + 2, 10, name)


class WaterfallWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[np.ndarray] = []
        self._max_history = 512
        self._center_freq = 145.5e6
        self._span = 2.4e6
        self._min_db = -80
        self._max_db = 0
        self._band_overlay = BandPlanOverlay()
        self._band_data: list[tuple] = []
        self.setMinimumHeight(180)

    def set_freq_range(self, center: float, span: float):
        self._center_freq = center
        self._span = span

    def set_band_data(self, bands: list[tuple]):
        self._band_data = bands
        self._band_overlay.set_bands(bands)

    def push_fft(self, psd: np.ndarray):
        self._history.append(psd.copy())
        if len(self._history) > self._max_history:
            self._history.pop(0)
        self.update()

    def clear(self):
        self._history.clear()
        self.update()

    def paintEvent(self, event):
        if not self._history:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        rows = len(self._history)
        if rows == 0 or len(self._history[0]) == 0:
            painter.end()
            return
        col_w = w / len(self._history[0])
        row_h = h / rows
        for ri in range(rows):
            psd_normalized = (self._history[ri] - self._min_db) / (self._max_db - self._min_db)
            psd_normalized = np.clip(psd_normalized, 0, 1)
            for ci in range(0, len(psd_normalized), 2):
                val = psd_normalized[ci]
                color = self._spectrum_color(val)
                painter.fillRect(
                    int(ci * col_w), int(ri * row_h), int(col_w * 2 + 1), int(row_h + 1), color
                )
        self._band_overlay.draw(painter, w, h, self._center_freq, self._span)
        self._draw_overlay(painter, w, h)
        painter.end()

    def _spectrum_color(self, t: float) -> QColor:
        t = max(0, min(1, t))
        if t < 0.2:
            return QColor(0, 0, int(40 + t * 800))
        elif t < 0.4:
            return QColor(0, int(255 * (t - 0.2) * 5), 255)
        elif t < 0.6:
            return QColor(int(255 * (t - 0.4) * 5), 255, int(255 * (1 - (t - 0.4) * 5)))
        elif t < 0.8:
            return QColor(255, int(255 * (1 - (t - 0.6) * 5)), 0)
        else:
            return QColor(255, 0, 0)

    def _draw_overlay(self, painter: QPainter, w: int, h: int):
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        font = QFont("Sans", 8)
        painter.setFont(font)
        for i in range(9):
            x = int(w * i / 8)
            freq = self._center_freq - self._span / 2 + self._span * i / 8
            painter.setPen(QColor(80, 80, 100, 80))
            painter.drawLine(x, 0, x, h)
            painter.setPen(QColor(180, 180, 200))
            label = f"{freq / 1e6:.2f}"
            painter.drawText(x - 25, h - 16, 50, 14, Qt.AlignmentFlag.AlignCenter, label)


class SpectrumWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._psd = np.zeros(512)
        self._center_freq = 145.5e6
        self._span = 2.4e6
        self._min_db = -80
        self._max_db = 0
        self._peak_hold = np.full(512, -100.0)
        self._decay = 0.97
        self._band_overlay = BandPlanOverlay()
        self._band_data: list[tuple] = []
        self._avg_psd: Optional[np.ndarray] = None
        self._avg_alpha = 0.3
        self.setMinimumHeight(120)

    def set_freq_range(self, center: float, span: float):
        self._center_freq = center
        self._span = span

    def set_band_data(self, bands: list[tuple]):
        self._band_data = bands
        self._band_overlay.set_bands(bands)

    def update_psd(self, psd: np.ndarray):
        self._psd = psd
        if self._avg_psd is None:
            self._avg_psd = psd.copy()
        else:
            self._avg_psd = self._avg_psd * (1 - self._avg_alpha) + psd * self._avg_alpha
        if len(psd) == len(self._peak_hold):
            self._peak_hold = np.maximum(self._peak_hold * self._decay, psd)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(8, 8, 16))
        n = len(self._psd)
        if n == 0:
            painter.end()
            return

        self._band_overlay.draw(painter, w, h, self._center_freq, self._span)

        fill_path = []
        for i in range(n):
            x = int(w * i / (n - 1))
            norm = (self._psd[i] - self._min_db) / (self._max_db - self._min_db)
            norm = max(0.0, min(1.0, norm))
            y = int(h * (1 - norm))
            fill_path.append((x, y))

        gradient = QLinearGradient(0, h, 0, 0)
        gradient.setColorAt(0, QColor(0, 100, 200, 30))
        gradient.setColorAt(1, QColor(0, 200, 255, 120))
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(1, len(fill_path)):
            x1, y1 = fill_path[i - 1]
            x2, y2 = fill_path[i]
            painter.setPen(QPen(self._trace_color(self._psd[i]), 2))
            painter.drawLine(x1, y1, x2, y2)

        painter.setPen(QPen(QColor(0, 255, 100, 80), 1))
        for i, val in enumerate(self._peak_hold):
            x = int(w * i / (n - 1))
            norm = (val - self._min_db) / (self._max_db - self._min_db)
            norm = max(0.0, min(1.0, norm))
            y = int(h * (1 - norm))
            painter.drawPoint(x, y)

        self._draw_grid(painter, w, h)
        painter.end()

    def _trace_color(self, val: float) -> QColor:
        norm = (val - self._min_db) / (self._max_db - self._min_db)
        norm = max(0, min(1, norm))
        r = int(max(0, min(255, 512 * (norm - 0.5))))
        g = int(max(0, min(255, 512 * (0.5 - abs(norm - 0.5)))))
        b = int(max(0, min(255, 255 - 512 * (norm - 0.5))))
        return QColor(r, g, b, 220)

    def _draw_grid(self, painter: QPainter, w: int, h: int):
        painter.setPen(QPen(QColor(60, 60, 80, 100), 1))
        font = QFont("Sans", 8)
        painter.setFont(font)
        for i in range(9):
            x = int(w * i / 8)
            freq = self._center_freq - self._span / 2 + self._span * i / 8
            painter.setPen(QColor(50, 50, 70, 80))
            painter.drawLine(x, 0, x, h)
            painter.setPen(QColor(160, 160, 180))
            painter.drawText(x - 25, h - 16, 50, 14, Qt.AlignmentFlag.AlignCenter, f"{freq/1e6:.2f}")
        painter.setPen(QColor(160, 180, 200))
        painter.drawText(4, 14, f"{self._max_db} dB")
        painter.drawText(4, h - 6, f"{self._min_db} dB")
