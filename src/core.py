from qgis.gui import QgisInterface, QgsRubberBand
from qgis.core import Qgis, QgsRectangle, QgsGeometry

from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt

from . import widgets


__all__ = ["QSAM"]


class QSAM:
    def _update_available_rasters(self, rasters):
        self.available_rasters = rasters

    def _update_selected_raster_index(self, index):
        self.selected_raster_index = index

    def _bbox_select(self, bbox: QgsRectangle):
        if self.selected_raster_index < 0:
            return

        self.bbox = bbox
        self.toolbar.tool_qsam.set_bbox(bbox)

        self.render_state()
        self.toolbar.action_use_tool.toggle()

        # TODO SAM embed image

    def _stream_sam(self):
        pass

    def _prompt_sam(self):
        pass

    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.canvas = iface.mapCanvas()

        # state
        self.bbox: QgsRectangle = None
        self.available_rasters: list = []
        self.selected_raster_index: int = -1

    def __setup_toolbar(self):
        self.toolbar = widgets.QSamToolBar("QSAM Toolbar", canvas=self.canvas)
        self.toolbar.tool_bbox.bbox_select.connect(self._bbox_select)

        self.toolbar.tool_qsam.stream.connect(self._stream_sam)
        self.toolbar.tool_qsam.prompt.connect(self._prompt_sam)

        self.toolbar.activated.connect(lambda s: self.render_state() if s else self.clear_canvas())

        self.iface.addToolBar(self.toolbar)

    def __setup_panel(self):
        self.panel = widgets.QSamPanel("QSAM")
        self.panel.widget_rasters.available_rasters.connect(self._update_available_rasters)
        self.panel.widget_rasters.selected_raster_index.connect(self._update_selected_raster_index)

        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.panel)

    def initGui(self):
        self._rb_bbox = QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon)
        self._rb_mask = QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon)

        self.__setup_panel()
        self.__setup_toolbar()

    def render_state(self):
        self._rb_bbox.reset()

        if self.bbox is None:
            return

        self._rb_bbox.setToGeometry(QgsGeometry.fromRect(self.bbox))
        self._rb_bbox.setColor(QColor(255, 255, 0, 255))
        self._rb_bbox.setFillColor(QColor(255, 255, 255, 0))
        self._rb_bbox.setWidth(3)

        self._rb_bbox.show()
        self.canvas.refresh()

    def clear_canvas(self):
        self._rb_bbox.reset()
        self.canvas.refresh()

    def unload(self):
        self.clear_canvas()

        self.toolbar.deleteLater()
        self.iface.removeDockWidget(self.panel)
