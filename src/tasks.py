from qgis.core import *

from transformers import AutoModelForSemanticSegmentation, AutoImageProcessor
import torch

import rasterio
import numpy as np
import os

from .sam import SAM
from . import utils


class SamImageEmbedTask(QgsTask):
    def __init__(
        self,
        sam: SAM,
        context: utils.ImageContext,
        description: str = None
    ):
        super().__init__(description=description, flags=QgsTask.CanCancel)

        self.sam = sam
        self.context = context

    def run(self):
        self.sam.set_image(image_context=self.context)
        return True

    def finished(self, exception, res=None):
        if exception is not None:
            QgsMessageLog.logMessage(
                "Exception: {}".format(exception),
                "QSAM",
                Qgis.Critical)

            raise exception

        QgsMessageLog.logMessage(
            f"Embed complete {{bbox: {self.sam.bbox.toString()}}}",
            "QSAM",
            Qgis.Info)


class SamModelChangeTask(QgsTask):
    def __init__(self, sam: SAM, model: str, description: str = None, callback = None):
        super().__init__(description=description, flags=QgsTask.CanCancel)

        self.sam = sam
        self.model = model

        self.callback = callback

    def run(self):
        self.sam.set_checkpoint(id=self.model)
        return True

    def finished(self, exception, res=None):
        if self.callback is not None:
            self.callback(self.sam.checkpoint)

        if exception is not None:
            QgsMessageLog.logMessage(
                "Exception: {}".format(exception),
                "QSAM",
                Qgis.Critical)

            raise Exception("Model change failed. Check error logs")

        QgsMessageLog.logMessage(
            f"Model changed {{model: {self.sam.checkpoint}}}",
            "QSAM",
            Qgis.Info)


class InferenceTask(QgsTask):
    def __init__(
        self,
        checkpoint: str,
        context: utils.ImageContext,
        bbox: QgsReferencedRectangle,
        device: str = "cpu",
        description: str = None
    ):
        super().__init__(description=description, flags=QgsTask.CanCancel)

        self.checkpoint = checkpoint
        self.context: utils.ImageContext = context
        self.bbox = bbox

        self.device = device
        self.device = "mps"

    def run(self):

        checkpoint = os.path.join(utils.get_model_write_path(), self.panel.widget_modeling.get_model_checkpoint())

        m = AutoModelForSemanticSegmentation.from_pretrained(checkpoint)
        m.to("mps")

        p = AutoImageProcessor.from_pretrained(checkpoint)

        inps = p(images=self.context.image, return_tensors="pt")

        with torch.no_grad():
            outs = m(**inps.to("mps"))

        res, = p.post_process_semantic_segmentation(outs, target_sizes=[(int(self.bbox.height()), int(self.bbox.width())), ])
        res = res.detach().cpu().numpy().astype(np.uint8)

        transform = utils.transform_from_qgs_refrect(self.bbox, res.shape)
        crs = self.bbox.crs().authid()  # e.g., 'EPSG:32643'

        tmp_file = QgsProcessingUtils.generateTempFilename("inference_output.tif")

        with rasterio.open(
            tmp_file, "w",
            driver="GTiff",
            height=res.shape[0],
            width=res.shape[1],
            count=1,
            dtype=res.dtype,
            crs=crs,
            transform=transform,
        ) as dst:
            dst.write(res[None, ...])

        raster_layer = QgsRasterLayer(tmp_file, "inference_output")
        QgsProject.instance().addMapLayer(raster_layer)

        return True

    def finished(self, exception, res=None):
        if exception is not None:
            QgsMessageLog.logMessage(
                "Exception: {}".format(exception),
                "QSAM",
                Qgis.Critical)

            raise Exception(exception)

        QgsMessageLog.logMessage(
            f"Embed complete {{bbox: {self.sam.bbox.toString()}}}",
            "QSAM",
            Qgis.Info)
