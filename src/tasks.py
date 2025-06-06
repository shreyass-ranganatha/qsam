from qgis.core import *
import numpy as np

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
