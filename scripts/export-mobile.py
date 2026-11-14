"""Describe this MobileNet graph for the lightweight browser worker."""
import json
from pathlib import Path
import onnx
from onnx import helper

web = Path(__file__).resolve().parents[1] / "web"
raw = (web / "models/monster.onnx").read_bytes()
model = onnx.load_from_string(raw)
weights = {}
for tensor in model.graph.initializer:
    offset = raw.find(tensor.raw_data)
    assert tensor.data_type == onnx.TensorProto.FLOAT and offset >= 0
    weights[tensor.name] = [offset, list(tensor.dims)]
graph = []
for node in model.graph.node:
    attrs = {a.name: helper.get_attribute_value(a) for a in node.attribute}
    assert node.op_type in {"Conv","Relu","HardSwish","HardSigmoid","GlobalAveragePool","Gemm","Flatten","Mul","Add"}
    if node.op_type == "Conv":
        assert attrs["dilations"] == [1,1] and attrs["strides"][0] == attrs["strides"][1] and len(set(attrs["pads"])) == 1
    if node.op_type == "Gemm":
        assert attrs == {"alpha":1,"beta":1,"transB":1}
    graph.append([node.op_type,list(node.input),node.output[0],attrs])
import hashlib
(web / "data/mobile-graph.json").write_text(json.dumps(dict(sha256=hashlib.sha256(raw).hexdigest(), weights=weights,graph=graph),separators=(",",":")),encoding="utf8")
