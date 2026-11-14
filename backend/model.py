import io
import pickle
import threading
import warnings
from pathlib import Path

import torch
from PIL import Image, ImageOps, UnidentifiedImageError
from torchvision import models, transforms

from .catalog import BY_ID

ARCHITECTURE = "mobilenet_v3_small"
NORMALIZE = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])


def evaluation_transform():
    return transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(), NORMALIZE])


def build_model(classes, pretrained=False):
    weights = models.MobileNet_V3_Small_Weights.DEFAULT if pretrained else None
    network = models.mobilenet_v3_small(weights=weights)
    network.classifier[-1] = torch.nn.Linear(network.classifier[-1].in_features, classes)
    return network


def decode_image(raw):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("请上传 JPG、PNG 或 WebP 图片。")
                if image.width * image.height > 20_000_000:
                    raise ValueError("图片不能超过 2000 万像素。")
                image.load()
                image = ImageOps.exif_transpose(image)
                if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    background = Image.new("RGBA", rgba.size, "white")
                    image = Image.alpha_composite(background, rgba)
                return image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("无法读取图片，请换一张有效的 JPG、PNG 或 WebP。") from exc


class Classifier:
    def __init__(self, path):
        self.path = Path(path)
        self.network = None
        self.classes = []
        self.metadata = {}
        self.error = None
        self.lock = threading.Lock()

    def load(self):
        if not self.path.is_file():
            return
        try:
            checkpoint = torch.load(self.path, map_location="cpu", weights_only=True)
            classes = checkpoint["classes"]
            if checkpoint.get("architecture") != ARCHITECTURE:
                raise ValueError("模型结构不匹配")
            if len(classes) < 2 or len(set(classes)) != len(classes) or any(c not in BY_ID for c in classes):
                raise ValueError("模型类别不匹配")
            network = build_model(len(classes))
            network.load_state_dict(checkpoint["state_dict"], strict=True)
            network.eval()
            self.classes, self.network = classes, network
            self.metadata = checkpoint.get("metrics", {})
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, EOFError, pickle.UnpicklingError) as exc:
            self.error = f"模型加载失败：{type(exc).__name__}。请重新训练并重启服务。"

    @property
    def ready(self):
        return self.network is not None

    def predict(self, raw):
        image = decode_image(raw)
        tensor = evaluation_transform()(image).unsqueeze(0)
        with self.lock, torch.inference_mode():
            scores = self.network(tensor).softmax(dim=1)[0].tolist()
        ranking = sorted([dict(monster=BY_ID[key], score=score) for key, score in zip(self.classes, scores)], key=lambda row: row["score"], reverse=True)
        return dict(winner=ranking[0]["monster"], ranking=ranking, mode="model", notice="分数是模型在已知怪兽类别中的相对输出，未经概率校准。真人照片不属于训练分布，匹配仅供娱乐，不代表性格、能力或身份。")
