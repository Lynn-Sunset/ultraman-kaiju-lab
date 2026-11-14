"""Export the trained classifier and verify the ONNX graph against PyTorch."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from PIL import Image

from backend.catalog import MONSTERS
from backend.model import build_model, evaluation_transform

ROOT = Path(__file__).resolve().parent


def main():
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    checkpoint = torch.load(ROOT / "models" / "monster.pt", map_location="cpu", weights_only=True)
    network = build_model(len(checkpoint["classes"]))
    network.load_state_dict(checkpoint["state_dict"])
    network.eval()
    folder = ROOT / "web" / "models"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "monster.onnx"
    example = torch.zeros(1, 3, 224, 224)
    torch.onnx.export(network, example, str(target), input_names=["image"], output_names=["logits"], opset_version=18, dynamo=False, external_data=False)
    onnx.checker.check_model(onnx.load(str(target)))
    session = ort.InferenceSession(str(target), providers=["CPUExecutionProvider"])
    deviations = []
    with torch.inference_mode():
        for key in ["gomora", "galactron", "metron"]:
            with Image.open(ROOT / "web" / "portraits" / f"{key}.jpg") as image:
                tensor = evaluation_transform()(image.convert("RGB")).unsqueeze(0)
            expected = network(tensor).numpy()
            actual = session.run(None, {"image": tensor.numpy()})[0]
            np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-4)
            deviations.append(float(np.abs(actual - expected).max()))
    data = ROOT / "web" / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "catalog.json").write_text(json.dumps(MONSTERS, ensure_ascii=False, indent=2), encoding="utf-8")
    dataset = json.loads((ROOT / "data" / "summary.json").read_text(encoding="utf-8"))
    config = dict(architecture="MobileNetV3 Small", classes=checkpoint["classes"], modelFile="models/monster.onnx", sha256=hashlib.sha256(target.read_bytes()).hexdigest(), metrics=checkpoint["metrics"], dataset=dict(downloaded=dataset["downloaded"], reviewed=dataset["accepted"]), preprocessing=dict(resize=256, crop=224, mean=[.485,.456,.406], std=[.229,.224,.225]), verification=dict(max_logit_difference=max(deviations), images=3), notice="真人照片匹配仅供娱乐，不代表真实性格或能力。")
    (data / "model.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {target.stat().st_size:,} bytes; 30 classes; max logit difference {max(deviations):.8f}.")


if __name__ == "__main__":
    main()
