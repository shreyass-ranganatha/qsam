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
from PyQt5.QtWidgets import *
from PyQt5.QtGui import QColor, QPalette, QKeyEvent, QIcon
from PyQt5.QtCore import Qt, pyqtSignal

from .. import utils


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
    selected_checkpoint = pyqtSignal(str)
    streaming_enabled = pyqtSignal(bool)
    resolution_set = pyqtSignal(int)

    def __init__(self, parent):
        super().__init__(title="SAM", parent=parent)

        # self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.init_ui()

    def __cb_update_checkpoint(self):
        self.m_reload_button.setEnabled(False)
        self.selected_checkpoint.emit(self.m_checkpoints.currentText())

    def __setup_objects(self):
        # reload button
        self.m_reload_button = QPushButton(text="↻")
        self.m_reload_button.clicked.connect(self.__cb_update_checkpoint)
        self.m_reload_button.setFixedWidth(30)
        self.m_reload_button.setEnabled(False)
        self.m_reload_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        # model checkpoints
        self.m_checkpoints = QComboBox()
        # TODO
        self.m_checkpoints.setEnabled(True)
        self.m_checkpoints.setEditable(True)

        self.m_checkpoints.addItems([ # default checkpoints
            "facebook/sam-vit-base",
            "facebook/sam-vit-large",
            "facebook/sam-vit-huge"
        ])

        self.m_checkpoints.currentTextChanged.connect(lambda _: self.m_reload_button.setEnabled(True))

        # model devices
        devices = [
            "cpu",
            "cuda" if torch.cuda.is_available() else None,
            "mps" if torch.backends.mps.is_available() else None
        ]

        self.m_device = QComboBox()
        self.m_device.addItems([d for d in devices if d is not None])
        self.m_device.setCurrentIndex(0)
        self.m_device.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.m_device.currentTextChanged.connect(self.selected_device.emit)

        # model resolution
        self.m_resolution = QSpinBox()
        self.m_resolution.setRange(200, 10000)
        self.m_resolution.setValue(1000)
        self.m_resolution.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.m_resolution.enterEvent = lambda e: self.m_resolution.setToolTip("Resolution of the image")
        self.m_resolution.valueChanged.connect(lambda v: self.resolution_set.emit(v))

        # streaming
        self.stream = QCheckBox(text="Streaming Enabled")
        self.stream.setChecked(True)
        self.stream.stateChanged.connect(lambda s: self.streaming_enabled.emit(s == Qt.Checked))

    def __layout_row_1(self):
        l = QHBoxLayout()
        l.addWidget(QLabel(text="Checkpoint"), stretch=1)
        l.addWidget(self.m_checkpoints, stretch=10)
        # l.addWidget(self.m_device, stretch=2)
        l.addWidget(self.m_reload_button)

        return l

    def __layout_row_2(self):
        l = QHBoxLayout()
        l.addWidget(QLabel(text="Resolution"))
        l.addWidget(self.m_resolution)

        return l

    def __layout_row_3(self):
        l = QHBoxLayout()
        l.addWidget(self.stream, stretch=1)

        return l

    def init_ui(self):
        self.__setup_objects()

        l_m = QVBoxLayout(self)
        l_m.addLayout(self.__layout_row_1())
        l_m.addLayout(self.__layout_row_2())
        l_m.addLayout(self.__layout_row_3())

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

        l_m.addWidget(self.widget_layers)
        l_m.addWidget(self.widget_sam)
        # ly_m.addWidget(Color("yellow"), stretch=1)
        # ly_m.addWidget(Color("blue"), stretch=1)
        wdg_m.setLayout(l_m)

        self.setWidget(wdg_m)

    def setup_ui(self):
        self.widget_layers.setup_ui()
