# Paper Radar

每日追踪 arXiv 上 **智能座舱**（舱内感知、驾驶员状态、车载语音/多模态助手、人机交互）、**具身智能**（VLA、机器人操作与学习、人形、世界模型、仿真到真实等）与 **端侧部署·智能体**（端侧/车载/机器人芯片上的模型部署、量化压缩与推理加速、智能体记忆、跨设备协同）方向的新论文，按“研究兴趣 + 可落地程度”打推荐度、每天挑出 3–5 篇 **重点推荐**（附通俗推荐理由），并标注作者单位包含 **清华大学 / 北京大学 / 北京航空航天大学** 的论文。

- 网站：`site/`（纯静态，无外部依赖），由 GitHub Pages 发布
- 数据：`data/papers.json`（累积库），`data/state.json`（上次运行时间）
- 流水线：`python run.py`（见 `RUNBOOK.md`）
- 每日自动更新：`.github/workflows/daily.yml`

## 工作方式
1. **检索**：每日 arXiv RSS（cs.RO/AI/CV/CL/HC/LG/MA/AR/DC 等分类）为主，必要时用 arXiv API 按日期窗口补缺（cs.RO 全量 + 具身、座舱、端侧/智能体关键词查询），再用本地规则分类（`radar/arxiv.py`, `radar/config.py`）。
2. **去重**：按 arXiv ID 与 `data/papers.json` 对比。
3. **机构解析**（`radar/affil.py`）：arXiv 元数据 → 论文 PDF 前两页（pdftotext，作者上标与单位编号对应）→ OpenAlex（按 DOI `10.48550/arXiv.<id>`，提供逐作者机构）。新论文在 OpenAlex 中通常有数天延迟，未解析完整的论文会在之后 14 天内自动复查。
4. **摘要**：自动抽取摘要中的关键句（"we propose…"）+ 中文关键词标签；`data/zh_summaries.json` 中可写入人工中文简介（id → 文本），重建时自动合并。
5. **推荐度与重点推荐**（`radar/interest.py`）：兴趣权重（端侧部署、模型压缩/加速、智能体记忆、跨设备协同、座舱交互、具身智能）+ 可落地信号（公开代码、真机/实车实验、延迟/显存数据、面向部署、即插即用），偏理论工作降权但保留；每天挑 3–5 篇，规则生成“解决什么 / 为什么可落地 / 可以用来做 / 一句话”。往期推荐见网站“★ 重点推荐”视图（`site/data/picks.json`）。
6. **输出**：`site/`（网站），`out-digest/latest.html|txt`（每日邮件正文，本地生成，不入库）。

人工修正：把误收论文的 ID 加入 `data/rejected_ids.json` 即会从库与网站中移除。
