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
→ 复查近 14 天未解析完整的论文 → 计算推荐度 / 挑选当天“重点推荐”（与网站已有的当天推荐保持一致）
→ 重建本地 `site/` → 生成邮件 `out-digest/latest.html|.txt|.json`（文件名、命令与之前完全相同）。
通常 10 秒–4 分钟。日志：`data/run.log`。退出码非 0 表示失败（看日志最后几行）。

然后：

1. **读取** `out-digest/latest.json`：`subject`（邮件主题）、`ids`（本封邮件包含的论文）、`flagged`、`counts`、
   `picks`（重点推荐，最多 5 篇，每篇含 `line` 一句话、`solve` 解决什么、`why` 为什么可落地、`use` 可以用来做、`rec` 推荐度）。
2. **若 `ids` 为空**（周六、周日 arXiv 不发布）：不发邮件，直接结束（不要运行 `--mark-sent`）。
3. **（推荐）中文简介**：优先给 `picks` 里还没有中文简介的论文写（推荐理由里的“解决什么”会直接用它，否则显示英文要点），
   其次是 `flagged` 中的论文以及邮件里列出的其他论文。依据摘要写 1–2 句忠实、通俗的中文简介（写清它做了什么、关键数字），
   合并进 `data/zh_summaries.json`（`{"2611.12345": "……"}`），然后
   ```bash
   python3 run.py --rebuild
   ```
   （不写也可：邮件和网站显示“[中文关键词标签] + 摘要原文关键句”。）
4. **发邮件**：收件人按 routine 配置；主题 = `latest.json` 的 `subject`；HTML 正文 = `out-digest/latest.html` 的全文；纯文本备选 = `out-digest/latest.txt`。
   邮件结构：数量统计 + 网站链接 → **★ 重点推荐（3–5 篇，附通俗推荐理由）** → 其余清华/北大/北航论文（学校与作者高亮）
   → 座舱（最多 8 篇）→ 端侧部署与智能体（最多 8 篇）→ 具身（最多 10 篇），均按推荐度排序，其余注明“见网站”。
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

## 推荐度与重点推荐（`radar/interest.py`）
- **方向**：除“智能座舱”“具身智能”外，新增第三个方向“端侧·智能体”（`edge`）：端侧/车载/机器人芯片上的模型部署、量化压缩与推理加速、智能体记忆、跨设备协同（分类规则在 `radar/arxiv.py` `classify` 与 `radar/config.py` 的 `EDGE_*`/`AGENT*`/`CROSS_DEVICE`）。
- **推荐度 `interest.rec`**（每篇都有，网站卡片显示“推荐度 N”）= 兴趣权重（端侧部署 3、智能体记忆 3、跨设备协同 3、模型压缩/加速 2.5、座舱交互 2、智能体 1.5、VLA 1.5、世界模型/机器人操作 1、导航/人形 0.8；标题命中加成，单次顺带提及不计）
  ＋ 可落地信号（公开代码/项目页 +2、真实设备/真机/实车实验 +2、延迟/显存等数据 +1.5、面向部署 +1.5、免训练/即插即用 +1、基于开源模型 +0.5）
  ＋ 清北航 +1.5、顶会/期刊 +1；偏理论且缺少实验 ×0.6（降权但保留，卡片标“偏理论”）。
- **重点推荐**：每次抓取后，从本次新论文 + 当天已有推荐中挑 3–5 篇（推荐度 ≥ 5，同一兴趣方向最多 2 篇），写入论文的 `pick` 字段 `{date, rank, line, solve, why, use}`（date = 北京时间运行日期）。推荐理由由规则生成；有中文简介时“解决什么”直接使用中文简介。
- **一致性**：GitHub Action（09:10）先挑当天推荐并发布；box 09:30 `--sync` 时以网站已有的当天推荐为准，再把 box 自己新抓到的论文并入重新挑选。邮件里的“重点推荐”= 本封邮件论文中带 `pick` 的论文，最多 5 篇（多天未发时按推荐度并兼顾方向多样性选 5 篇）。
- **网站**：顶部“最新重点推荐”（最近一天，不足 3 篇时连同前一天）；“★ 重点推荐”视图 = 全部往期推荐（`site/data/picks.json`），可按方向（座舱/具身/端侧·智能体）和兴趣标签（端侧部署、模型压缩/加速、智能体记忆、跨设备协同……）筛选，URL 例：`#v=picks&i=memory`。
- 调整权重：改 `radar/interest.py` 的 `INTERESTS` / `SIGNALS`，然后 `python3 run.py --rebuild`（只刷新推荐度与理由文字，不改已有推荐）；要按新规则重新挑选全部往期推荐用 `python3 run.py --rebuild --reseed-picks`（按论文提交日分组重挑，慎用）。

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
| `python3 run.py --rebuild --reseed-picks` | 按当前规则重新挑选全部往期重点推荐（慎用） |
| `gh workflow run daily-update -R ctao7271-a11y/paper-radar` | 手动触发网站更新 |
| `gh run list -R ctao7271-a11y/paper-radar` | 查看网站更新运行记录 |

## 智能座舱召回（2026-11-24 调整）
- 座舱是小众方向：按 2026-08-26～11-24 的 90 天回溯，arXiv 上真正与舱内/驾驶员/车载交互相关的新论文约 40 篇（每周 3～4 篇），远少于具身（每天全量抓取 cs.RO）。
- 抓取：RSS 增加 eess.SP；API 查询 `cockpit_kw`（扩充的短语）、`cockpit_hci`、`cockpit_title`（标题含 driver/vehicle/car/cabin/cockpit/passenger/occupant，限定 cs.HC/CV/CL/RO/AI/LG、eess.SP/AS/IV、cs.SD/MM）。
- 分类（`radar/arxiv.py` + `radar/config.py`）：强短语（舱内、车载助手/智能体、信息娱乐、AR-HUD、驾驶员状态/视线/情绪/负荷、接管、乘客 EEG/生理信号等）+ 句级共现；纯自动驾驶感知/规划、交通行为建模、车联网、保险遥测、楼宇“occupant”等排除。一篇论文可同时属于座舱与端侧/具身（多标签）。
- 一次性回溯：`python3 run.py --backfill-cockpit 90 --no-digest`。回溯论文 `first_seen` = arXiv 日期、带 `backfill: true`，并写入本地 `digested_ids.json`——只在网站显示，不进邮件、不参与当天重点推荐。

## 机构解析说明
- 顺序：arXiv 元数据 → PDF 首页（普通文本 + `-layout` 文本，按作者上标与单位编号/列位置对应；“X is with … University” 脚注；所有单位同校则全员；邮箱前缀）→ OpenAlex（仅在 PDF 无法定位具体作者时补充；新论文常延迟，且有时把所有机构赋给所有作者，故优先级最低）。
- 匹配：清华（Tsinghua University / 清华大学 / tsinghua.edu.cn / Tsinghua SIGS / IIIS / AIR），北大（Peking University / PKU / 北京大学 / pku.edu.cn），北航（Beihang / BUAA / Beijing University of Aeronautics and Astronautics / 北京航空航天大学 / buaa.edu.cn）。裸缩写只在摘要前的作者区有效；排除 “Tsinghua-Tencent 100K”、“Peking Union Medical College” 等。
- 学校识别到但具体作者对不上时显示“作者待确认”，之后 14 天内自动复查。

## 故障排查
- arXiv API 429 限流：自动退避；仍失败则只用 RSS 继续，不中断。漏掉的日子在下次运行时按“上次运行前 4 天”回补。
- `--sync` 失败（网络 / GitHub 不可达）会跳过并继续，本地抓取照常进行。
- 网站没更新：`gh run list -R ctao7271-a11y/paper-radar` 查看 `daily-update` 是否失败；可 `gh workflow run daily-update -R ctao7271-a11y/paper-radar` 重跑。

## 阅读清单、云同步与打开次数（网站前端）
- 每张卡片左上角有“阅读清单”勾选框；勾选的论文进入“阅读清单”视图（`#v=mine`，导航显示数量），可按加入时间（新/旧）或打开次数排序、按已读/未读筛选、标记“已读”、移除；“导出”下载 JSON 备份，“导入”合并。
- **云同步（Supabase）**：项目 `paper-radar`，ref `gabsjglbryeftyolopev`，区域 ap-southeast-1（新加坡），免费档。前端只内置 publishable/anon key（`radar/assets/app.js` 顶部），**绝不放 service_role key**。
  - 点右上角“登录同步”→ 输入邮箱 → 点邮件里的登录链接（每台设备一次）。若链接跳到别的地址，把整条链接（或邮件里的验证码）粘贴回对话框即可登录。
  - 首次在某台设备登录：本地清单与云端取并集（加入时间取最早，已读取“或”），之后勾选/已读/移除都即时写云端；离线时写本地并排队，下次联网同步。退出登录后本地清单保留。
  - 只有白名单邮箱能注册/使用：`public.allowed_users`（RLS 拒绝所有直接访问）+ `auth.users` 上的 BEFORE INSERT 触发器 `private.enforce_signup_allowlist`；`reading_list` 的 RLS 为 `auth.uid() = user_id and private.is_allowed()`。增加可同步邮箱：在 SQL 编辑器执行 `insert into public.allowed_users(email) values ('<email>');`
  - 建议在 Supabase 控制台 Authentication → URL Configuration 把 Site URL 与 Redirect URLs 设为 `https://ctao7271-a11y.github.io/paper-radar/`（否则邮件链接可能指向默认地址，需要粘贴回对话框）。
- **打开次数（全站总计）**：卡片上只显示一个数字“打开 N 次”= 所有访客点击标题、arXiv 或 PDF 链接的总次数（事件委托，不拦截跳转，中键也算）。表 `public.global_clicks(arxiv_id, count, updated_at)`；匿名访客只能 SELECT 和调用 SECURITY DEFINER 函数 `increment_global_click(p_arxiv_id)`（校验 ID 格式与长度），不能直接写表。同一浏览器同一篇 30 秒内只计一次（客户端限流）。连接不上 Supabase 时不显示数字。
  - 修正误计数：`update public.global_clicks set count = greatest(count - <n>, 0) where arxiv_id = '<id>';`
- 视觉（Aurora 浅色主题，2026-11-24 晚）：画布 #F7F6FC、卡片 #FFFFFF、墨色 #1E1B3A、次要文字 #5B5878/#8A87A3、细线 #E7E4F3/#D6D1EA；紫 #7C5CFC（文字用 #6D28D9）、粉 #EC4899（文字用 #DB2777）、蓝 #3B82F6（文字用 #2563EB）、靛 #6366F1；渐变 粉→紫（总数卡、重点推荐、已勾选）、紫→蓝（推荐度、已读、占比条）。弱投影、圆角卡片、胶囊按钮，顶部有 arXiv→三方向的流向图。样式在 `radar/assets/style.css`（构建时复制到 `site/`）；supabase-js 本地化为 `radar/assets/supabase-2.119.2.js`。
- 自测：`/workspace/pwenv/bin/python tests/test_reading_list.py <url> <tag> [测试邮箱 测试密码]`。注意脚本的点击会真实计入全站次数，结束时打印 `GLOBAL_CLICK_DELTAS`，按上面的 SQL 扣回。

## AI 论文助手（对话框，2026-11-25）
- **入口**：右下角“✦ 问 AI”浮动按钮 → 右侧滑出面板（手机为全屏）；每张卡片也有“✦ 问 AI”按钮（直接让 AI 分析这一篇）。回答里的 arXiv 编号是可点的胶囊（打开 arXiv，计入打开次数），下方“引用的论文”列表的“定位”按钮会滚动并高亮页面上的卡片。对话记录只存在本浏览器（localStorage `paperRadar.chat.v1`，最近 20 条），“新对话”清空。
- **只有登录用户能用**：未登录时面板显示“登录后即可使用”；服务端校验 Supabase 登录会话（JWT）+ 白名单（`private.is_allowed()`），匿名/publishable key/伪造 token 一律 401，非白名单 403。
- **架构**：前端 `radar/assets/chat.js`（构建时复制到 `site/`）→ Supabase Edge Function **`paper-chat`**（源码 `supabase/functions/paper-chat/index.ts`，`verify_jwt=false`，鉴权在代码里做，以便处理 CORS 预检）→ DeepSeek `deepseek-chat`（流式）。**LLM 密钥只在服务端**，网页里没有。
  - 检索：函数从 GitHub Pages 读取 `data/manifest.json` 和各月份 JSON（缓存 10 分钟，所以每日更新后自动可检索），对标题×3、中文摘要×2、标签×2、英文摘要、作者做 BM25（中文按双字切分 + 常用中→英同义词扩展），再按方向、清北航、重点推荐、推荐度、“最近”类问题的时间加权，取前 12 篇（连同卡片上点的那篇、上一轮回答里引用的论文）作为上下文。
  - 回答规则（system prompt）：用提问的语言回答；只依据摘要，不编造；每个结论标 arXiv 编号；库里没有相关论文就直说。多轮：带最近 6 条消息。
  - 返回 NDJSON 流：`refs`（检索到的论文 + 当日额度）→ `delta`（逐段文字）→ `done`；出错为 `error`。
- **额度**：每个账号每天（北京时间）最多 60 次（`public.chat_take_quota(p_limit)`，硬上限 200），用量和 token 数记在 `public.chat_usage(user_id, day, n, tokens)`。调额度：改 `index.ts` 里的 `p_limit` 后重新部署。查用量：`select * from public.chat_usage order by day desc;`
- **密钥（DeepSeek API key）设置 / 轮换** —— 永远不要写进代码、提交或打印：
  1. Supabase 控制台 → 项目 `paper-radar` → Edge Functions → **Secrets**（或 Project Settings → Edge Functions）→ Add new secret：Name `DEEPSEEK_API_KEY`，Value 粘贴 key → Save。立即生效，无需重新部署。
  2. 轮换：在 DeepSeek 控制台（platform.deepseek.com → API keys）新建 key → 在上面同一处把 `DEEPSEEK_API_KEY` 的值改成新 key → 在面板问一句确认正常 → 回 DeepSeek 删除旧 key。
  3. 备选：函数在没有环境变量时会读 Supabase Vault 中名为 `deepseek_api_key` 的密钥（`public.chat_llm_key()`，仅 service_role 可调用）。
  - 未配置密钥时，面板仍会显示检索到的论文，并提示“AI 服务尚未配置密钥”。
- **费用**：DeepSeek 按 token 计费，一次问答约 5–6k token（≈ ¥0.02）。余额不足时会返回错误提示；在 DeepSeek 控制台充值即可。
- **重新部署函数**：用 Supabase MCP `deploy_edge_function`（name `paper-chat`，`verify_jwt: false`，文件 `index.ts`），或 CLI `supabase functions deploy paper-chat --no-verify-jwt --project-ref gabsjglbryeftyolopev`。
- **本地调试**：`cd supabase/functions/paper-chat && SUPABASE_URL=https://gabsjglbryeftyolopev.supabase.co SUPABASE_ANON_KEY=<anon key> SUPABASE_SERVICE_ROLE_KEY=unused deno run --allow-net --allow-env index.ts`（`DEEPSEEK_API_KEY` 从环境继承，监听 :8000）。
