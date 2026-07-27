# ERBS-plugin

[English](../README.md) · [中文快速开始](QUICK_START.md)

ERBS-plugin 是面向中文互联网服务的机器人插件。用于查询《永恒轮回》公开数据、进行分析、输出 JSON、管理本地图片资源，并渲染 PNG 数据卡片。

本项目为个人开发项目，仅供**学习、交流与参考**，且不保证持续稳定更新。若有侵权或代码问题，请联系我进行删除或修改。

## 安装

Python >= 3.12

```bash
pip install erbs-plugin
```

生成 PNG 还需安装渲染依赖，并在系统中已有 Chrome、Edge 或 Chromium：

```bash
pip install 'erbs-plugin[render]'
```

## 命令行

直接查询 JSON：

```bash
erbs overview playername
erbs matches playername --count 10
```

下载本地资源并生成 PNG：

```bash
erbs assets download --directory ./data/erbs-assets
erbs assets check --directory ./data/erbs-assets
erbs overview playername --format path --output ./player.png
```

也可以将 PNG 字节输出重定向到文件：

```bash
erbs overview playername --format bytes > player.png
```

同一命令行也可通过 `python -m erbs_plugin` 调用；`erbs-assets` 命令为兼容既有使用方式而保留。更多命令、调试和配置示例见[中文快速开始](QUICK_START.md)。

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

长生命周期应用可复用 `AsyncERBSClient` 与 `HtmlCardRenderer`；由调用方传入的资源仍由调用方负责关闭。

## 数据、缓存与资源

数据读取自 DAK.GG 网站使用的《永恒轮回》公开端点。该包不会调用玩家刷新、认证、管理或写入接口。使用方应采用保守的请求频率，并在适当位置保留数据来源说明。

成功的高层查询会缓存到当前系统用户的平台数据目录中的私有 SQLite 数据库。每种查询可分别通过 `ERBSConfig.query_cache_seconds` 配置过期时间；缓存键包含查询参数、语言和 API 地址。所有结果都有 `footer.updatedAt`，缓存命中还会提供 `footer.cached=true` 与数据可能非最新的提示。

渲染时会在当前目录及其父目录中查找已下载的本地资源，匹配时复用；缺失时使用包内占位图。运行时不会隐式下载图片资源。

## 免责声明与商标

ERBS-plugin 是非官方项目，与 Nimble Neuron 没有隶属关系。《永恒轮回》为 Nimble Neuron 的商标。项目内的双行中英文文字标为本项目独立生成的视觉素材，并非官方游戏 logo。

## 许可证

本项目采用 Apache-2.0 许可证。第三方参考、字体许可与相关声明见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
