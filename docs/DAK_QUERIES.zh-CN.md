# DAK.GG 查询与绘图迁移

LoMu 风格的公开数据查询已合并进 ERBS-plugin 的客户端、服务、命令分发和私有查询缓存。
默认图片使用 `SkiaCardRenderer` 原生绘制。原有玩家总览、雷达评分、装备习惯、路线等接口继续可用。

## 安装与命令

```bash
uv sync --extra render --group dev
uv run erbs command '/查询角色 席琳 排位 灭钻' --format path --output ./celine.png
```

命令默认返回 JSON；`--format bytes` 返回 PNG，`--format path --output ...` 保存 PNG。
参数中的空格需要引号，例如 `/查询玩家 "有 空格的昵称" 排位`。

| 中文命令 | CLI 操作 | Python 函数 | 内容 |
| --- | --- | --- | --- |
| `/查询玩家 <昵称> [模式]`、`/查玩家 ...` | `search` | `search` | 赛季统计、最近战绩、英雄池、评分和走势 |
| `/查询角色 <角色> [模式] [段位]` | `character` | `character` | 武器、出装、技能、战术技能、潜能、灌注、高分玩家 |
| `/查询角色装备 <角色> [模式] [段位]` | `character-equipment` | `character_equipment` | 武器、热门出装、合成顺序、各部位装备 |
| `/角色数据 [段位]`、`/角色数据统计 ...` | `character-stats` | `character_stats` | 全角色 / 武器统计，按评分排序 |
| `/段位统计 [服务器]` | `tier-stats` | `tier_stats` | 指定服务器分数线与全服段位分布 |
| `/永恒多少分 [服务器]` | `tier-cutoffs` | `tier_cutoffs` | 指定服务器的永恒、半神分数线 |
| `/查询装备 <名称/ID/拼音>` | `item` | `item` | 物品属性、合成材料 |
| `/帮助` | `help` | `query("help")` | 本地命令帮助，无网络请求 |

CLI 的中文操作名也可直接使用，例如 `erbs 查询玩家 PLAYER --mode 普通`。
完整斜杠命令通过 `erbs command '...'` 执行。

```bash
erbs search PLAYER --mode RANK --count 20
erbs character 席琳 --mode RANK --tier meteorite_plus
erbs character-equipment 艾玛 --weapon Arcana --mode COBALT
erbs character-stats --tier mithril_plus
erbs tier-stats --server asia2
erbs tier-cutoffs --server frankfurt
erbs item lieyang
erbs debug character 席琳 --tier diamond_plus
```

玩家模式支持 `RANK/排位`、`NORMAL/普通`、`COBALT/钴协议`、`ALL/全部`；默认排位。
角色详情和角色出装支持排位、钴协议，默认排位、`diamond_plus`。
段位支持灭钻 / 钻石、星陨、无暇 / 无瑕、修罗、黄金、白银、青铜、铁阎、`in1000`，
也可使用 `diamond_plus`、`meteorite_plus`、`mithril_plus` 等对应值。

服务器默认 `seoul`，支持 `asia2`、`asia3`、`ohio`、`frankfurt`、`saopaulo`、`global`；
中文别名包括亚1 / 国际服、亚2 / 国服、亚3、美服、欧服、南美、全球。
角色和物品支持名称、ID、拼音及拼音首字母；模糊查询有多个候选时会报错提示候选名称。

## Python 调用

```python
from erbs_plugin import (
    ERBSConfig, character, character_equipment, character_stats,
    execute_command, search, tier_cutoffs, tier_stats,
)

profile_json = await search("PLAYER", mode="普通", count=10)
character_png = await character("席琳", tier="星陨", format="bytes")
build_json = await character_equipment("艾玛", weapon="Arcana", mode="钴协议")
table_json = await character_stats(tier="灭钻")
distribution_json = await tier_stats(server="国服")
cutoffs_json = await tier_cutoffs(server="亚1")
image_path = await execute_command(
    "/查询角色 席琳 排位 灭钻", format="path", output="celine.png",
)

# 仅使用已缓存的图片素材；数据查询仍遵循正常的网络和查询缓存规则。
offline_images = ERBSConfig(download_render_assets=False)
```

`search()` 与 `/查询玩家` 默认最近 20 场，可通过 Python / CLI 的 `count` 设置为 1–20。
底层通用 `query()` 保留原有的默认 `count=5`。
新功能使用已有的 `client`、`renderer`、`config` 和 `format` 所有权约定。
`parse_command()` 只解析命令，`execute_command()` 解析后调用统一查询 API；两者不保存平台用户绑定。

## 请求与统计口径

| 数据 | 公开 GET 来源 |
| --- | --- |
| 玩家资料 | `er.dakgg.io/api/v1/players/{nickname}/profile` |
| 玩家对局 | `er.dakgg.io/api/v1/players/{nickname}/matches` |
| 角色总表 | `er.dakgg.io/api/v1/character-stats?dt=7&...` |
| 角色详情 | `dak.gg/er/characters/{key}` 中的 `__NEXT_DATA__` / 查询快照 |
| 当前赛季 | `er.dakgg.io/api/v0/current-season` |
| 排行与分数线 | `er.dakgg.io/api/v0/leaderboard` |
| 段位分布 | `er.dakgg.io/api/v0/statistics/tier-distribution` |

角色页只解析 JSON 快照，不执行网页脚本或截图网页。页面请求与 JSON API 共用限流、重试、
进程缓存和上游失败处理。没有调用玩家刷新或其他写入接口。

玩家查询按资料中的最近游玩赛季匹配战绩，保留定位赛的 0 RP；`ALL` 汇总该赛季各模式统计。
出装的合成序列按上游的 **1 起始位置**解析，各部位装备统计累加全部出装记录的场次、胜场，
再计算胜率；热门出装仅展示前四项。缺失统计保留 `null` / 原因，不填造数值。

分数线按明确的 `tierType=8/7` 分别识别永恒与半神；没有类型的旧响应兼容位置规则。
分数线使用所选服务器，段位分布接口返回全服统计，卡片中明确标注。
角色统计以 DAK.GG 当前快照为准；页面结构或公开接口变化时可能需要更新解析器。

## 图片与 legacy

PNG 依赖 `erbs-plugin[render]`，使用系统字体并按字形回退。Linux 可安装 Noto Sans CJK，
或配置 `render_font_path` / CLI `--font-path`。
JSON 查询不导入 Skia，也不下载图片。

PNG 渲染只自动下载结果中引用的 `cdn.dak.gg` 图片，优先复用本地清单。
未指定目录时查找当前目录及父目录的素材清单，最后使用平台用户数据目录；
显式 `asset_directory` 决定新渲染器的存储位置。下载失败的图片使用占位图，成功下载的图片仍保留。
设置 `download_render_assets=False` 可以禁用自动下载。

旧 HTML/CSS 模板、主题、字体、浏览器渲染器和雷达 SVG 坐标计算已全部放入
[`src/erbs_plugin/legacy/`](../src/erbs_plugin/legacy/README.md)。默认入口不再导出 `HtmlCardRenderer`。
旧渲染器的显式导入方式、依赖和归档校验说明见该目录 README。

本次参考 [EternalReturnLoMu](https://github.com/LuoRenMu/EternalReturnLoMu)
提交 `e04e650a9d8ce7f370171ef13c256baddf9896f3` 的公开查询行为和请求约定；
Python 查询与绘图独立实现，没有复制或分发其 Kotlin 源码及素材。
