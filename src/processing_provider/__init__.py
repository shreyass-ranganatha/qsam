from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .train_model import TrainModelAlgorithm
from .dataset_export import DatasetExportAlgorithm


class QsamProcessingProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(TrainModelAlgorithm())
        self.addAlgorithm(DatasetExportAlgorithm())

    def id(self) -> str:
        return "qsam"

    def name(self) -> str:
        return self.tr("QSAM")

    def icon(self) -> QIcon:
        return QgsProcessingProvider.icon(self)
