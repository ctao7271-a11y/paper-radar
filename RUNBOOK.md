# Paper Radar · 每日运行手册 (RUNBOOK)

目标：每天 09:30（北京时间）把当天的座舱/具身新论文摘要发到用户邮箱，并让网站累积更新。

## 架构（两条线，互不依赖）

| 部分 | 在哪里跑 | 做什么 |
|---|---|---|
| 网站更新 | GitHub Actions（仓库 `.github/workflows/daily.yml`，每天 01:10 UTC = 09:10 北京时间） | `python run.py --no-digest` → 提交 `data/` `site/` → 发布 GitHub Pages |
| 邮件摘要 | 本机 box（定时 routine，09:30 北京时间） | `python3 run.py --sync <raw papers.json>` → 生成 `out-digest/latest.html/.txt` → 发邮件 → `--mark-sent` |

> 为什么网站更新放在 GitHub Actions：box 上的 `gh` 未登录，Cursor 内置的 GitHub 工具（cursor-github）只能读仓库/评论/PR，**不能创建仓库、不能推送文件、不能开启 Pages**。
> 因此每日推送改由仓库自己的 Action 完成（用仓库自带的 GITHUB_TOKEN，无需任何密钥）。box 端不需要推送任何东西。

## 每日步骤（routine 照做即可）

```bash
cd /workspace/paper-radar
# 1) 先同步网站上的累积库（仓库公开，匿名可读；仓库尚未建好时这一步会自动跳过）
python3 run.py --sync https://raw.githubusercontent.com/ctao7271-a11y/paper-radar/main/data/papers.json
#    该命令同时会：检索 arXiv 新论文（RSS + 必要时 API 补缺）→ 去重 → 解析作者机构（PDF 首页 + OpenAlex）
#    → 复查近 14 天未解析完整的论文 → 重建 site/ → 生成邮件 out-digest/latest.html|.txt|.json
#    耗时：通常 1–4 分钟（每篇新论文下载一次 PDF）。日志：data/run.log
```

2) （可选，推荐）写中文简介：读 `out-digest/latest.json` 里的 `ids`，对其中**清北航论文 + 邮件里列出的论文**，
   依据摘要写 1–2 句忠实的中文简介，写入 `data/zh_summaries.json`（`{"2611.12345": "……"}`），然后：
   ```bash
   python3 run.py --rebuild      # 不重新抓取，只合并中文简介、重建网站与邮件
   ```
   （不写也可以：邮件和网站会显示“[中文关键词标签] + 摘要原文关键句”。）

3) 发邮件：
   - 收件人：由 routine 配置（用户指定的工作邮箱）
   - 主题：`out-digest/latest.json` 的 `subject` 字段（例如“论文雷达 11月23日：座舱 3 篇 · 具身 280 篇 · 清北航 25 篇”）
   - 正文：`out-digest/latest.html`（HTML，内联样式）；纯文本备选 `out-digest/latest.txt`
   - 若 `latest.json` 的 `ids` 为空（周末 arXiv 不发布），可发一封“今日无新论文”的短邮件或跳过，按 routine 约定。

4) 发送成功后标记已发送（避免明天重复）：
   ```bash
   python3 run.py --mark-sent
   ```

5) 让网站也带上中文简介（可选）：网站由 GitHub Action 每天 09:10 自动更新，不依赖 box。
   box 上写的 `data/zh_summaries.json` 如需上网站，需要把该文件提交到仓库（见下文“推送文件”）。

## 推送文件到 GitHub（仅首次部署或修改代码时需要）

box 上没有可用的推送通道。可选做法：
- 用户在 GitHub 网页上 “Add file → Upload files”，把 `/workspace/paper-radar/repo-bundle/` 里的文件拖进去；或
- 由主助手启动 Cursor 云端代理（Cloud Agent）在该仓库里写入文件（仓库需先授权给 Cursor GitHub App）。

首次部署清单：
1. 用户在 GitHub 新建公开空仓库 `ctao7271-a11y/paper-radar`（Cursor 不能代建 GitHub 仓库），并在 Cursor GitHub App 的授权里加入该仓库。
2. 推送 `repo-bundle/` 的全部内容（含 `.github/workflows/daily.yml`、`data/papers.json` 首批数据、`site/`）。
3. 仓库 Settings → Pages → Build and deployment → Source 选 **GitHub Actions**（一次性，一键）。
4. 仓库 Actions 页手动运行一次 `daily-update`（或等次日 09:10），网址为 `https://ctao7271-a11y.github.io/paper-radar/`。
5. 写入站点地址：`echo '{"url": "https://ctao7271-a11y.github.io/paper-radar/"}' > data/site.json`（邮件里的网站链接用它）。

## 常用命令

| 命令 | 作用 |
|---|---|
| `python3 run.py` | 正常每日运行 |
| `python3 run.py --rebuild` | 只重建网站和邮件（改了中文简介/剔除名单后） |
| `python3 run.py --mark-sent` | 当前邮件已发出 |
| `python3 run.py --no-pdf` | 跳过 PDF 解析（更快，机构覆盖率下降） |
| `python3 -m http.server -d site 8000` | 本地预览网站 |

人工修正：
- 误收论文：把 arXiv ID 加入 `data/rejected_ids.json`（JSON 数组），`--rebuild` 后即移除。
- 检索词与分类规则：`radar/config.py`（查询、关键词、学校匹配）与 `radar/arxiv.py`（`classify`）。

## 机构解析说明
- 顺序：arXiv 元数据（极少有）→ PDF 前两页（作者上标编号 ↔ 单位编号；“X is with … University” 脚注；全体同单位）→ OpenAlex（按 DOI `10.48550/arXiv.<id>`，逐作者机构，新论文通常延迟数天到数周）。
- 匹配：清华（Tsinghua University / 清华大学 / tsinghua.edu.cn / Tsinghua SIGS / IIIS / AIR），北大（Peking University / PKU / 北京大学 / pku.edu.cn），北航（Beihang / BUAA / Beijing University of Aeronautics and Astronautics / 北京航空航天大学 / buaa.edu.cn）。裸缩写（PKU、BUAA、THU、Tsinghua）只在标题区（摘要之前）才算数；“Tsinghua-Tencent 100K”、“Peking Union Medical College” 等排除。
- 学校能识别但具体作者对不上时，显示“作者待确认”，并在之后 14 天内用 OpenAlex 复查。

## 故障排查
- arXiv API 返回 429（限流）：脚本会退避重试；仍失败时只用 RSS（当天公告）继续，不会中断。若某天整体失败，下一次运行会按“上次运行时间前 4 天”回补。
- 日志：`data/run.log`；运行状态：`data/state.json`。
