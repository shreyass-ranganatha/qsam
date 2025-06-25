from typing import Any, Optional

from qgis.core import (
    QgsFeatureSink,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingParameterFile,
    QgsProcessingParameterEnum,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterMapLayer,
    QgsProcessingFeedback,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
)
from qgis import processing

from transformers import AutoModelForSemanticSegmentation, AutoImageProcessor, Trainer
import torch.utils.data
import torch

import time

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

class Types:
    unet = 0
    model2 = "ResNet"


class QsamDataset(torch.utils.data.Dataset):
    def __init__(self, ds_path: Path):
        super().__init__()

        self.ds_path = Path(ds_path)

        self.images_path = self.ds_path / "images"
        self.labels_path = self.ds_path / "labels"

        self.images = list(self.images_path.glob("*.npy"))

    def __len__(self):
        return len(self.images)

    def __getitem__(self, index):
        image_pt = self.images[index]
        label_pt = self.labels_path / os.path.basename(image_pt)

        return np.stack(np.load(image_pt), axis=2), np.load(label_pt).astype(np.uint8)


class TrainModelAlgorithm(QgsProcessingAlgorithm):
    def name(self) -> str:
        return "train_model"

    def displayName(self) -> str:
        return "Train Model"

    # def group(self) -> str:
    #     return "Modeling"

    # def groupId(self) -> str:
    #     return "modeling"

    def shortHelpString(self) -> str:
        return "Train a model with a generated QSAM dataset."

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        self.addParameter(QgsProcessingParameterString(
            name="RUN_ID",
            description="Run ID", )
        )

        self.addParameter(QgsProcessingParameterString(
            name="MODEL_CHECKPOINT",
            description="Model Checkpoint",
            # options=["Segformer: nvidia/mit-b0"],
            defaultValue="nvidia/mit-b0" )
        )

        self.addParameter(QgsProcessingParameterNumber(
            name="BATCH_SIZE",
            description="Batch Size",
            defaultValue=2,
            minValue=1, )
        )

        self.addParameter(QgsProcessingParameterNumber(
            name="NUM_EPOCHS",
            description="Num Epochs",
            defaultValue=5,
            minValue=1, )
        )

        self.addParameter(QgsProcessingParameterFolderDestination(
            name="DATASET_DIR",
            description="Dataset Directory", )
        )


        self.addParameter(QgsProcessingParameterFolderDestination(
            name="OUTPUT_DIR",
            description="Train Output Directory", )
        )

    def __collate_fn(self, args, processor: AutoImageProcessor, feedback: QgsProcessingFeedback):
        # args is (batch_size, 2 -> (image, label), ::)
        images = []
        labels = []

        for image, label in args:
            images.append(np.array(image))
            labels.append(np.array(label))

        inps = processor(
            images=images,
            segmentation_maps=labels,
            return_tensors="pt", )

        return inps

    def train_fn(
        self,
        model: AutoModelForSemanticSegmentation,
        processor: AutoImageProcessor,
        dataset: torch.utils.data.Dataset,
        params: dict,
        feedback: QgsProcessingFeedback,
        p_output_dir: str
    ):
        device = params.get("DEVICE", "mps")
        model.to(device)

        # -----------------------------
        # prepare dataloader

        dataloader = torch.utils.data.DataLoader(
            dataset,
            batch_size=params["BATCH_SIZE"],
            shuffle=True,
            collate_fn=lambda *args, **kw: self.__collate_fn(*args, **kw, processor=processor, feedback=feedback),
        )

        # -----------------------------
        optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5,)
        global_min_loss = float('inf')

        for e in range(params["NUM_EPOCHS"]):
            time_start = time.time()

            tr_losses = []

            for batch in dataloader:
                outs = model(**batch.to(device))

                loss = outs.loss
                tr_losses.append(loss.item())

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            tr_loss = np.mean(tr_losses)

            feedback.pushInfo(
                f"Epoch {e:02} — "
                f"train loss: {tr_loss} — "
                f"time taken: {time.time() - time_start}")

            if tr_loss < global_min_loss:
                global_min_loss = tr_loss

                feedback.pushDebugInfo(f"Minimum loss found, saving to {p_output_dir}")

                processor.save_pretrained(p_output_dir)
                model.save_pretrained(p_output_dir)

    def processAlgorithm(
        self,
        params: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback
    ):
        p_run_id = params["RUN_ID"]

        p_output_dir: Path = Path(params["OUTPUT_DIR"]) / p_run_id
        p_output_dir.mkdir(exist_ok=True, parents=True)

        # -----------------------------
        feedback.pushInfo("Preparing Dataset & DataLoader")

        p_dataset_path = Path(params["DATASET_DIR"])

        dataset = QsamDataset(p_dataset_path)
        feedback.pushDebugInfo(f"{len(dataset)}")

        # -----------------------------
        feedback.pushInfo("Fetching Model")

        p_checkpoint = params["MODEL_CHECKPOINT"]

        model = AutoModelForSemanticSegmentation.from_pretrained(p_checkpoint)
        processor = AutoImageProcessor.from_pretrained(p_checkpoint)

        # -----------------------------
        feedback.pushInfo("Training")

        self.train_fn(
            model=model,
            processor=processor,
            dataset=dataset,
            params=params,
            feedback=feedback,
            p_output_dir=p_output_dir)

        return {"OUTPUT": p_output_dir}

    @classmethod
    def createInstance(cls):
        return cls()
