from typing import Any, Optional

from qgis.core import (
    QgsProject,
    QgsMapLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterFile,
    QgsReferencedRectangle,
    QgsRectangle,
    QgsRasterLayer,
    QgsCoordinateReferenceSystem,
    QgsProcessingParameterString,
    QgsFeatureSink,
    QgsProcessing,
    QgsProcessingUtils,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterEnum,
    QgsProcessingParameterMapLayer,
    QgsProcessingFeedback,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource, )

import processing

import geopandas as gpd

from rasterio.transform import rowcol
from rasterio.windows import Window
import rasterio.features
import rasterio.io
import rasterio

from pathlib import Path
import numpy as np
import os

from .. import data, utils, consts


def compute_transform_and_window(bbox: list[int], strf: rasterio.transform.Affine):
    p1 = ~strf * (bbox[0], bbox[1])
    p2 = ~strf * (bbox[2], bbox[3])

    w = int(round(abs(p2[0] - p1[0])))
    h = int(round(abs(p2[1] - p1[1])))

    trf = rasterio.transform.from_bounds(*bbox, w, h)
    wnd = rasterio.windows.from_bounds(*bbox, transform=strf)

    return trf, wnd, (h, w)



class DatasetExportAlgorithm(QgsProcessingAlgorithm):
    def name(self) -> str:
        return "export_dataset"

    def displayName(self) -> str:
        return "Export Dataset"

    # def group(self) -> str:
    #     return "Dataset"

    # def groupId(self) -> str:
    #     return "dataset"

    def shortHelpString(self):
        return "Export ROIs as a dataset"

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        # input raster layer
        raster_layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if lyr.type() == QgsMapLayer.RasterLayer
        ]

        vector_layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if lyr.type() == QgsMapLayer.VectorLayer
        ]

        default_raster_id = raster_layers[0].id() if raster_layers else None
        default_vector_id = vector_layers[0].id() if vector_layers else None

        self.addParameter(QgsProcessingParameterRasterLayer(
            name="INPUT_RASTER",
            description="Input Raster",
            defaultValue=default_raster_id, )
            # types=[QgsProcessing.TypeVectorAnyGeometry],
        )

        self.addParameter(QgsProcessingParameterVectorLayer(
            name="INPUT_VECTOR",
            description="Input Vector",
            defaultValue=default_vector_id, )
            # types=[QgsProcessing.TypeVectorAnyGeometry],
        )

        self.addParameter(QgsProcessingParameterFile(
            name="DB_FILE",
            description="ROIs database file", )
        )

        self.addParameter(QgsProcessingParameterNumber(
            name="WINDOW_SIZE",
            description="Window Size",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=256,
            minValue=1, )
        )

        self.addParameter(QgsProcessingParameterNumber(
            name="STRIDE",
            description="Stride",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=-1,
            minValue=-1, )
        )

        self.addParameter(QgsProcessingParameterFolderDestination(
            name="OUTPUT_DIR",
            description="Output Directory", )
        )

    def processAlgorithm(
        self,
        params: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback
    ):
        vector_layer = QgsProject.instance().mapLayer(params["INPUT_VECTOR"])
        raster_layer = QgsProject.instance().mapLayer(params["INPUT_RASTER"])

        if raster_layer is not None:
            raster_layer_path = raster_layer.source()

        elif os.path.exists(params["INPUT_RASTER"]):
            raster_layer_path = params["INPUT_RASTER"]

        rf: rasterio.DatasetReader = rasterio.open(raster_layer_path)
        bounds = QgsReferencedRectangle(
            rectangle=QgsRectangle(rf.bounds.left, rf.bounds.bottom, rf.bounds.right, rf.bounds.top),
            crs=QgsCoordinateReferenceSystem.fromEpsgId(rf.crs.to_epsg()), )

        db = data.DataStore(params["DB_FILE"])

        p_window_size = params["WINDOW_SIZE"]
        p_stride = params["STRIDE"] if params["STRIDE"] != -1 else p_window_size

        p_output_dir = Path(params["OUTPUT_DIR"])

        images_output_dir = p_output_dir / "images"
        images_output_dir.mkdir(exist_ok=True, parents=True)

        labels_output_dir = p_output_dir / "labels"
        labels_output_dir.mkdir(exist_ok=True, parents=True)

        bboxes = db.list_rois(bounds)
        i_counter = 0

        for i, bbox in enumerate(bboxes):
            r_cof, r_rof = rowcol(rf.transform, bbox.xMinimum(), bbox.yMaximum())

            # TODO: Fix rasterizing

            # rasterize
            # mf = gpd.read_file(vector_layer.dataProvider().dataSourceUri())
            # mf = gpd.read_file(buffer["OUTPUT"])
            # feedback.pushInfo(f"{[(shp, 1) for shp in mf['geometry']]}")

            # transform = compute_transform_and_window(
            #     [bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(), bbox.yMaximum()],
            #     rf.transform)

            # mask = rasterio.features.rasterize(
            #     # shapes=[(shp, 1) for shp in mf["geometry"]],
            #     shapes=[(shp, 1) for shp in mf["geometry"]],
            #     out_shape=(bbox.height(), bbox.width()),
            #     transform=transform,
            #     fill=0,
            #     all_touched=True
            # )

            # feedback.pushInfo(f"{mask.shape}")

            # Assume vector_layer and bbox are defined
            tmp_path = QgsProcessingUtils.generateTempFilename(f"temp_output {i:03}.tif", context)
            os.makedirs(os.path.dirname(tmp_path), exist_ok=True)

            rasterize_params = {
                "INPUT": utils.get_vector_layer_uri(vector_layer),
                # "INPUT": buffer["OUTPUT"],
                "FIELD": "class",
                "USE_Z": False,
                "UNITS": 0,
                "WIDTH": int(bbox.width()),
                "HEIGHT": int(bbox.height()),
                "EXTENT": utils.extent_str_from_rectangle(bbox),
                "NODATA": 0,
                "OPTIONS": "",
                "DATA_TYPE": 5,
                "INIT": None,
                "INVERT": False,
                "EXTRA": "",
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT
            }

            res = processing.run(
                "gdal:rasterize",
                parameters=rasterize_params,
                is_child_algorithm=True,
                context=context,
                feedback=feedback)

            feedback.pushDebugInfo(f"gdal:rasterize — {rasterize_params}")
            feedback.pushInfo(f"Rasterized Vector {i:03}: {res['OUTPUT']}")

            # rl = QgsRasterLayer(res["OUTPUT"], f"raster boxes {i:03}")
            # QgsProject.instance().addMapLayer(rl)

            with rasterio.open(res["OUTPUT"]) as vf:
                v_cof, v_rof = rowcol(vf.transform, bbox.xMinimum(), bbox.yMaximum())

                for ws in range(0, int(round(bbox.width())) + 1, p_stride):
                    for hs in range(0, int(round(bbox.height())) + 1, p_stride):
                        rw = Window(r_cof + ws, r_rof + hs, p_window_size, p_window_size)
                        # intersect within bbox bounds
                        rw = rw.intersection(Window(
                            r_cof, r_rof,
                            int(round(bbox.width())), int(round(bbox.height())),))

                        vw = Window(v_cof + ws, v_rof + hs, p_window_size, p_window_size)

                        image = rf.read(window=rw)
                        image = utils.normalize(image)
                        feedback.pushDebugInfo("{} {}".format(image.shape, image.dtype))

                        label = vf.read(1, window=vw)
                        feedback.pushDebugInfo("{} {}".format(label.shape, np.unique(label),))

                        # write arrays
                        np.save(images_output_dir / f"{i_counter:04}.npy", image)
                        np.save(labels_output_dir / f"{i_counter:04}.npy", label)

                        i_counter += 1

                        if consts.MODE_DEBUG:
                            import matplotlib.pyplot as pt

                            (p_output_dir / "images-png").mkdir(exist_ok=True, parents=True)
                            pt.imsave(p_output_dir / "images-png" / f"{i_counter:04}.png", np.stack(image, axis=2))

                            (p_output_dir / "labels-png").mkdir(exist_ok=True, parents=True)
                            pt.imsave(p_output_dir / "labels-png" / f"{i_counter:04}.png", label)

        return {
            "OUTPUT_DIR": p_output_dir,
        }

    @classmethod
    def createInstance(cls):
        return cls()
