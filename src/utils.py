from qgis.core import (
    QgsRasterLayer,
    QgsRectangle,
    QgsCoordinateTransform,
    QgsProject,
    QgsVectorLayer,
    QgsMessageLog,
    QgsFeature,
    QgsReferencedRectangle,
    QgsMapLayerStyleManager,
    QgsCoordinateReferenceSystem )

from qgis.gui import QgsMapCanvas

import numpy as np
from dataclasses import dataclass

from . import consts


@dataclass
class ImageContext:
    image: np.ndarray
    layer: QgsRasterLayer
    bbox: QgsReferencedRectangle
    scale: list[float]
    resolution: float

    def resolve(self, x: float, y: float) -> list[int, int]:
        return [
            x / self.scale[0] * self.resolution,
            y / self.scale[1] * self.resolution]

    def resolve_bbox(self, bbox: QgsReferencedRectangle) -> QgsReferencedRectangle:
        return QgsReferencedRectangle(
            QgsRectangle(
                *self.resolve(bbox.xMinimum(), bbox.yMaximum()),
                *self.resolve(bbox.xMaximum(), bbox.yMinimum())),
            crs=self.bbox.crs() )

    def internal_point(self, x: float, y: float) -> list[float]:
        return self.resolve(x - self.bbox.xMinimum(), self.bbox.yMaximum() - y)

    def internal_box(self, bbox: QgsReferencedRectangle) -> list[float]:
        bbox = QgsReferencedRectangle(
            rectangle=QgsRectangle(
                bbox.xMinimum() - self.bbox.xMinimum(),
                self.bbox.yMaximum() - bbox.yMaximum(),
                bbox.xMaximum() - self.bbox.xMinimum(),
                self.bbox.yMaximum() - bbox.yMinimum(),),
            crs=self.bbox.crs() )

        return list(self.resolve_bbox(bbox).toRectF().getCoords())

    def to_crs(self, crs: QgsCoordinateReferenceSystem) -> QgsReferencedRectangle:
        proj = QgsProject.instance()

        if crs == "proj":
            crs = proj.crs()

        r = QgsCoordinateTransform(self.bbox.crs(), crs, proj) \
            .transformBoundingBox(self.bbox)

        return QgsReferencedRectangle(rectangle=r, crs=crs)


def log(*args):
    QgsMessageLog.logMessage(
        message=" ".join(str(_) for _ in args),
        tag="QSAM")


def ptshow(img):
    import matplotlib.pyplot as pt
    pt.imshow(img); pt.show()


def image_from_layer(
    layer: QgsRasterLayer,
    bbox: QgsReferencedRectangle,
    resolution: float = 1000.
) -> ImageContext:

    proj = QgsProject.instance()

    l_bbox = QgsCoordinateTransform(bbox.crs(), layer.crs(), proj) \
        .transformBoundingBox(bbox)
    l_bbox = QgsReferencedRectangle(rectangle=l_bbox, crs=layer.crs())

    l_scale = [layer.rasterUnitsPerPixelX(), layer.rasterUnitsPerPixelY()]

    w, h = round(l_bbox.width() / l_scale[0]), round(l_bbox.height() / l_scale[1])

    s = resolution / max(w, h)
    w, h = int(w * s), int(h * s)

    datatype = {
        1: np.uint8,
        2: np.uint16,
        4: np.uint32,
        8: np.uint64
    }

    rs = []

    # TODO improve this process
    for i in range(1, layer.bandCount()+1):
        band = np.frombuffer(
            layer.dataProvider().block(i, l_bbox, w, h).data(),
            dtype=datatype[layer.dataProvider().dataTypeSize(i)] )

        assert 0 not in band.shape, f"Invalid shape of image {band.shape}"

        band = band.reshape(h, w, 1).astype(np.float64)
        band = (band - band.min()) / (band.max() - band.min()) * (2 ** 8)

        rs.append(band.astype(np.uint8))

    # shape (H, W, C)
    rimg = np.concatenate(rs, axis=2)

    if consts.MODE_DEBUG:
        log(rimg.shape)
        ptshow(rimg)

    return ImageContext(
        image=rimg[..., :3], # TODO: Support FCC ?
        layer=layer,
        bbox=l_bbox,
        scale=l_scale,
        resolution=s )


def empty_vector_layer(
    p_crs: QgsCoordinateReferenceSystem = None
) -> QgsVectorLayer:

    if p_crs is None:
        p_crs = QgsProject.instance().crs()

    assert isinstance(p_crs, QgsCoordinateReferenceSystem), "Invalid CRS dtype"

    layer = QgsVectorLayer(
        path=f"Polygon?crs={p_crs.authid()}&field=id:integer"
            "&field=class:integer&field=area:double",
        baseName="QSAM polys",
        providerLib="memory", )

    return layer


def write_features_into_vector_layer(
    features: list[QgsFeature],
    layer: QgsVectorLayer,
    canvas: QgsMapCanvas
):
    return True

    layer.startEditing()
    layer.dataProvider().addFeatures(features)

    layer.commitChanges(stopEditing=True)
    canvas.refresh()

