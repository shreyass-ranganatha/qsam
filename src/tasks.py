from qgis.core import QgsTask, QgsRectangle, QgsMessageLog, Qgis
import numpy as np

from .sam import SAM


class SamImageEmbedTask(QgsTask):
    def __init__(self, sam: SAM, image: np.ndarray, bbox: QgsRectangle, description: str = None):
        super().__init__(description=description, flags=QgsTask.CanCancel)

        self.sam = sam

        #
        self.image = image
        self.bbox = bbox

    def run(self):
        self.sam.set_image(self.image[..., :3], self.bbox)
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
