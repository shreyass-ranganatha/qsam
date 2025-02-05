from qgis.core import QgsRasterLayer, QgsRectangle, QgsMessageLog, QgsCoordinateTransform, QgsProject

import numpy as np


def image_from_layer(layer: QgsRasterLayer, bbox: QgsRectangle):
    proj = QgsProject.instance()
    bbox = QgsCoordinateTransform(proj.crs(), layer.crs(), proj) \
        .transformBoundingBox(bbox)

    w, h = round(bbox.width()), round(bbox.height())
    rs = []

    datatype = {
        1: np.uint8,
        2: np.uint16,
        4: np.uint32,
        8: np.uint64
    }

    for i in range(1, 4+1):
        # TODO find a better way to read data blocks

        band = np.frombuffer(
            layer.dataProvider().block(i, bbox, w, h).data(),
            dtype=datatype[layer.dataProvider().dataTypeSize(i)] )

        band = band.reshape(h, w, 1).astype(np.float64)
        band = (band - band.min()) / (band.max() - band.min()) * (2 ** 8)

        rs.append(band.astype(np.uint8))

    return np.concatenate(rs, axis=2)
