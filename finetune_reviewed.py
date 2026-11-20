"""Fine-tune the classifier head on reviewed photos, using the previous validation set."""
import argparse
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from torchvision import transforms

from train import ROOT, MonsterDataset, split_samples
from backend.model import build_model, evaluation_transform, NORMALIZE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    torch.manual_seed(42)
    torch.set_num_threads(4)
    ckpt = torch.load(args.base, map_location="cpu", weights_only=True)
    rows = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf8"))
    classes, train, val = split_samples(rows)
    assert classes == ckpt["classes"]
    network = build_model(len(classes)).eval()
    network.load_state_dict(ckpt["state_dict"])

    def features(rows, transform):
        xs, ys = [], []
        with torch.no_grad():
            for x, y in DataLoader(MonsterDataset(rows, classes, transform), batch_size=12):
                xs.append(network.avgpool(network.features(x)).flatten(1))
                ys.append(y)
        return torch.cat(xs), torch.cat(ys)

    augment = transforms.Compose([transforms.RandomResizedCrop(224, scale=(.72, 1)), transforms.RandomHorizontalFlip(), transforms.ColorJitter(.15,.15,.15), transforms.ToTensor(), NORMALIZE])
    x, y = zip(*[features(train, transform) for transform in [evaluation_transform(), augment, augment, augment]])
    x, y = torch.cat(x), torch.cat(y)
    vx, vy = features(val, evaluation_transform())
    head = network.classifier
    optimizer = torch.optim.AdamW(head.parameters(), lr=.0003)
    loss_fn = torch.nn.CrossEntropyLoss(weight=1 / y.bincount().float())
    history = []
    best = None
    for epoch in range(31):
        head.eval()
        with torch.no_grad():
            predicted = head(vx).argmax(1)
        matrix = (vy * len(classes) + predicted).bincount(minlength=len(classes)**2).reshape(len(classes), -1)
        recall = matrix.diag() / matrix.sum(1)
        acc = float((vy == predicted).float().mean())
        balanced = float(recall.mean())
        history.append(dict(epoch=epoch, validation_accuracy=acc, balanced_accuracy=balanced))
        if epoch == 0:
            print("Baseline", acc, balanced, flush=True)
            best = (acc, balanced)
        elif (acc, balanced) > best and balanced >= history[0]["balanced_accuracy"]:
            best = (acc, balanced)
            metrics = dict(ckpt["metrics"], validation_accuracy=acc, balanced_accuracy=balanced, train_samples=len(train), validation_samples=len(val), epoch=epoch, confusion_matrix=matrix.tolist(), per_class={key:dict(train_samples=sum(r["class_id"]==key for r in train), validation_samples=int(matrix[i].sum()), recall=float(recall[i])) for i,key in enumerate(classes)})
            torch.save(dict(ckpt,state_dict=network.state_dict(),metrics=metrics), args.output)
            print("Candidate", epoch, best, flush=True)
        head.train()
        for batch in torch.randperm(len(y)).split(24):
            optimizer.zero_grad()
            loss_fn(head(x[batch]), y[batch]).backward()
            optimizer.step()
    report = dict(classes=classes, best_validation_accuracy=best[0], best_balanced_accuracy=best[1], history=history, train=[r["path"] for r in train],validation=[r["path"] for r in val],selection_metric="validation accuracy with baseline balanced accuracy floor", caveat="Small validation set used for model selection.")
    args.output.with_suffix(".report.json").write_text(json.dumps(report,indent=2),encoding="utf8")


if __name__ == "__main__":
    main()
