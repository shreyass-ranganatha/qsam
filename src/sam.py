from qgis.core import QgsReferencedRectangle

from transformers import SamModel, SamProcessor, SamConfig
import torch
import numpy as np

from . import utils


class SAM:
    def __init__(self, checkpoint: str = "facebook/sam-vit-base", device="cpu"):
        #
        self.set_checkpoint(checkpoint)
        self.set_device(device)

        #
        self.checkpoint = None

        self.__image_context: utils.ImageContext = None

        self.__image_embedding = None
        self.__image: np.ndarray = None
        self.__scale = None

    @property
    def context(self) -> utils.ImageContext:
        return self.__image_context

    @property
    def image(self):
        return self.context.image

    @property
    def image_width(self):
        return self.image.shape[1]

    @property
    def image_height(self):
        return self.image.shape[0]

    def set_checkpoint(self, id: str, local_files_only: bool = True):
        p = SamProcessor.from_pretrained(id, local_files_only=local_files_only)
        m = SamModel.from_pretrained(id, local_files_only=local_files_only)

        self.p, self.m = p, m
        self.checkpoint = id

    def set_device(self, device):
        self.device = torch.device(device)
        self.m.to(device)

    def set_image(self, image_context: utils.ImageContext):
        inp = self.p(
            images=image_context.image,
            return_tensors="pt"
        ).to(device=self.m.device)

        with torch.no_grad():
            self.__image_embedding = self.m.get_image_embeddings(
                pixel_values=inp["pixel_values"])

        self.__image_context = image_context
        return True

    def prompt(self, pts):
        if self.__image_embedding is None:
            return

        ps = [p[0] for p in pts]
        ls = [p[1] for p in pts]

        inp = self.p(
            images=self.image,
            input_points=[ps],
            input_labels=[ls],
            return_tensors="pt"
        ).to(self.m.device)

        del inp["pixel_values"]
        inp["image_embeddings"] = self.__image_embedding

        with torch.no_grad():
            out = self.m.forward(
                **inp,
                multimask_output=False # NOTE
            )

        rimg, *_ = self.p.post_process_masks(
            out.pred_masks.cpu(),
            inp["original_sizes"].cpu(),
            inp["reshaped_input_sizes"].cpu())

        return rimg.to(torch.uint8)[0, 0].numpy()

    def prompt_box(self, box):
        inp = self.p(
            images=self.image,
            input_boxes=[[box]],
            return_tensors="pt"
        ).to(self.m.device)

        del inp["pixel_values"]
        inp["image_embeddings"] = self.__image_embedding

        with torch.no_grad():
            out = self.m.forward(
                **inp,
                multimask_output=True # NOTE
            )

        rimg, *_ = self.p.post_process_masks(
            out.pred_masks.cpu(),
            inp["original_sizes"].cpu(),
            inp["reshaped_input_sizes"].cpu())

        rimg = rimg.to(torch.uint8)[0] \
            .any(axis=0) \
            .numpy() \
            .astype(np.uint8)

        return rimg
