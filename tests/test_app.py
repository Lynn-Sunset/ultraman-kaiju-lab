import io
import json
from pathlib import Path

import pytest
import torch
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import MAX_BYTES, ROOT, create_app
from backend.catalog import BY_ID
from backend.model import ARCHITECTURE, build_model, decode_image
from train import split_samples


def photo_bytes(mode="RGB", format="PNG"):
    buffer = io.BytesIO()
    Image.new(mode, (80, 120)).save(buffer, format=format)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    # An explicitly synthetic fixture tests checkpoint label order and scores.
    path = tmp_path_factory.mktemp("model") / "fixture.pt"
    network = build_model(2)
    for parameter in network.parameters():
        parameter.data.zero_()
    network.classifier[-1].bias.data[1] = 2.
    torch.save(dict(architecture=ARCHITECTURE, classes=["zetton", "gomora"], state_dict=network.state_dict()), path)
    with TestClient(create_app(path)) as test_client:
        yield test_client


def test_prediction_preserves_checkpoint_labels_and_returns_normalized_ranking(client):
    response = client.post("/api/classify", files={"file": ("portrait.png", photo_bytes(), "image/png")})
    assert response.status_code == 200
    body = response.json()
    assert body["winner"]["id"] == "gomora"
    assert body["ranking"][0]["score"] == pytest.approx(.880797, abs=1e-5)
    assert sum(r["score"] for r in body["ranking"]) == pytest.approx(1.)
    assert body["winner"]["abilities"]
    assert "娱乐" in body["notice"]
    assert body["mode"] == "model"


@pytest.mark.parametrize("payload", [b"not an image", b"<svg></svg>"])
def test_rejects_disguised_images(client, payload):
    response = client.post("/api/classify", files={"file": ("fake.jpg", payload, "image/jpeg")})
    assert response.status_code == 400


def test_empty_and_oversized_uploads(client):
    assert client.post("/api/classify", files={"file": ("empty.png", b"", "image/png")}).status_code == 400
    assert client.post("/api/classify", files={"file": ("large.png", b"x" * (MAX_BYTES + 1), "image/png")}).status_code == 413


def test_absent_model_has_explicit_unavailable_status(tmp_path):
    with TestClient(create_app(tmp_path / "absent.pt")) as client:
        assert client.get("/api/status").json()["ready"] is False
        assert client.post("/api/classify", files={"file": ("photo.png", photo_bytes(), "image/png")}).status_code == 503


def test_corrupt_checkpoint_does_not_crash_the_site(tmp_path):
    path = tmp_path / "corrupt.pt"
    path.write_bytes(b"invalid checkpoint")
    with TestClient(create_app(path)) as client:
        assert client.get("/").status_code == 200
        status = client.get("/api/status").json()
        assert not status["ready"]
        assert "加载失败" in status["message"]


def test_transparency_and_supported_formats():
    image = decode_image(photo_bytes("RGBA"))
    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (255, 255, 255)
    with pytest.raises(ValueError):
        decode_image(photo_bytes(format="GIF"))


def test_real_dataset_has_reviewed_labels_and_no_group_leakage():
    rows = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    classes, training, validation = split_samples(rows)
    assert set(classes) == set(BY_ID)
    assert all(r["review_status"] == "accepted" for r in training + validation)
    assert set(r["source_group"] for r in training).isdisjoint(r["source_group"] for r in validation)
    assert set(r["class_id"] for r in training) == set(classes)
    assert set(r["class_id"] for r in validation) == set(classes)
    assert split_samples(rows)[1:] == (training, validation)


def test_trained_checkpoint_and_every_archive_photo():
    path = ROOT / "models" / "monster.pt"
    if not path.is_file():
        pytest.skip("Train the real seed model first")
    with TestClient(create_app(path)) as client:
        assert client.get("/api/status").json()["ready"]
        for monster in client.get("/api/monsters").json():
            image = client.get(f"/portraits/{monster['id']}.jpg")
            assert image.status_code == 200
            result = client.post("/api/classify", files={"file": ("reference.jpg", image.content, "image/jpeg")})
            assert result.status_code == 200
            ranking = result.json()["ranking"]
            assert {row["monster"]["id"] for row in ranking} == set(BY_ID)
            assert result.json()["winner"]["id"] == ranking[0]["monster"]["id"]


def test_catalog_is_complete_and_has_unique_translated_profiles():
    assert len(BY_ID) >= 30
    assert len({m["name"] for m in BY_ID.values()}) == len(BY_ID)
    for key, monster in BY_ID.items():
        assert monster["id"] == key
        assert len(monster["abilities"]) >= 3
        assert monster["description"]
        assert monster["source"].startswith("https://tsuburaya-prod.com/encyclopedia/")
        assert monster["era"] in {"昭和", "平成", "新生代"}

