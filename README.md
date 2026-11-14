# 怪兽研究所 · KAIJU LAB

红白配色的奥特怪兽身份匹配小站。上传照片，在 30 类怪兽中取得最高分对应的身份和能力档案，支持保存 PNG 身份卡和复制结果。

[在线体验](https://lynn-sunset.github.io/ultraman-kaiju-lab/) · [GitHub 仓库](https://github.com/Lynn-Sunset/ultraman-kaiju-lab)

**照片只在访客自己的浏览器中处理，不上传到 GitHub 或 Python 服务。** 已训练的 MobileNetV3 模型通过 ONNX Runtime Web / WebAssembly 在 Web Worker 中运行，适合直接部署到 GitHub Pages。

## 本地预览发布版

需要 Node.js 22 或更新版本，以及 Python（仅用于本地静态文件服务）：

```powershell
npm ci --ignore-scripts --no-audit --no-fund
npm run build
python scripts/preview-pages.py
```

打开 <http://127.0.0.1:8010/ultraman-kaiju-lab/>。这与 GitHub 项目网站的子路径相同，可以验证所有相对路径、模型和 WASM 资源。不要直接双击 HTML 文件打开，模块、Worker、剪贴板等功能需要 HTTP/HTTPS 环境。

发布包在 `dist/`，约 22.1 MiB。模型约 6.2 MB，WASM 运行时约 14.8 MB；首次打开需要下载资源，后续缓存由浏览器和站点响应控制。只复制使用的 WASM 文件，运行时固定为 `onnxruntime-web@1.31.1`，开源许可证随发布包保留。

## GitHub Pages

`.github/workflows/pages.yml` 在 `main` 更新后自动：

1. 安装锁定版本的 npm 依赖。
2. 构建并核对 30 类图鉴、模型 SHA-256 和全部角色图片。
3. 上传静态资源并部署到 GitHub Pages。

仓库的 Settings → Pages → Source 使用 **GitHub Actions**。站点不需要 API Key、Python 后端或个人电脑保持运行。全部站点资源从同一个 Pages 地址加载。

正常修改页面后提交 `web/` 和相关源码即可。不要提交 `node_modules/`、`dist/`、`.venv/`、照片缓存、下载目录、个人截图或本机凭据。`scripts/github-publish.py` 是本项目首次发布辅助脚本，只使用已经登录的 Git 凭据管理器；令牌只存在于进程内存中，不写入仓库或命令参数。

## 功能

- 30 类怪兽真实模型推理、前五名及可展开的完整排名。
- 图鉴名称搜索、昭和/平成/新生代筛选、角色能力介绍。
- 1000×1320 红白 PNG 身份卡；卡片只含怪兽资料，不包含用户照片。
- 复制身份、得分和能力介绍；剪贴板权限不可用时提供手动复制文本。
- 手机与桌面布局；照片支持 JPG/PNG/WebP、最大 10 MB、2000 万像素。

## 模型与数据

使用 ImageNet 预训练 MobileNetV3 Small，冻结特征提取器，训练 30 分类头。下载并去重的候选图 295 张，另有一个带目标框的艾斯杀手裁剪样本；296 条标注中，154 张审核通过、142 张拒绝。裁剪图与原图共享来源组，不能算独立来源。

训练 114 张、验证 40 张，同一商品的不同角度整组划分。40 轮后按各类平均召回率选中第 36 轮：准确率 **50.0%（20/40）**，各类平均召回率 **48.3%**。验证集参与了模型选择，不是独立测试结果。某些类别只有两三张图片，当前仍是小样本原型。

真人照片属于怪兽训练分布之外。结果仅供娱乐，不构成真实身份、性格或能力判断；Softmax 得分未经概率校准。

| 文件 | 用途 |
| --- | --- |
| `web/models/monster.onnx` | 可公开部署的训练模型 |
| `web/data/model.json` | 权重类别顺序、校验值、预处理参数与模型指标 |
| `web/data/catalog.json` | 30 类角色资料 |
| `data/labels.csv` | 逐图标签、审核状态、理由、来源、裁剪关系 |
| `data/class-summary.csv` | 每类样本数量和验证表现 |
| `data/manifest.json` | 训练清单（原始图片不随公开仓库分发） |
| `models/monster.report.json` | 每轮损失、验证指标与划分清单 |

30 类覆盖：哥莫拉、巴尔坦星人、杰顿、艾雷王、雷德王、卡内贡、皮古蒙、金古桥、达达、内隆嘎、百慕拉、古维拉、安东拉、贾米拉、古敦、双尾怪、贝蒙斯坦、布莱克王、巴顿、泰兰特、艾斯杀手、巴克西姆、哥尔赞、美尔巴、加佐特、希尔巴贡、眼Q、加拉特隆、五帝王、梅特龙星人。

## 重新训练与导出

在本项目环境中安装 Python 训练和导出依赖：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-export.txt
```

原始训练图片不会发布到 GitHub。采集并完成视觉审核后才能训练：

```powershell
.venv/Scripts/python.exe collect_dataset.py
.venv/Scripts/python.exe collect_dataset.py --sheets-only
.venv/Scripts/python.exe review_dataset.py
.venv/Scripts/python.exe train.py --epochs 40
.venv/Scripts/python.exe summarize_dataset.py
.venv/Scripts/python.exe export_browser.py
npm run build
```

新图默认 pending，只有 accepted 图片进入训练。审核不能用搜索关键词或文件名代替。`review_expansion.py` 的具体决定仅适用于对应快照；图像变化后必须重新审核。默认权重在 `models/monster.pt`，本机旧六类版本仍保留但不随仓库发布。

导出采用 ONNX opset 18，三张参考图与 PyTorch 的最大 logits 差异约 `4.4e-5`。浏览器使用等价的短边缩放、中心裁剪和 ImageNet 归一化；Canvas 和 Pillow 的重采样实现不同，具体分数可能略有变化。导出后提交 `web/models/` 和 `web/data/`，供 Pages 直接使用；工作流不会重新训练。

## 检验

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=.test-tmp
npm run build
```

已实际检验浏览器模型加载与推理、项目子路径、身份卡 PNG 下载和复制后粘贴。Python 测试覆盖类别顺序、得分归一化、无效上传、权重缺失/损坏、来源分组隔离和全部 30 类角色。

`backend/app.py` 保留可选 FastAPI 推理接口；发布站点使用浏览器模型，不调用该接口。需要预览源文件时先运行 `npm run prepare:runtime`，再启动 `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`。

## 资料来源

角色与候选图片来自[圆谷官方怪兽图鉴](https://tsuburaya-prod.com/encyclopedialist)、[万代官方图库](https://toy.bandai.co.jp/ja/series/ultraman/sofubi/)及官方商品页，每张图片保留具体来源。角色和图片版权归原权利人所有，本项目为非官方同人实验。公开可访问不等于获得商业使用授权；商业用途应先确认相应权利或更换素材。
