# from qgis.gui import QgisInterface, QgsRubberBand
# from qgis.core import Qgis, QgsRectangle, QgsGeometry, QgsPointXY, QgsVectorLayer, QgsFields, QgsField
from qgis.core import *
from qgis.gui import *

from PyQt5.QtWidgets import QInputDialog, QMessageBox
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt, QVariant

import rasterio.features
import rasterio.transform
import rasterio

import os

from . import (
    widgets,
    utils,
    sam,
    tasks,
    consts,
    data, )

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

        utils.log("resolution", self.__sam_resolution)
        utils.log("model", self.sam.checkpoint)
        utils.log("device", self.sam.device)

        image_context: utils.ImageContext = utils.image_from_layer(
            layer=layer, bbox=bbox, resolution=self.__sam_resolution)

        self.datastore.insert_roi(bbox)

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

    def __sam_initial_check(self):
        """Initial checks for SAM prompts"""

        if self.sam.context is None:
            self.iface.messageBar().pushInfo(
                title="QSAM",
                message="Please wait until an AOI is selected", )

            return False
        return True

    def _sam_stream(self, pts: list[list[QgsReferencedPointXY, int]]):

        if not self.__stream_points or not self.__sam_initial_check():
            self._rb_mask.reset()
            self.canvas.refresh()

            return

        shapes = self.sam.qgs_prompt_points(pts, to_crs="proj")

        for geom in shapes:
            self._rb_mask.setToGeometry(geom)
            self._rb_mask.setColor(QColor(0, 0, 0, 100))
            self._rb_mask.setWidth(2)

        self.canvas.refresh()

    def _sam_prompt(self, pts: list[list[QgsReferencedPointXY, int]]):
        # TODO: Fix window refresh bug, (right mouse click after saving should reset it)

        if not self.__sam_initial_check():
            return

        if self.selected_vector_index < 0:
            return self.iface.messageBar().pushMessage(
                title="Error",
                text="Please select a vector layer",
                duration=2)

        try:
            layer = self.available_vectors[self.selected_vector_index]
        except IndexError:
            return self.iface.messageBar().pushMessage(
                text="Invalid vector layer index",
                level=Qgis.MessageLevel.Warning,
                duration=2)

        shapes = self.sam.qgs_prompt_points(pts, to_crs=layer.crs())

        class_id, _ret = QInputDialog.getInt(None, "QSAM", "Enter the Class ID")
        if not _ret:
            return self.iface.messageBar().pushMessage(
                text="Class ID not valid/provided",
                level=Qgis.MessageLevel.Warning,
                duration=2)

        features = []
        for geom in shapes:
            ft = QgsFeature()
            ft.setGeometry(geom)
            ft.setAttributes([1, class_id, geom.area()])

            features.append(ft)

        # write to vector file
        if utils.write_features_into_vector_layer(
            features=features,
            layer=layer,
            canvas=self.canvas
        ):
            self.toolbar.ptool.activate()
            self.canvas.refresh()

    def _sam_stream_box(self, bbox: QgsReferencedRectangle):
        """Stream bbox prompts
        Accept bbox -> segment -> stream possible feature on canvas"""

        if not self.__sam_initial_check():
            return

        shapes = self.sam.qgs_prompt_bbox(bbox, to_crs="proj")

        for geom in shapes:
            self._rb_mask.setToGeometry(geom)
            self._rb_mask.setColor(QColor(0, 0, 0, 100))
            self._rb_mask.setWidth(2)

        self.canvas.refresh()

    def _sam_prompt_box(self, bbox: QgsReferencedRectangle):
        """Finalise bbox prompts and write into vector layer
        Accept bbox -> segment -> write into vector layer"""

        # TODO: Fix window refresh bug, (right mouse click after saving should reset it)

        if not self.__sam_initial_check():
            return

        try:
            layer = self.available_vectors[self.selected_vector_index]
        except IndexError:
            return self.iface.messageBar().pushMessage(
                text="Invalid vector layer index",
                level=Qgis.MessageLevel.Warning,
                duration=2)

        shapes = self.sam.qgs_prompt_bbox(bbox, to_crs=layer.crs())

        class_id, _ = QInputDialog.getInt(None, "QSAM", "Enter the Class ID")

        features: list[QgsFeature] = []
        for geom in shapes:
            area = geom.area()

            ft = QgsFeature()
            ft.setGeometry(geom)
            ft.setAttributes([1, class_id, area])

            features.append(ft)

        # write to vector file
        if utils.write_features_into_vector_layer(
            features=features,
            layer=layer,
            canvas=self.canvas
        ):
            self._rb_mask.reset()
            self.canvas.refresh()

    def __show_rois(self, v: bool):
        self._rb_rois.reset()
        self.canvas.refresh()

        if v:
            rts = self.datastore.list_rois()
            if not rts:
                return

            geoms = []

            for rt in rts:
                geoms.append(QgsGeometry.fromRect(rt))

            self._rb_rois.setToGeometry(QgsGeometry.collectGeometry(geoms), rt.crs())
            self._rb_rois.setColor(QColor(0, 255, 0, 255))
            self._rb_rois.setFillColor(QColor(255, 255, 255, 0))

            self._rb_rois.setWidth(4)
            self.canvas.refresh()

    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.canvas = iface.mapCanvas()

        # self.sam = sam.SAM()
        self.sam = sam.SAMBridgeForQGIS()
        self.__sam_resolution = 1000

        self.datastore = data.DataStore()

        # state variables
        self.bbox: QgsRectangle = None
        self.available_rasters: list[QgsRasterLayer] = []
        self.available_vectors: list[QgsVectorLayer] = []
        self.selected_raster_index: int = -1
        self.selected_vector_index: int = -1

        self.__stream_points: bool = True

    def __setup_toolbar(self):
        """Mapping the plugin tools"""

        self.toolbar = widgets.QSamToolBar("QSAM Toolbar", canvas=self.canvas)
        self.toolbar.activated.connect(lambda s: self.render_state() if s else self.clear_canvas())

        self.toolbar.tool_roi.bbox_select.connect(self._bbox_select)

        # point prompt tool
        self.toolbar.ptool.stream.connect(self._sam_stream)
        self.toolbar.ptool.prompt.connect(self._sam_prompt)

        # box prompt tool
        self.toolbar.btool.bbox_select.connect(self._sam_stream_box)
        self.toolbar.btool.approve_click.connect(self._sam_prompt_box)

        self.iface.addToolBar(self.toolbar)

    def __setup_panel(self):
        self.panel = widgets.QSamPanel("QSAM", canvas=self.canvas)

        ## LAYERS
        self.panel.widget_sam.m_resolution.setValue(self.__sam_resolution)
        self.panel.widget_sam.resolution_set.connect(lambda v: setattr(self, "_QSAM__sam_resolution", v))

        # sync list of available rasters/vectors
        self.panel.widget_layers.available_rasters.connect(lambda v: setattr(self, "available_rasters", v))
        self.panel.widget_layers.available_vectors.connect(lambda v: setattr(self, "available_vectors", v))

        # set selected raster/vector layers
        self.panel.widget_layers.selected_raster_index.connect(lambda v: setattr(self, "selected_raster_index", v))
        self.panel.widget_layers.selected_vector_index.connect(lambda v: setattr(self, "selected_vector_index", v))

        self.panel.widget_layers.create_vector_layer.connect(
            lambda: QgsProject.instance().addMapLayer(utils.empty_vector_layer()))

        ## SAM
        self.panel.widget_sam.selected_device.connect(self.sam.set_device)
        self.panel.widget_sam.selected_checkpoint.connect(self._sam_model_select)
        self.panel.widget_sam.streaming_enabled.connect(lambda v: setattr(self, "_QSAM__stream_points", v))

        ## DATASET
        self.panel.widget_roi.show_rois.connect(self.__show_rois)

        source_db_path = self.panel.widget_roi.i_rois_db_path.text()

        if os.path.exists(source_db_path):
            reply = QMessageBox().question(
                None,
                "QSAM — Confirm Action",
                "The DB file exists, do you want to load the data in?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes)

            if reply == QMessageBox.Yes:
                self.datastore.load(source_db_path)

        # MODEL
        # self.panel.widget_model.inference_req.connect(
        #     lambda bbox: self.modeling.inference_request(layer= , bbox=bbox))

        self.panel.setup_ui()
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.panel)

    def initGui(self):
        self._rb_bbox = QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon)
        self._rb_mask = QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon)
        self._rb_rois = QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon)

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
        # don't unload since it should persist without plugin
        self._rb_rois.reset()
        self.datastore.backup(self.panel.widget_roi.i_rois_db_path.text())

        self.clear_canvas()

        self.toolbar.deleteLater()
        self.iface.removeDockWidget(self.panel)
