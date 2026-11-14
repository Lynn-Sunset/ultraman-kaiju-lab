import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import torch
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .catalog import MONSTERS
from .model import Classifier

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 10 * 1024 * 1024


def create_app(model_path=None):
    classifier = Classifier(model_path or os.getenv("KAIJU_MODEL_PATH", ROOT / "models" / "monster.pt"))

    @asynccontextmanager
    async def lifespan(app):
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        await run_in_threadpool(classifier.load)
        yield

    app = FastAPI(title="KAIJU LAB · 怪兽研究所", lifespan=lifespan)
    app.state.classifier = classifier

    @app.get("/api/status")
    def status():
        return dict(ready=classifier.ready, classes=classifier.classes, architecture="MobileNetV3 Small", message=classifier.error or ("原型模型已就绪" if classifier.ready else "等待训练权重"), metrics=classifier.metadata)

    @app.get("/api/monsters")
    def monsters():
        return MONSTERS

    @app.get("/api/dataset")
    def dataset():
        manifest = ROOT / "data" / "manifest.json"
        if not manifest.is_file():
            return {"total": 0, "reviewed": 0, "classes": {}}
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        return dict(total=len(rows), downloaded=sum(not r.get("derived_from") for r in rows), derived=sum(bool(r.get("derived_from")) for r in rows), reviewed=sum(r.get("review_status") == "accepted" for r in rows), classes={m["id"]: sum(r["class_id"] == m["id"] and r.get("review_status") == "accepted" for r in rows) for m in MONSTERS})

    @app.post("/api/classify")
    async def classify(file: UploadFile):
        try:
            raw = await file.read(MAX_BYTES + 1)
        finally:
            await file.close()
        if not raw:
            raise HTTPException(400, "图片是空的。")
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "图片大小不能超过 10 MB。")
        if not classifier.ready:
            raise HTTPException(503, classifier.error or "模型尚未就绪。请完成数据审核并运行训练脚本，然后重启服务。")
        try:
            return await run_in_threadpool(classifier.predict, raw)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/")
    def index():
        return FileResponse(ROOT / "web" / "index.html")

    app.mount("/assets", StaticFiles(directory=ROOT / "web"), name="assets")
    app.mount("/portraits", StaticFiles(directory=ROOT / "web" / "portraits", check_dir=False), name="portraits")
    app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="browser-app")
    return app


app = create_app()
