# ERBS-plugin

[English](../README.md) · [中文快速开始](QUICK_START.md)

ERBS-plugin 是面向中文互联网服务的机器人插件。用于查询《永恒轮回》公开数据、进行分析、输出 JSON、管理本地图片资源，并渲染 PNG 数据卡片。

本项目为个人开发项目，仅供**学习、交流与参考**，且不保证持续稳定更新。若有侵权或代码问题，请联系我进行删除或修改。

## 安装

Python 3.12

```bash
pip install erbs-plugin
```

生成 PNG 使用原生 Skia 绘图，安装渲染依赖即可：

```bash
pip install 'erbs-plugin[render]'
```

## 命令行

直接查询 JSON：

```bash
erbs overview playername
erbs matches playername --count 10
```

生成 PNG（所需 CDN 图片会按需缓存）：

```bash
erbs overview playername --format path --output ./player.png
```

也可以将 PNG 字节输出重定向到文件：

```bash
erbs overview playername --format bytes > player.png
```

同一命令行也可通过 `python -m erbs_plugin` 调用；`erbs-assets` 命令为兼容既有使用方式而保留。更多命令、调试和配置示例见[中文快速开始](QUICK_START.md)。

## 插画总结图

网站评价可通过 `await service.published_player_summary("玩家昵称")` 获取，再传入
`SkiaCardRenderer.render()` 在本地生成 PNG。该独立入口读取 ERCraft 当前赛季的
`scope=overall` 报告，直接显示接口等级（E–SSS）、百分位 P 和各轴有效场数。
不会拉取 DAK 对局、补入普通匹配或回退到本地评分。返回的评价直接采用，不再做本地样本、
等级、百分位或身份/赛季复核；缺失值显示“—”。身份解析和报告准备期间持续等待，
没有总等待时限，接口或网站任务明确报错才退出。可传入异步 `progress` 回调，接收网站的
处理阶段、排队次序、前方人数和预计等待时间。准备状态不缓存，避免卡在旧状态。
段位实际观测时间超过玩家缓存时长（默认 5 分钟）时，先调用 ERCraft 排位刷新任务，
成功后清除该玩家的本地资料与评价缓存再取数；刷新失败不会继续展示旧 RP。
原有卡片页脚显示报告实际样本场数，网站已收录样本不一定等于赛季总场数。
角色抽图按报告角色场次加权，
DAK 元数据仅用于素材名称与稀有度且允许缺失。报告时间、版本和原始轴字段保留在 payload 中，
不将网站缓存视为刚刚重算的最新完整战绩。下文 `summary` CLI/API 仍为独立保留的本地流程。

网站评价卡的称号按前端 `play-card-percentile.v4` 规则动态选择：输入为 API 的六维百分位，
阈值、判定顺序及并列优先级与网站一致，不重新计算原始评分、等级或百分位。
JSON 中 `styleId`、`styleRuleVersion`、`displayTitle` 记录选定类型、规则版本和显示称号；
`summary_title` 仍可显式覆盖显示文字。背景插画和版式保持现有行为，本地评分入口不套用网站称号。

| 编号 | 显示称号 |
|---|---|
| 01 | 至尊的六边形战士 |
| 02 | 可靠的带队老司机 |
| 03 | 莽撞的铁头战士 |
| 04 | 不稳定的蹦蹦炸弹 |
| 05 | 稳健的可靠战友 |
| 06 | 无情的上分机器 |
| 07 | 从容的均衡主义者 |
| 08 | 顽强的生存能手 |
| 09 | 精明的操盘运营手 |
| 10 | 无私的团队后盾 |
| 11 | 仍需努力 |
| 12 | 倒霉的复活点常客 |
| 13 | 帅就完了的嘉豪 |

规则核验来源：[网站 PlayCardDialog 脚本](https://ercraft.net/assets/PlayCardDialog-s8kz-wDg.js)，
核验日期 2026-10-22，脚本 SHA-256：
`bb75a024381324d2e62291b0f15087b29c4a74ed3ffb4ebd722e798a11ef5dbd`。

`summary` 参考 ERCraft 的竖版插画卡布局，复用插件已有的本地六维评分。默认统计本赛季排位三排，上限 500 场；不超过上限时统计全部，超过时取最近 500 场。排位不足 20 场时，用本赛季最近的普通匹配三排补足 20 场：

```bash
erbs summary dantynoel --format path --output ./summary.png
erbs summary dantynoel --art ./illustration.png --card-title "六维实战档案" --format path --output ./summary-custom.png
```

`--count` 为兼容旧调用仍接受 1–60，但不再改变统计范围。`--season` 可指定 DAK 赛季；默认使用 DAK 标记的当前赛季，即使本赛季没有排位也不会回退到旧赛季。排位记录逐页读取并去重；`--max-matches` 可调整上限（至少 20），Python 对应 `ERBSConfig(summary_match_limit=1000)`，设为 `None` 可解除上限。匹配只补足至 20 场，两者合计仍不足时保留真实场数。JSON 中的 `rankedCount`、`rankedTotal`、`normalCount`、`truncated` 明确记录样本组成与截断状态。图中只保留简洁的评级、百分数和场数；百分数为本地 0–100 分数，与人群百分位无关。等级使用固定分数区间：S ≥70、A ≥55、B ≥40、C ≥25、D ≥10，其余有效分数为 E。此规则版本为 `local-six-axis-bands.v1`，属于本地显示规则，与 ERCraft 网站等级及人群百分位独立；缺失或无效分数不授予等级。即使启用了雷达图的 ERCraft API 备选，总结图仍仅使用本地评分。

500 场上限来自本机真实取数到 PNG 的基准：500 场四次无本地缓存为 8.00–11.61 秒，1,000 场为 17.85–20.83 秒；热缓存分别约 0.16–0.21、0.21–0.28 秒，不含 QQ 上传发送。网络和 CDN 耗时会波动。可用 `python scripts/benchmark_summary.py --output 目录` 复测。

普通匹配补样按玩家所选赛季的排位段位选择本地评分基准；未定级玩家使用铁阎基准，依据写入 JSON 的 `normalBaselineTier` 与 `normalBaselineSource`。匹配隐藏分不会被当作排位 RP。此兼容只在总结图中启用，原排位逐局评分及雷达图行为保持不变。

`--art` 要求本机可解码的栅格底图，尺寸必须为 1024×1536 像素。未指定时，每次生成按本赛季排位三排的角色使用场次加权抽取角色，不随 500 场采样上限截断；无排位时按同赛季匹配的使用比例降级，赛季使用数据缺失时使用已采集场次。

选中角色后，优先从该角色的 ERCraft 已有插画卡面中抽取，不要求玩家使用过对应皮肤。仅当该角色没有 ERCraft 卡面时，才回退到该角色公开记录中使用过的皮肤，再在无有效皮肤记录时回退到基础皮肤，使用对应的 DAK 图片。卡面及皮肤候选均按英雄（紫色，DAK `grade=4`）权重 10、其余权重 1 抽取，皮肤使用次数不再乘入权重。公开皮肤记录不是完整的玩家皮肤库存。素材按需缓存，但命中查询缓存仍会重新抽图。`--card-title` 只修改显示称号。Python 对应配置为 `ERBSConfig(summary_art_path=Path("illustration.png"), summary_title="六维实战档案")`，两项默认均为 `None`，不影响评分或查询缓存。

```python
from erbs_plugin import player_summary, query

png_path = await player_summary("dantynoel", format="path", output="summary.png")
json_text = await query("summary", "dantynoel", count=20)
```

总结图使用独立的 180 秒查询缓存，缓存键包含采样范围、本地等级与头图抽取版本，旧版最近 20 场总结会重新查询，不会复用已有雷达图缓存。六维数值公式及雷达图展示保持原有行为。

## Python API

推荐使用导出的异步查询函数：

```python
from erbs_plugin import player_overview

json_text = await player_overview("playername", format="json")
png_bytes = await player_overview("playername", format="bytes")
png_path = await player_overview(
    "playername",
    format="path",
    output="player.png",
)
```

可查询玩家总览、段位、统计、对局、近期表现、雷达图、角色、队友、最佳对局、英雄池、装备习惯、排行榜、角色统计、物品和路线。通用 `query()` 函数也支持相同操作。

长生命周期应用可复用 `AsyncERBSClient` 与 `SkiaCardRenderer`；由调用方传入的资源仍由调用方负责关闭。

## LoMu 风格查询与迁移

```bash
erbs command '/查询玩家 玩家名称 排位'
erbs command '/查询角色 席琳 排位 灭钻' --format path --output celine.png
erbs command '/查询角色装备 席琳'
erbs command '/角色数据 星陨'
erbs command '/段位统计 国服'
erbs command '/永恒多少分 亚1'
erbs command '/查询装备 烈阳'
erbs command '/帮助'
```

新查询复用已有客户端、缓存、元数据和评分逻辑。完整命令、Python API 与数据口径见
[DAK.GG 查询与迁移说明](DAK_QUERIES.zh-CN.md)。

旧 HTML/CSS 绘图、主题、字体和 SVG 雷达坐标计算已归档到
[legacy](../src/erbs_plugin/legacy/README.md)，默认绘图使用 `SkiaCardRenderer`。

## 数据、缓存与资源

数据读取自 DAK.GG 网站使用的《永恒轮回》公开端点。该包不会调用玩家刷新、认证、管理或写入接口。使用方应采用保守的请求频率，并在适当位置保留数据来源说明。

成功的高层查询会缓存到当前系统用户的平台数据目录中的私有 SQLite 数据库。每种查询可分别通过 `ERBSConfig.query_cache_seconds` 配置过期时间；缓存键包含查询参数、语言和 API 地址。所有结果都有 `footer.updatedAt`，缓存命中还会提供 `footer.cached=true` 与数据可能非最新的提示。

PNG 渲染会复用本地资源清单，仅按需下载当前结果引用的 `cdn.dak.gg` 图片；失败时使用占位图。JSON 查询不下载图片。设置 `ERBSConfig(download_render_assets=False)` 可仅使用本地素材。

## 免责声明与商标

ERBS-plugin 是非官方项目，与 Nimble Neuron 没有隶属关系。《永恒轮回》为 Nimble Neuron 的商标。项目内的双行中英文文字标为本项目独立生成的视觉素材，并非官方游戏 logo。

## 许可证

本项目采用 Apache-2.0 许可证。第三方参考、字体许可与相关声明见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
