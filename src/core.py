# from qgis.gui import QgisInterface, QgsRubberBand
# from qgis.core import Qgis, QgsRectangle, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsFields, QgsField
from qgis.core import *
from qgis.gui import *

from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt, QVariant

import rasterio.features
import rasterio.transform
import rasterio

from . import widgets, utils, sam, tasks, consts

__all__ = ["QSAM"]


class QSAM:
    def _bbox_select(self, bbox: QgsReferencedRectangle):
        if self.selected_raster_index < 0:
            return

        self.bbox = bbox
        self.toolbar.ptool.set_bbox(bbox)

        self.render_state()
        # NOTE: tool to enable after
        self.toolbar.action_box_tool.toggle()

        # TODO move to custom QgsTask
        layer = self.available_rasters[self.selected_raster_index]
        image_context: utils.ImageContext = utils.image_from_layer(
            layer=layer, bbox=bbox)

        if consts.MODE_DEBUG:
            self.sam.set_image(image_context=image_context)

        else:
            task = tasks.SamImageEmbedTask(
                sam=self.sam,
                context=image_context,
                description="QSAM Image Embed")

            task_id = QgsApplication.instance().taskManager().addTask(task=task,)

            QgsMessageLog.logMessage(
                message=f"Embed requested {{task_id: {task_id}}}",
                tag="QSAM",
                level=Qgis.Info)

    def _sam_model_select(self, model: str):
        if model == self.sam.checkpoint:
            return

        task = tasks.SamModelChangeTask(
            sam=self.sam,
            model=model,
            description="QSAM Model Update",
            callback=lambda m: self.panel.widget_sam.m_checkpoints.setCurrentText(m))

        task_id = QgsApplication.instance().taskManager().addTask(task=task,)

        QgsMessageLog.logMessage(
            message=f"Model change requested {{task_id: {task_id}}}",
            tag="QSAM",
            level=Qgis.Info)

    def _sam_stream(self, pts: list[list[QgsReferencedPointXY, int]]):
        if not self.__stream_points or self.sam.context is None:
            self._rb_mask.reset()
            self.canvas.refresh()

            return

        trf = QgsCoordinateTransform(
            pts[0][0].crs(), self.sam.context.bbox.crs(), QgsProject.instance())

        for i, (p, l) in enumerate(pts):
            p = trf.transform(p)

            p = self.sam.context.resolve(
                p.x() - self.sam.context.bbox.xMinimum(),
                self.sam.context.bbox.yMaximum() - p.y() )

            pts[i] = [p, l]

        mask = self.sam.prompt(pts)

        if mask is None:
            return

        p_bbox = self.sam.context.to_crs("proj")

        bounds = rasterio.transform.from_bounds(
            p_bbox.xMinimum(), p_bbox.yMinimum(),
            p_bbox.xMaximum(), p_bbox.yMaximum(),
            self.sam.image_width, self.sam.image_height
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

        self.canvas.refresh()

    def _sam_prompt(self, pts: list[list[QgsReferencedPointXY, int]]):
        QgsMessageLog.logMessage(f"Prompting SAM with {pts}", "QSAM", Qgis.Info)

        if self.selected_vector_index < 0:
            return self.iface.messageBar().pushMessage(
                title="Error",
                text="Please select a vector layer",
                duration=2)

        trf = QgsCoordinateTransform(
            pts[0][0].crs(), self.sam.context.bbox.crs(), QgsProject.instance())

        for i, (p, l) in enumerate(pts):
            p = trf.transform(p)

            p = self.sam.context.resolve(
                p.x() - self.sam.context.bbox.xMinimum(),
                self.sam.context.bbox.yMaximum() - p.y() )

            pts[i] = [p, l]

        mask = self.sam.prompt(pts)

        if mask is None:
            return

        try:
            layer = self.available_vectors[self.selected_vector_index]
        except IndexError:
            return self.iface.messageBar().pushMessage(
                text="Invalid vector layer index",
                level=Qgis.MessageLevel.Warning,
                duration=2)

        class_id, _ = QInputDialog.getInt(None, "QSAM", "Enter the Class ID")

        if not _:
            return self.iface.messageBar().pushMessage(
                text="Class ID not valid/provided",
                level=Qgis.MessageLevel.Warning,
                duration=2)

        # projecting to vector layer
        p_bbox = self.sam.context.to_crs(layer.crs())

        bounds = rasterio.transform.from_bounds(
            p_bbox.xMinimum(), p_bbox.yMinimum(),
            p_bbox.xMaximum(), p_bbox.yMaximum(),
            self.sam.image_width, self.sam.image_height
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
            geom = QgsGeometry.fromPolygonXY([pts])

            ft = QgsFeature()
            ft.setGeometry(geom)
            ft.setAttributes([1, class_id, geom.area()])

            features.append(ft)

        layer.startEditing()

        layer.dataProvider().addFeatures(features)
        self.canvas.refresh()

        layer.commitChanges(stopEditing=True)

        self.toolbar.ptool.activate()
        self.canvas.refresh()

    def _sam_stream_box(self, bbox: QgsReferencedRectangle):
        # prepare bbox
        bbox = QgsCoordinateTransform(bbox.crs(), self.sam.context.bbox.crs(), QgsProject.instance()) \
            .transformBoundingBox(bbox)

        box: list[float] = self.sam.context.internal_box(bbox)
        mask = self.sam.prompt_box(box)

        if mask is None:
            return

        # project the mask to the project CRS for ribbon
        p_bbox = self.sam.context.to_crs("proj")

        bounds = rasterio.transform.from_bounds(
            p_bbox.xMinimum(), p_bbox.yMinimum(),
            p_bbox.xMaximum(), p_bbox.yMaximum(),
            self.sam.image_width, self.sam.image_height
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

        self.canvas.refresh()

    def _sam_prompt_box(self, bbox: QgsReferencedRectangle):
        # prepare bbox
        bbox = QgsCoordinateTransform(bbox.crs(), self.sam.context.bbox.crs(), QgsProject.instance()) \
            .transformBoundingBox(bbox)

        box: list[float] = self.sam.context.internal_box(bbox)

        mask = self.sam.prompt_box(box)

        if mask is None:
            return

        try:
            layer = self.available_vectors[self.selected_vector_index]
        except IndexError:
            return self.iface.messageBar().pushMessage(
                text="Invalid vector layer index",
                level=Qgis.MessageLevel.Warning,
                duration=2)

        # input class ID
        class_id, _ = QInputDialog.getInt(None, "QSAM", "Enter the Class ID")

        # project the mask to the vector layer's CRS
        v_bbox = self.sam.context.to_crs(layer.crs())

        bounds = rasterio.transform.from_bounds(
            v_bbox.xMinimum(), v_bbox.yMinimum(),
            v_bbox.xMaximum(), v_bbox.yMaximum(),
            self.sam.image_width, self.sam.image_height
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

            geom = QgsGeometry.fromPolygonXY([pts])
            area = geom.area()

            ft = QgsFeature()
            ft.setGeometry(geom)
            ft.setAttributes([1, class_id, area])

            features.append(ft)

        layer.startEditing()
        layer.dataProvider().addFeatures(features)

        layer.commitChanges(stopEditing=True)
        self.canvas.refresh()

        self._rb_mask.reset()
        self.toolbar.btool.activate()

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

        self.toolbar.tool_roi.bbox_select.connect(self._bbox_select)
        self.toolbar.ptool.stream.connect(self._sam_stream)
        self.toolbar.ptool.prompt.connect(self._sam_prompt)
        self.toolbar.btool.bbox_select.connect(self._sam_stream_box)
        self.toolbar.btool.approve_click.connect(self._sam_prompt_box)

        self.iface.addToolBar(self.toolbar)

    def __setup_panel(self):
        self.panel = widgets.QSamPanel("QSAM")

        # LAYERS
        self.panel.widget_layers.available_rasters.connect(lambda v: setattr(self, "available_rasters", v))
        self.panel.widget_layers.available_vectors.connect(lambda v: setattr(self, "available_vectors", v))

        self.panel.widget_layers.selected_raster_index.connect(lambda v: setattr(self, "selected_raster_index", v))
        self.panel.widget_layers.selected_vector_index.connect(lambda v: setattr(self, "selected_vector_index", v))

        self.panel.widget_layers.create_vector_layer.connect(
            lambda: QgsProject.instance().addMapLayer(utils.empty_vector_layer()))

        # SAM
        self.panel.widget_sam.selected_device.connect(self.sam.set_device)
        self.panel.widget_sam.selected_checkpoint.connect(self._sam_model_select)
        self.panel.widget_sam.streaming_enabled.connect(lambda v: setattr(self, "_QSAM__stream_points", v))

        self.panel.setup_ui()
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
        self._rb_mask.reset()

        self.canvas.refresh()

    def unload(self):
        self.clear_canvas()

        self.toolbar.deleteLater()
        self.iface.removeDockWidget(self.panel)
