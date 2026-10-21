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

`summary` 参考 ERCraft 的竖版插画卡布局，复用插件已有的本地六维评分，默认取当前赛季最近 20 场排位三排：

```bash
erbs summary dantynoel --format path --output ./summary.png
erbs summary dantynoel --count 40 --art ./illustration.png --card-title "六维实战档案" --format path --output ./summary-custom.png
```

`--count` 支持 1–60 场，`--season` 可指定 DAK 赛季。未指定赛季时，对局样本与玩家资料的当前赛季保持一致。图中标注实际取到的最近场数，每个维度显示本地分数与有效样本数，缺失项保持不可用；不会把最近对局包装为赛季全部数据，也不会生成网站百分位或字母评级。即使启用了雷达图的 ERCraft API 备选，总结图仍仅使用本地评分。

`--art` 要求本机可解码的栅格底图，尺寸必须为 1024×1536 像素；未指定时使用样本中最常玩的实验体及已缓存的 DAK 素材。`--card-title` 只修改显示称号。Python 对应配置为 `ERBSConfig(summary_art_path=Path("illustration.png"), summary_title="六维实战档案")`，两项默认均为 `None`，不影响评分或查询缓存。

```python
from erbs_plugin import player_summary, query

png_path = await player_summary("dantynoel", format="path", output="summary.png")
json_text = await query("summary", "dantynoel", count=20)
```

总结图使用独立的 180 秒查询缓存，不会复用已有雷达图缓存。

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
