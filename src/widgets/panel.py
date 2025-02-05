from qgis.core import QgsProject

import torch

from PyQt5.QtWidgets import (
    QDockWidget,
    QComboBox,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QWidget,
    QMessageBox,
    QGroupBox,
    QPushButton,
    QCheckBox,
    QSizePolicy,
    QStyle
)
from PyQt5.QtGui import QColor, QPalette, QKeyEvent, QIcon
from PyQt5.QtCore import Qt, pyqtSignal


__all__ = ["QSamPanel"]


class Color(QWidget):
    def __init__(self, color):
        super().__init__()
        self.setAutoFillBackground(True)

        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(color))
        self.setPalette(palette)


class LayersWidget(QGroupBox):
    available_rasters = pyqtSignal(list)
    available_vectors = pyqtSignal(list)

    selected_raster_index = pyqtSignal(int)
    selected_vector_index = pyqtSignal(int)

    create_vector_layer = pyqtSignal()

    def __init__(self, parent):
        super().__init__(title="Layers", parent=parent)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.init_ui()

    def __setup_rasters(self, ):
        # widgets
        self.r_label = QLabel(text="Raster")
        self.r_combo_rasters = QComboBox()
        self.r_combo_rasters.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        l = QHBoxLayout()
        l.addWidget(self.r_label)#, stretch=.8)
        l.addWidget(self.r_combo_rasters)#, stretch=1)

        return l

    def __setup_vectors(self, ):
        # widgets
        self.v_label = QLabel(text="Vector")

        self.v_combo_rasters = QComboBox()
        self.v_combo_rasters.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.v_action = QPushButton("+")
        self.v_action.setFixedWidth(30)
        self.v_action.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)

        l = QHBoxLayout()
        l.addWidget(self.v_label)
        l.addWidget(self.v_combo_rasters)
        l.addWidget(self.v_action)

        return l

    def init_ui(self):
        l_m = QVBoxLayout(self)
        l_m.addLayout(self.__setup_rasters())
        l_m.addLayout(self.__setup_vectors())

        self.setLayout(l_m)

    def setup_ui(self):
        #
        QgsProject.instance().layersAdded.connect(self.load_raster_layers)
        QgsProject.instance().layersAdded.connect(self.load_vector_layers)

        QgsProject.instance().layersRemoved.connect(self.load_raster_layers)
        QgsProject.instance().layersRemoved.connect(self.load_vector_layers)

        self.r_combo_rasters.currentIndexChanged.connect(self.selected_raster_index.emit)
        self.v_combo_rasters.currentIndexChanged.connect(self.selected_vector_index.emit)

        self.v_action.clicked.connect(lambda: self.create_vector_layer.emit())

        self.load_raster_layers()
        self.load_vector_layers()

    def load_raster_layers(self):
        self.r_combo_rasters.clear()

        self.rs = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() != 1:
                continue

            self.rs.append(layer)

        self.available_rasters.emit(self.rs)
        self.r_combo_rasters.addItems([l.name() for l in self.rs])

    def load_vector_layers(self):
        self.v_combo_rasters.clear()

        self.rs = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() != 0:
                continue

            self.rs.append(layer)

        self.available_vectors.emit(self.rs)
        self.v_combo_rasters.addItems([l.name() for l in self.rs])


class SamWidget(QGroupBox):
    selected_device = pyqtSignal(str)
    streaming_enabled = pyqtSignal(bool)

    def __init__(self, parent):
        super().__init__(title="SAM", parent=parent)

        # self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.init_ui()

    def __setup_model_path(self):
        self.model_path = QComboBox()
        self.model_path.setEditable(True)
        self.model_path.addItems([
            "facebook/sam-vit-base",
            "facebook/sam-vit-large",
            "facebook/sam-vit-huge"
        ])

        devices = [
            "cpu",
            "cuda" if torch.cuda.is_available() else None,
            "mps" if torch.backends.mps.is_available() else None
        ]

        # devices
        self.device = QComboBox()
        self.device.addItems([d for d in devices if d is not None])
        self.device.setCurrentIndex(0)

        self.device.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.device.currentTextChanged.connect(self.selected_device.emit)

        l = QHBoxLayout()
        l.addWidget(QLabel(text="Model"), stretch=.8)
        l.addWidget(self.model_path, stretch=1)
        l.addWidget(self.device, stretch=.2)

        return l

    def __setup_reload(self):
        self.reload = QPushButton(text="Reload")
        self.reload.setEnabled(False)
        # self.reload.clicked.connect(self.reload_model)

        l = QHBoxLayout()
        l.setAlignment(Qt.AlignRight)

        l.addWidget(self.reload)

        return l

    def __setup_stream(self):
        self.stream = QCheckBox(text="Streaming Enabled")
        self.stream.setChecked(True)

        self.stream.stateChanged.connect(lambda s: self.streaming_enabled.emit(s == Qt.Checked))

        l = QHBoxLayout()
        l.addWidget(self.stream)

        return l

    def init_ui(self):
        l_m = QVBoxLayout(self)
        l_m.addLayout(self.__setup_model_path())
        # l_m.addLayout(self.__setup_device())
        l_m.addLayout(self.__setup_stream())
        l_m.addLayout(self.__setup_reload())
        # l_m.addWidget(Color("yellow"), stretch=1)

        self.setLayout(l_m)


class QSamPanel(QDockWidget):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.setMinimumWidth(280)
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)

        self.init_ui()

    def init_ui(self):
        wdg_m = QWidget()

        self.widget_layers = LayersWidget(self)
        self.widget_sam = SamWidget(self)

        l_m = QVBoxLayout(wdg_m)
        l_m.setAlignment(Qt.AlignTop)

        l_m.addWidget(self.widget_layers, stretch=.2)
        l_m.addWidget(self.widget_sam, stretch=.8)
        # ly_m.addWidget(Color("yellow"), stretch=1)
        # ly_m.addWidget(Color("blue"), stretch=1)
        wdg_m.setLayout(l_m)

        self.setWidget(wdg_m)

    def setup_ui(self):
        self.widget_layers.setup_ui()
