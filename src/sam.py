from transformers import SamModel, SamProcessor, SamConfig
import torch
import numpy as np


class SAM:
    def __init__(self, checkpoint: str = "facebook/sam-vit-base", device="cpu"):
        #
        self.set_checkpoint(checkpoint)
        self.set_device(device)

        #
        self.checkpoint = None

        self.__image_embedding = None
        self.__image = None
        self.__scale = None

    @property
    def image(self):
        return self.__image

    @property
    def image_width(self):
        return self.__image.shape[1]

    @property
    def image_height(self):
        return self.__image.shape[0]

    def set_checkpoint(self, id: str, local_files_only: bool = True):
        p = SamProcessor.from_pretrained(id, local_files_only=local_files_only)
        m = SamModel.from_pretrained(id, local_files_only=local_files_only)

        self.p, self.m = p, m
        self.checkpoint = id

    def set_device(self, device):
        self.device = torch.device(device)
        self.m.to(device)

    def set_image(self, image, scale, bbox):
        inp = self.p(
            images=image,
            return_tensors="pt"
        ).to(device=self.m.device)

        with torch.no_grad():
            self.__image_embedding = self.m.get_image_embeddings(
                pixel_values=inp["pixel_values"])

        self.bbox = bbox
        self.__image = image
        self.__scale = scale

        return True

    def stream(self, pt):
        if self.__image_embedding is None:
            return

        x, y = pt.x(), pt.y()
        x = (x - self.bbox.xMinimum()) / self.__scale[0]
        y = (self.bbox.yMaximum() - y) / self.__scale[1]

        inp = self.p(
            images=self.__image,
            input_points=[[[x, y]]],
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

        return rimg.to(torch.uint8)[0, 0].numpy()

    def prompt(self, pts):
        if self.__image_embedding is None:
            return

        ps = [
            [
                (p[0] - self.bbox.xMinimum()) / self.__scale[0],
                (self.bbox.yMaximum() - p[1]) / self.__scale[1],
            ] for p in pts
        ]

        ls = [p[2] for p in pts]

        inp = self.p(
            images=self.__image,
            input_points=[ps],
            input_labels=[ls],
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

        return rimg.to(torch.uint8)[0, 0].numpy()

    def prompt_box(self, box):
        box = [
            (box[0] - self.bbox.xMinimum()) / self.__scale[0],
            (self.bbox.yMaximum() - box[3]) / self.__scale[1],
            (box[2] - self.bbox.xMinimum()) / self.__scale[0],
            (self.bbox.yMaximum() - box[1]) / self.__scale[1],
        ]

        inp = self.p(
            images=self.__image,
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
