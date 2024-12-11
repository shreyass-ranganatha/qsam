from qgis.core import QgsRasterLayer, QgsRectangle, QgsMessageLog, QgsCoordinateTransform, QgsProject

import numpy as np


def image_from_layer(layer: QgsRasterLayer, bbox: QgsRectangle):
    proj = QgsProject.instance()
    bbox = QgsCoordinateTransform(proj.crs(), layer.crs(), proj) \
        .transformBoundingBox(bbox)

    w, h = round(bbox.width()), round(bbox.height())
    rs = []

    for i in range(1, 4+1):
        # TODO find a better way to read data blocks
        band = np.frombuffer(
            layer.dataProvider().block(i, bbox, w, h).data(),
            # NOTE assuming raster is of dtype uint16
            dtype=np.uint16)

        band = band.reshape(h, w, 1).astype(np.float32)
        band = (band - band.min()) / (band.max() - band.min()) * (2 ** 8)

        rs.append(band.astype(np.uint8))

    return np.concatenate(rs, axis=2)
