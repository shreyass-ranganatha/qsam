from qgis.core import (
    QgsRasterLayer,
    QgsRectangle,
    QgsCoordinateTransform,
    QgsProject,
    QgsVectorLayer,
    QgsMessageLog,
    QgsMapLayerStyleManager,
    QgsCoordinateReferenceSystem )

import numpy as np
from . import consts


def log(*args):
    QgsMessageLog.logMessage(
        message=" ".join(str(_) for _ in args),
        tag="QSAM")


def ptshow(img):
    import matplotlib.pyplot as pt
    pt.imshow(img); pt.show()


def image_from_layer(
    layer: QgsRasterLayer,
    bbox: QgsRectangle,
    min_scale: float = .1,
) -> tuple[np.ndarray, list[float]]:

    proj = QgsProject.instance()
    bbox = QgsCoordinateTransform(proj.crs(), layer.crs(), proj) \
        .transformBoundingBox(bbox)

    scale = [
        max(layer.rasterUnitsPerPixelX(), min_scale),
        max(layer.rasterUnitsPerPixelY(), min_scale)]

    w, h = round(bbox.width() / scale[0]), round(bbox.height() / scale[1])
    rs = []

    datatype = {
        1: np.uint8,
        2: np.uint16,
        4: np.uint32,
        8: np.uint64
    }

    # TODO improve this process
    for i in range(1, layer.bandCount()+1):

        band = np.frombuffer(
            layer.dataProvider().block(i, bbox, w, h).data(),
            dtype=datatype[layer.dataProvider().dataTypeSize(i)] )

        band = band.reshape(h, w, 1).astype(np.float64)
        band = (band - band.min()) / (band.max() - band.min()) * (2 ** 8)

        rs.append(band.astype(np.uint8))

    rimg = np.concatenate(rs, axis=2)

    if consts.MODE_DEBUG:
        log(rimg.shape)

        import matplotlib.pyplot as pt
        pt.imshow(rimg); pt.show()

    return rimg, np.array(scale)


def empty_vector_layer(
    p_crs: QgsCoordinateReferenceSystem = QgsProject.instance().crs()
) -> QgsVectorLayer:

    assert isinstance(p_crs, QgsCoordinateReferenceSystem), "Invalid CRS type"

    layer = QgsVectorLayer(
        path=f"Polygon?crs={p_crs.authid()}&field=id:integer"
            "&field=class:integer&field=area:double",
        baseName="QSAM polys",
        providerLib="memory", )

    return layer
