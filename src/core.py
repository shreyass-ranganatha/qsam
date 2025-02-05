# from qgis.gui import QgisInterface, QgsRubberBand
# from qgis.core import Qgis, QgsRectangle, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsFields, QgsField
from qgis.core import *
from qgis.gui import *

from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt, QVariant

import rasterio.features
import rasterio
import tempfile

from . import widgets, utils, sam, tasks, consts

__all__ = ["QSAM"]


class QSAM:
    def _bbox_select(self, bbox: QgsRectangle):
        if self.selected_raster_index < 0:
            return

        self.bbox = bbox
        self.toolbar.tool_qsam.set_bbox(bbox)

        self.render_state()
        self.toolbar.action_use_tool.toggle()

        # TODO move to custom QgsTask
        image = utils.image_from_layer(
            layer=self.available_rasters[self.selected_raster_index],
            bbox=bbox)

        if consts.MODE_DEBUG:
            self.sam.set_image(image[..., :3], self.bbox)

        else:
            task = tasks.SamImageEmbedTask(
                sam=self.sam,
                image=image,
                bbox=bbox,
                description="QSAM Image Embed")

            task_id = QgsApplication.instance().taskManager().addTask(task=task,)

            QgsMessageLog.logMessage(
                message=f"Embed requested {{task_id: {task_id}}}",
                tag="QSAM",
                level=Qgis.Info)

    def _sam_stream(self, pt):
        if not self.__stream_points:
            self._rb_mask.reset()
            self.canvas.refresh()

            return

        mask = self.sam.stream(pt)

        if mask is None:
            return

        bounds = rasterio.transform.from_bounds(
            self.sam.bbox.xMinimum(), self.sam.bbox.yMinimum(),
            self.sam.bbox.xMaximum(), self.sam.bbox.yMaximum(),
            self.sam.bbox.width(), self.sam.bbox.height()
        )

        polygons = rasterio.features.shapes(
            source=mask,
            mask=mask,
            connectivity=4,
            transform=bounds
        )

        shapes = []
        for p, v in polygons:
            if v == 0:
                continue

            pts = [QgsPointXY(x, y) for x, y in p["coordinates"][0]]

            polygon = QgsGeometry.fromPolygonXY([pts])
            shapes.append(polygon)

            self._rb_mask.setToGeometry(polygon)
            self._rb_mask.setColor(QColor(0, 0, 0, 100))
            self._rb_mask.setWidth(2)

    def _sam_prompt(self, pts):
        QgsMessageLog.logMessage(f"Prompting SAM with {pts}", "QSAM", Qgis.Info)

        if self.selected_vector_index < 0:
            return self.iface.messageBar().pushMessage(
                title="Error",
                text="Please select a vector layer",
                duration=2)

        mask = self.sam.prompt(pts)

        if mask is None:
            return

        try:
            layer = self.available_vectors[self.selected_vector_index]
        except IndexError:
            return self.iface.messageBar().pushMessage(
                text="Error",
                level="Invalid vector layer index",
                duration=2)

        class_id, _o = QInputDialog.getInt(None, "QSAM", "Enter the Class ID")

        if not _o:
            self.iface.messageBar().pushMessage(
                text="Error",
                level="Class ID not valid/provided",
                duration=2)

            return

        bounds = rasterio.transform.from_bounds(
            self.sam.bbox.xMinimum(), self.sam.bbox.yMinimum(),
            self.sam.bbox.xMaximum(), self.sam.bbox.yMaximum(),
            self.sam.bbox.width(), self.sam.bbox.height()
        )

        polygons = rasterio.features.shapes(
            source=mask,
            mask=mask,
            connectivity=4,
            transform=bounds
        )

        features = []
        for p, v in polygons:
            if v == 0:
                continue

            pts = [QgsPointXY(x, y) for x, y in p["coordinates"][0]]

            ft = QgsFeature()
            ft.setGeometry(QgsGeometry.fromPolygonXY([pts]))
            ft.setAttributes([1, class_id, ft.geometry().area()])

            features.append(ft)

        layer.startEditing()

        layer.addFeatures(features)
        self.canvas.refresh()

        layer.commitChanges(stopEditing=True)

        self.toolbar.tool_qsam.activate()
        self.canvas.refresh()

    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.canvas = iface.mapCanvas()

        self.sam = sam.SAM()

        # state
        self.bbox: QgsRectangle = None
        self.available_rasters: list[QgsRasterLayer] = []
        self.available_vectors: list[QgsVectorLayer] = []
        self.selected_raster_index: int = -1
        self.selected_vector_index: int = -1

        self.__stream_points: bool = True

    def __setup_toolbar(self):
        self.toolbar = widgets.QSamToolBar("QSAM Toolbar", canvas=self.canvas)
        self.toolbar.activated.connect(lambda s: self.render_state() if s else self.clear_canvas())

        self.toolbar.tool_bbox.bbox_select.connect(self._bbox_select)
        self.toolbar.tool_qsam.stream.connect(self._sam_stream)
        self.toolbar.tool_qsam.prompt.connect(self._sam_prompt)

        self.iface.addToolBar(self.toolbar)

    def __setup_panel(self):
        self.panel = widgets.QSamPanel("QSAM")

        # widget layers
        self.panel.widget_layers.available_rasters.connect(lambda v: setattr(self, "available_rasters", v))
        self.panel.widget_layers.available_vectors.connect(lambda v: setattr(self, "available_vectors", v))

        self.panel.widget_layers.selected_raster_index.connect(lambda v: setattr(self, "selected_raster_index", v))
        self.panel.widget_layers.selected_vector_index.connect(lambda v: setattr(self, "selected_vector_index", v))

        self.panel.widget_layers.create_vector_layer.connect(self.__create_vector_layer)

        # widget sam
        self.panel.widget_sam.selected_device.connect(self.sam.set_device)
        self.panel.widget_sam.streaming_enabled.connect(lambda v: setattr(self, "_QSAM__stream_points", v))

        self.panel.setup_ui()
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.panel)

    def __create_vector_layer(self):
        fields = QgsFields()
        fields.append(QgsField("id", QVariant.Int))
        fields.append(QgsField("class", QVariant.Int))
        fields.append(QgsField("area", QVariant.Double))

        p_crs = QgsProject.instance().crs()
        t_ctx = QgsProject.instance().transformContext()

        s_opt = QgsVectorFileWriter.SaveVectorOptions()
        s_opt.driverName = "ESRI Shapefile"
        s_opt.fileEncoding = "UTF-8"

        # filepath = "/tmp/vectorfile.shp"
        _, fname = tempfile.mkstemp(suffix=".shp")
        # lname = "SAM shapes"

        lname, ok = QInputDialog.getText(self.iface.mainWindow(), "Layer Name", "Enter name for the new vector layer:")
        lname = lname.strip()

        if not ok or not lname.strip():
            return

        wt = QgsVectorFileWriter.create(
            fileName=fname,
            fields=fields,
            geometryType=QgsWkbTypes.Polygon,
            srs=p_crs,
            transformContext=t_ctx,
            options=s_opt
        )

        if wt.hasError() != QgsVectorFileWriter.NoError:
            QgsMessageLog.logMessage(wt.errorMessage(), "qSAM", Qgis.Critical)
        del wt

        layer = QgsVectorLayer(fname, lname, "ogr")
        QgsProject.instance().addMapLayer(layer)

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
        self._rb_mask.reset()

        self.canvas.refresh()

    def unload(self):
        self.clear_canvas()

        self.toolbar.deleteLater()
        self.iface.removeDockWidget(self.panel)
