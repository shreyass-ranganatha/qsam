from qgis.core import QgsProject

from PyQt5.QtWidgets import QDockWidget, QComboBox, QHBoxLayout, QVBoxLayout, QLabel, QWidget, QMessageBox
from PyQt5.QtGui import QColor, QPalette, QKeyEvent
from PyQt5.QtCore import Qt, pyqtSignal


__all__ = ["QSamPanel"]


class Color(QWidget):
    def __init__(self, color):
        super().__init__()
        self.setAutoFillBackground(True)

        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(color))
        self.setPalette(palette)


class RastersWidget(QWidget):
    available_rasters = pyqtSignal(list)
    selected_raster_index = pyqtSignal(int)

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self._init_ui()

        # signals
        QgsProject.instance().layersAdded.connect(self.load_raster_layers)
        QgsProject.instance().layersRemoved.connect(self.load_raster_layers)

        self.combo_rasters.currentIndexChanged.connect(self.selected_raster_index.emit)

        self.load_raster_layers()

    def _init_ui(self):
        # widgets
        self.label = QLabel(text="Select Raster")
        self.combo_rasters = QComboBox()

        # layouts
        ly_m = QHBoxLayout(self)
        ly_m.addWidget(self.label, stretch=.5)
        ly_m.addWidget(self.combo_rasters, stretch=1)
        self.setLayout(ly_m)

    def load_raster_layers(self):
        self.combo_rasters.clear()

        rs = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() != 1:
                continue

            rs.append(layer)

        self.combo_rasters.addItems([l.name() for l in rs])
        self.available_rasters.emit(rs)


class QSamPanel(QDockWidget):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.setMinimumWidth(280)
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)

        self._init_ui()

    def _init_ui(self):
        wdg_m = QWidget()

        self.widget_rasters = RastersWidget(self)

        ly_m = QVBoxLayout(wdg_m)
        ly_m.addWidget(self.widget_rasters, stretch=.2)
        # ly_m.addWidget(Color("blue"), stretch=1)
        # ly_m.addWidget(Color("yellow"), stretch=1)
        wdg_m.setLayout(ly_m)

        self.setWidget(wdg_m)
