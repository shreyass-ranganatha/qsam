from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand, QgsMapMouseEvent, QgsVertexMarker, QgsMapToolExtent
from qgis.core import QgsWkbTypes, QgsGeometry, QgsRectangle, Qgis, QgsPointXY

from PyQt5.QtWidgets import QToolBar, QAction, QGraphicsScene
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor


__all__ = ["QSamToolBar"]


class BBoxTool(QgsMapTool):
    bbox_select = pyqtSignal(QgsRectangle)
    approve_click = pyqtSignal(QgsRectangle)

    def _draw_rect(self, x1y1, x2y2):
        self._rb.reset()

        if x1y1 is None or x2y2 is None:
            return

        self._rb.setToGeometry(QgsGeometry.fromRect(QgsRectangle(x1y1, x2y2)))
        self._rb.setColor(QColor(255, 255, 0, 255))
        self._rb.setFillColor(QColor(255, 255, 0, 50))
        self._rb.setWidth(3)

        self._rb.show()
        self.canvas().show()

    def _clear_rect(self):
        self._rb.reset()
        self.canvas().refresh()

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)

        self.x1y1 = None
        self.x2y2 = None

        self.tracking = False

        self._rb = QgsRubberBand(self.canvas(), Qgis.GeometryType.Polygon)
        self.__prev_bbox = None

    def activate(self):
        self.canvas().setMapTool(self)
        self.canvas().refresh()

        return super().activate()

    def deactivate(self):
        self.canvas().unsetMapTool(self)
        self._clear_rect()

        return super().deactivate()

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        if e.button() == Qt.LeftButton:
            self.x1y1 = self.toMapCoordinates(e.pos())
            self.x2y2 = None

            self.tracking = True
            self._draw_rect(self.x1y1, self.x1y1)

            self.__prev_bbox = None

        elif (
            e.button() == Qt.RightButton and
            self.x1y1 is not None and
            self.x2y2 is not None
        ):
            self.__prev_bbox = QgsRectangle(self.x1y1, self.x2y2)
            self.bbox_select.emit(self.__prev_bbox)

            self.x1y1 = None
            self.x2y2 = None
            self._clear_rect()

        elif (
            e.button() == Qt.RightButton and
            self.__prev_bbox is not None
        ):
            self.approve_click.emit(self.__prev_bbox)
            self.__prev_bbox = None

        self.canvas().refresh()
        return super().canvasPressEvent(e)

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        if not self.tracking:
            return

        self._draw_rect(self.x1y1, self.toMapCoordinates(e.pos()))
        return super().canvasMoveEvent(e)

    def canvasReleaseEvent(self, e: QgsMapMouseEvent):
        if e.button() == Qt.LeftButton and self.tracking:
                self.x2y2 = self.toMapCoordinates(e.pos())

        self.tracking = False
        return super().canvasReleaseEvent(e)


class PointTool(QgsMapTool):
    stream = pyqtSignal(QgsPointXY)
    prompt = pyqtSignal(list)

    def _mark_point(self, x, y, l):
        pt = QgsPointXY(x, y)

        mrk = QgsVertexMarker(self.canvas())
        mrk.setCenter(pt)
        mrk.setColor(QColor(100, 255, 0) if l else QColor(255, 100, 0))
        mrk.setIconType(QgsVertexMarker.ICON_CIRCLE)
        mrk.setPenWidth(3)

        self.canvas().refresh()
        self.points.append([(x, y, l), mrk])

    def _clear_markers(self):
        scene: QGraphicsScene = self.canvas().scene()
        for _, m in self.points:
            scene.removeItem(m)

        self.canvas().refresh()
        self.points = []

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)

        self.bbox: QgsRectangle = None
        self.points = []

    def set_bbox(self, bbox: QgsRectangle):
        self._clear_markers()
        self.bbox = bbox

    def activate(self):
        self.canvas().setMapTool(self)
        self.canvas().refresh()

        return super().activate()

    def deactivate(self):
        self.canvas().unsetMapTool(self)
        self._clear_markers()

        return super().deactivate()

    def canvasPressEvent(self, e: QgsMapMouseEvent):
        pos = self.toMapCoordinates(e.pos())
        pt = QgsPointXY(pos.x(), pos.y())

        if self.bbox is not None and not self.bbox.contains(pt):
            return

        if e.button() == Qt.LeftButton:
            self._mark_point(pos.x(), pos.y(), 1)

        elif e.button() == Qt.RightButton:
            self._mark_point(pos.x(), pos.y(), 0)

        return super().canvasPressEvent(e)

    def canvasMoveEvent(self, e: QgsMapMouseEvent):
        pos = self.toMapCoordinates(e.pos())
        pt = QgsPointXY(pos.x(), pos.y())

        if self.bbox is not None and not self.bbox.contains(pt):
            return

        self.stream.emit(pt)
        return super().canvasMoveEvent(e)

    def canvasDoubleClickEvent(self, e: QgsMapMouseEvent):
        if e.button() == Qt.LeftButton:
            self._clear_markers()

        # elif e.button() == Qt.MiddleButton:
        elif e.button() == Qt.RightButton:
            self.prompt.emit([p[0] for p in self.points])
            self._clear_markers()

        return super().canvasDoubleClickEvent(e)


class QSamToolBar(QToolBar):
    activated = pyqtSignal(int)

    def __init__(self, *args, canvas: QgsMapCanvas, **kw):
        super().__init__(*args, **kw)

        self.canvas = canvas

        self.init_ui()

    def init_ui(self):
        #
        self.action_use_qsam = QAction("Q", self)
        self.action_use_qsam.setToolTip("Use QSAM")
        self.action_use_qsam.setCheckable(True)
        self.action_use_qsam.toggled.connect(self.__on_toggle_qsam)
        self.addAction(self.action_use_qsam)

        #
        self.tool_aoi = BBoxTool(self.canvas)

        self.action_aoi_tool = QAction("A", self)
        self.action_aoi_tool.setToolTip("Create AOI")
        self.action_aoi_tool.setCheckable(True)
        self.action_aoi_tool.setDisabled(True)
        self.action_aoi_tool.toggled.connect(self.__on_toggle_aoi)
        self.addAction(self.action_aoi_tool)

        #
        self.ptool = PointTool(self.canvas)

        self.action_point_tool = QAction("T", self)
        self.action_point_tool.setToolTip("SAM Point Prompt")
        self.action_point_tool.setCheckable(True)
        self.action_point_tool.setDisabled(True)
        self.action_point_tool.toggled.connect(self.__on_toggle_ptool)
        self.addAction(self.action_point_tool)

        #
        self.btool = BBoxTool(self.canvas)

        self.action_box_tool = QAction("B", self)
        self.action_box_tool.setToolTip("SAM Box Prompt")
        self.action_box_tool.setCheckable(True)
        self.action_box_tool.setDisabled(True)
        self.action_box_tool.toggled.connect(self.__on_toggle_btool)
        self.addAction(self.action_box_tool)

    def __on_toggle_qsam(self, state):
        if state:
            self.action_aoi_tool.setDisabled(False)
            self.action_point_tool.setDisabled(False)
            self.action_box_tool.setDisabled(False)

            self.activated.emit(1)

        else:
            self.action_aoi_tool.setChecked(False)
            self.action_aoi_tool.setDisabled(True)

            self.action_point_tool.setChecked(False)
            self.action_point_tool.setDisabled(True)

            self.action_box_tool.setChecked(False)
            self.action_box_tool.setDisabled(True)

            self.activated.emit(0)

    def __on_toggle_aoi(self, state):
        if state:
            self.action_aoi_tool.setChecked(True)
            self.action_point_tool.setChecked(False)
            self.action_box_tool.setChecked(False)

            if not self.tool_aoi.isActive():
                self.tool_aoi.activate()
        else:
            if self.tool_aoi.isActive():
                self.tool_aoi.deactivate()

    def __on_toggle_ptool(self, state):
        if state:
            self.action_aoi_tool.setChecked(False)
            self.action_point_tool.setChecked(True)
            self.action_box_tool.setChecked(False)

            if not self.ptool.isActive():
                self.ptool.activate()
        else:
            if self.ptool.isActive():
                self.ptool.deactivate()

    def __on_toggle_btool(self, state):
        if state:
            self.action_aoi_tool.setChecked(False)
            self.action_point_tool.setChecked(False)
            self.action_box_tool.setChecked(True)

            if not self.btool.isActive():
                self.btool.activate()
        else:
            if self.btool.isActive():
                self.btool.deactivate()

    def deleteLater(self):
        self.tool_aoi.deactivate()
        self.ptool.deactivate()

        return super().deleteLater()
