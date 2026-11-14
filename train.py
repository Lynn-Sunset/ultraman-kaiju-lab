"""Train only visually accepted samples, keeping source groups out of both splits."""
import argparse
import hashlib
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

from backend.catalog import BY_ID
from backend.model import ARCHITECTURE, NORMALIZE, build_model, evaluation_transform

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("TORCH_HOME", str(ROOT / ".cache" / "torch"))


class MonsterDataset(Dataset):
    def __init__(self, rows, classes, transform):
        self.rows, self.classes, self.transform = rows, classes, transform

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(ROOT / row["path"]) as im:
            image = im.convert("RGB")
        return self.transform(image), self.classes.index(row["class_id"])


def split_samples(rows, seed=42):
    accepted = [r for r in rows if r.get("review_status") == "accepted"]
    classes = sorted({r["class_id"] for r in accepted})
    if len(classes) < 2 or any(c not in BY_ID for c in classes):
        raise ValueError("至少需要两个已审核的已知怪兽类别。")
    seen, groups = {}, {}
    for row in accepted:
        digest = hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
        if digest in seen:
            if seen[digest] != row["class_id"]:
                raise ValueError("同一图片存在冲突标签，请重新审核。")
            continue
        seen[digest] = row["class_id"]
        group = row["source_group"]
        if group in groups and groups[group][0]["class_id"] != row["class_id"]:
            raise ValueError("同一来源组包含不同怪兽标签，请重新审核。")
        groups.setdefault(group, []).append(row)
    train, val = [], []
    rng = random.Random(seed)
    for label in classes:
        candidates = [key for key, samples in groups.items() if samples[0]["class_id"] == label]
        if len(candidates) < 2:
            raise ValueError(f"{label} 至少需要两个独立来源组，不能把同一商品的不同角度同时放进训练集和验证集。")
        rng.shuffle(candidates)
        nval = max(1, round(len(candidates) * .2))
        for index, key in enumerate(candidates):
            (val if index < nval else train).extend(groups[key])
    return classes, train, val


def train(args):
    if args.epochs < 1 or args.batch_size < 2:
        raise ValueError("epochs 至少为 1，batch-size 至少为 2。")
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    rows = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    classes, training, validation = split_samples(rows, args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    network = build_model(len(classes), pretrained=args.weights == "imagenet").to(device)
    # Frozen ImageNet features are practical for this deliberately small seed set.
    if args.weights == "imagenet" and not args.finetune:
        for parameter in network.features.parameters():
            parameter.requires_grad = False
    augmentation = transforms.Compose([transforms.RandomResizedCrop(224, scale=(.7, 1.)), transforms.RandomHorizontalFlip(), transforms.ColorJitter(.15, .15, .15), transforms.ToTensor(), NORMALIZE])
    generator = torch.Generator().manual_seed(args.seed)
    train_loader = DataLoader(MonsterDataset(training, classes, augmentation), batch_size=args.batch_size, shuffle=True, generator=generator, num_workers=0)
    val_loader = DataLoader(MonsterDataset(validation, classes, evaluation_transform()), batch_size=args.batch_size, num_workers=0)
    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, network.parameters()), lr=args.lr)
    counts = torch.tensor([sum(r["class_id"] == c for r in training) for c in classes], dtype=torch.float, device=device)
    loss_fn = torch.nn.CrossEntropyLoss(weight=counts.sum() / (len(classes) * counts))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    best, best_accuracy, history = -1., -1., []
    print(f"Device={device} classes={classes} train={len(training)} val={len(validation)}", flush=True)
    for epoch in range(args.epochs):
        network.train()
        if args.weights == "imagenet" and not args.finetune:
            network.features.eval()
        # Feature BatchNorm stays in eval mode for singleton final batches.
        for module in network.features.modules():
            if isinstance(module, torch.nn.BatchNorm2d):
                module.eval()
        total_loss = 0.
        for inputs, labels in train_loader:
            optimizer.zero_grad(set_to_none=True)
            logits = network(inputs.to(device))
            loss = loss_fn(logits, labels.to(device))
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(labels)
        network.eval()
        correct, matrix = 0, torch.zeros((len(classes), len(classes)), dtype=torch.int64)
        with torch.inference_mode():
            for inputs, labels in val_loader:
                predictions = network(inputs.to(device)).argmax(1).cpu()
                correct += (predictions == labels).sum().item()
                for actual, predicted in zip(labels, predictions):
                    matrix[actual, predicted] += 1
        accuracy = correct / len(validation)
        recalls = matrix.diag().float() / matrix.sum(1).clamp(min=1)
        balanced_accuracy = recalls.mean().item()
        record = dict(epoch=epoch + 1, train_loss=total_loss / len(training), validation_accuracy=accuracy, balanced_accuracy=balanced_accuracy)
        history.append(record)
        print(json.dumps(record), flush=True)
        if balanced_accuracy > best or (balanced_accuracy == best and accuracy > best_accuracy):
            best, best_accuracy = balanced_accuracy, accuracy
            per_class = {label: dict(train_samples=sum(r["class_id"] == label for r in training), validation_samples=int(matrix[index].sum()), recall=float(recalls[index])) for index, label in enumerate(classes)}
            metrics = dict(validation_accuracy=accuracy, balanced_accuracy=balanced_accuracy, train_samples=len(training), validation_samples=len(validation), epoch=epoch + 1, confusion_matrix=matrix.tolist(), class_order=classes, per_class=per_class, prototype=True)
            checkpoint = dict(architecture=ARCHITECTURE, classes=classes, state_dict={k: v.cpu() for k, v in network.state_dict().items()}, metrics=metrics, created_at=datetime.now(timezone.utc).isoformat(), seed=args.seed)
            temporary = output.with_suffix(".tmp")
            torch.save(checkpoint, temporary)
            temporary.replace(output)
    report = dict(classes=classes, best_validation_accuracy=best_accuracy, best_balanced_accuracy=best, selection_metric="balanced_accuracy", history=history, train=[r["path"] for r in training], validation=[r["path"] for r in validation], caveat="Small official product/reference seed set; validation is not a held-out test or human-photo benchmark.")
    output.with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {output}; selected validation accuracy: {best_accuracy:.1%}; balanced accuracy: {best:.1%}. Prototype only.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train the visually reviewed kaiju seed dataset")
    parser.add_argument("--manifest", default=str(ROOT / "data" / "manifest.json"))
    parser.add_argument("--output", default=str(ROOT / "models" / "monster.pt"))
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=.001)
    parser.add_argument("--weights", choices=["imagenet", "none"], default="imagenet")
    parser.add_argument("--finetune", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    try:
        train(parser.parse_args())
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(1, f"训练未开始：{exc}\n")
