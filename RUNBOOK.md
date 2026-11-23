# Paper Radar · 每日运行手册 (RUNBOOK)

- 仓库：https://github.com/ctao7271-a11y/paper-radar （公开）
- 网站：https://ctao7271-a11y.github.io/paper-radar/ （GitHub Pages，来源 = GitHub Actions）
- box 工作目录：`/workspace/paper-radar/`（流水线 + 本地库 + 邮件输出）
- box 上的 git 克隆：`/workspace/paper-radar/repo-bundle/`（只在推送代码 / 中文简介时使用）

## 分工

| 部分 | 在哪里跑 | 时间（北京时间） | 做什么 |
|---|---|---|---|
| 网站更新 | GitHub Actions `daily-update`（`.github/workflows/daily.yml`） | 每天 09:10（cron `10 1 * * *` UTC，GitHub 可能延迟 5–30 分钟） | 抓取 → 解析机构 → 提交 `data/` `site/` → 发布 Pages。无需 box 参与。 |
| 邮件摘要 | box 定时 routine | 每天 09:30 | 同步网站数据 + 自行抓取补漏 → 生成邮件 → 发送 → 标记已发送 |

## 每日 routine 步骤（box，09:30）

```bash
cd /workspace/paper-radar
python3 run.py --sync https://raw.githubusercontent.com/ctao7271-a11y/paper-radar/main/data/papers.json
```
该命令：合并仓库里的累积库 → 用 arXiv RSS（必要时 API 补缺）抓新论文 → 去重 → 解析作者机构（PDF 首页 + OpenAlex）
→ 复查近 14 天未解析完整的论文 → 重建本地 `site/` → 生成邮件 `out-digest/latest.html|.txt|.json`。
通常 10 秒–4 分钟。日志：`data/run.log`。退出码非 0 表示失败（看日志最后几行）。

然后：

1. **读取** `out-digest/latest.json`：`subject`（邮件主题）、`ids`（本封邮件包含的论文）、`flagged`、`counts`。
2. **若 `ids` 为空**（周六、周日 arXiv 不发布）：不发邮件，直接结束（不要运行 `--mark-sent`）。
3. **（可选）中文简介**：对 `flagged` 中的论文以及邮件里列出的其他论文，依据摘要写 1–2 句忠实的中文简介，
   合并进 `data/zh_summaries.json`（`{"2611.12345": "……"}`），然后
   ```bash
   python3 run.py --rebuild
   ```
   （不写也可：邮件和网站显示“[中文关键词标签] + 摘要原文关键句”。）
4. **发邮件**：收件人按 routine 配置；主题 = `latest.json` 的 `subject`；HTML 正文 = `out-digest/latest.html` 的全文；纯文本备选 = `out-digest/latest.txt`。
   邮件结构：数量统计 + 网站链接 → 全部清华/北大/北航论文（学校与作者高亮）→ 座舱（最多 10 篇）→ 具身（按相关度最多 12 篇），其余注明“见网站”。
5. **发送成功后**：
   ```bash
   python3 run.py --mark-sent
   ```
   （只在确认发送成功后运行；未发送就不要运行，第二天会连同新论文一起再发。邮件只包含 4 天内首次收录且未发送过的论文。）
6. **（可选）把中文简介同步到网站**（只有第 3 步写了简介才需要）：
   ```bash
   cd /workspace/paper-radar/repo-bundle && git pull -q --rebase origin main \
     && cp ../data/zh_summaries.json data/ && git add data/zh_summaries.json \
     && (git diff --cached --quiet || (git commit -qm "zh summaries $(date +%F)" && git push -q))
   ```
   推送会自动触发 `daily-update`（`--rebuild` 模式），约 1 分钟后网站更新。

## 修改代码 / 规则后发布

规则在 `radar/config.py`（查询词、关键词、学校匹配）与 `radar/arxiv.py`（`classify`）。改完在 box 上 `python3 run.py --rebuild` 验证，然后：
```bash
cd /workspace/paper-radar/repo-bundle && git pull -q --rebase origin main
cp -r ../radar ../run.py ../RUNBOOK.md ../README.md . && rm -rf radar/__pycache__
cp ../data/zh_summaries.json ../data/rejected_ids.json data/
git add -A && git commit -m "update pipeline" && git push
```
误收论文：把 arXiv ID 加入 `data/rejected_ids.json`，按上面方式推送即可从网站移除。

## 常用命令

| 命令 | 作用 |
|---|---|
| `python3 run.py --sync <raw url>` | 每日运行（见上） |
| `python3 run.py` | 不同步，只本地抓取 + 生成 |
| `python3 run.py --rebuild` | 只重建网站与邮件（改了简介/剔除名单/规则后） |
| `python3 run.py --mark-sent` | 记录当前邮件已发送 |
| `gh workflow run daily-update -R ctao7271-a11y/paper-radar` | 手动触发网站更新 |
| `gh run list -R ctao7271-a11y/paper-radar` | 查看网站更新运行记录 |

## 机构解析说明
- 顺序：arXiv 元数据 → PDF 首页（普通文本 + `-layout` 文本，按作者上标与单位编号/列位置对应；“X is with … University” 脚注；所有单位同校则全员；邮箱前缀）→ OpenAlex（仅在 PDF 无法定位具体作者时补充；新论文常延迟，且有时把所有机构赋给所有作者，故优先级最低）。
- 匹配：清华（Tsinghua University / 清华大学 / tsinghua.edu.cn / Tsinghua SIGS / IIIS / AIR），北大（Peking University / PKU / 北京大学 / pku.edu.cn），北航（Beihang / BUAA / Beijing University of Aeronautics and Astronautics / 北京航空航天大学 / buaa.edu.cn）。裸缩写只在摘要前的作者区有效；排除 “Tsinghua-Tencent 100K”、“Peking Union Medical College” 等。
- 学校识别到但具体作者对不上时显示“作者待确认”，之后 14 天内自动复查。

## 故障排查
- arXiv API 429 限流：自动退避；仍失败则只用 RSS 继续，不中断。漏掉的日子在下次运行时按“上次运行前 4 天”回补。
- `--sync` 失败（网络 / GitHub 不可达）会跳过并继续，本地抓取照常进行。
- 网站没更新：`gh run list -R ctao7271-a11y/paper-radar` 查看 `daily-update` 是否失败；可 `gh workflow run daily-update -R ctao7271-a11y/paper-radar` 重跑。
