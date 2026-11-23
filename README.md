# Paper Radar

每日追踪 arXiv 上 **智能座舱**（舱内感知、驾驶员状态、车载语音/多模态助手、人机交互）与 **具身智能**（VLA、机器人操作与学习、人形、世界模型、仿真到真实等）方向的新论文，并标注作者单位包含 **清华大学 / 北京大学 / 北京航空航天大学** 的论文。

- 网站：`site/`（纯静态，无外部依赖），由 GitHub Pages 发布
- 数据：`data/papers.json`（累积库），`data/state.json`（上次运行时间）
- 流水线：`python run.py`（见 `RUNBOOK.md`）
- 每日自动更新：`.github/workflows/daily.yml`

## 工作方式
1. **检索**：arXiv API，按提交日期窗口（上次运行前 4 天至今，首次 7 天）检索 cs.RO 全量 + 关键词查询（具身、座舱），再用本地规则分类（`radar/arxiv.py`, `radar/config.py`）。
2. **去重**：按 arXiv ID 与 `data/papers.json` 对比。
3. **机构解析**（`radar/affil.py`）：arXiv 元数据 → 论文 PDF 前两页（pdftotext，作者上标与单位编号对应）→ OpenAlex（按 DOI `10.48550/arXiv.<id>`，提供逐作者机构）。新论文在 OpenAlex 中通常有数天延迟，未解析完整的论文会在之后 14 天内自动复查。
4. **摘要**：自动抽取摘要中的关键句（"we propose…"）+ 中文关键词标签；`data/zh_summaries.json` 中可写入人工中文简介（id → 文本），重建时自动合并。
5. **输出**：`site/`（网站），`out-digest/latest.html|txt`（每日邮件正文，本地生成，不入库）。

人工修正：把误收论文的 ID 加入 `data/rejected_ids.json` 即会从库与网站中移除。
