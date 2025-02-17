from transformers import SamModel, SamProcessor, SamConfig
import torch
import threading


class SAM:
    def __init__(self, device="cpu"):
        self.t_lock = threading.Lock()

        #
        self.model = "facebook/sam-vit-base"
        self.set_model(self.model)

        #
        self.set_device(device)

        #
        self.__image_embedding = None
        self.__image = None

    def set_model(self, model: str):
        try:
            self.p = SamProcessor.from_pretrained(model)
            self.m = SamModel.from_pretrained(model)

        except Exception as e:
            self.p = SamProcessor.from_pretrained(self.model)
            self.m = SamModel.from_pretrained(self.model)

            raise

        finally:
            self.model = model

    def set_device(self, device):
        with self.t_lock:
            self.device = torch.device(device)
            self.m.to(device)

    def set_image(self, image, bbox):
        inp = self.p(
            images=image,
            return_tensors="pt"
        ).to(device=self.m.device)

        with torch.no_grad():
            self.__image_embedding = self.m.get_image_embeddings(
                pixel_values=inp["pixel_values"])

        self.bbox = bbox
        self.__image = image

    def stream(self, pt):
        if self.__image_embedding is None:
            return

        x, y = pt.x(), pt.y()
        x = round(x - self.bbox.xMinimum())
        y = round(self.bbox.yMaximum() - y)

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
                round(p[0] - self.bbox.xMinimum()),
                round(self.bbox.yMaximum() - p[1]),
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
