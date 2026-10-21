# ERBS-plugin 中文快速开始

ERBS-plugin 是一个独立、框架无关的《永恒轮回》数据查询与图片渲染库。它可以通过
命令行或 Python 异步 API 返回 JSON、PNG 字节或保存后的图片路径。

数据来自 DAK.GG 的公开接口。调用方负责决定如何保存、发送或展示最终结果。

## 1. 环境要求

- Python 3.12
- 生成 PNG 时需要 `render` 扩展；Linux 建议安装 Noto Sans CJK 字体
- 下载数据和图片资源时需要能够访问 DAK.GG

只使用 JSON 查询：

```bash
pip install erbs-plugin
```

需要 PNG 渲染：

```bash
pip install "erbs-plugin[render]"
```

在源码仓库中开发时，可以使用 uv 安装全部依赖：

```bash
uv sync --all-extras --dev
```

## 2. 准备本地图片资源

PNG 与 debug 按需下载当前结果引用的 DAK.GG CDN 图片，并复用本地清单。JSON 不下载图片。
也可以提前批量准备资源：

```bash
erbs assets download --directory ./assets
erbs assets check --directory ./assets
```

源码开发环境中的等价命令是：

```bash
uv run erbs assets download --directory ./assets
uv run erbs assets check --directory ./assets
```

渲染器不需要额外传入资源目录参数。它会从当前目录逐级向上查找：

1. `assets/`
2. `data/erbs-assets/`
3. `erbs-assets/`
4. 平台用户数据目录中的 `erbs-plugin/assets/`

图片下载失败时使用内置占位图。通过 `ERBSConfig(download_render_assets=False)`
可禁用自动下载；通过 `asset_directory` 可指定缓存位置。

资源维护命令：

```bash
erbs assets update --directory ./assets
erbs assets prune --directory ./assets
erbs assets check --directory ./assets
```

## 3. 命令行查询

命令默认输出 JSON：

```bash
erbs overview "B站丨咕咕禽OC"
erbs matches "B站丨咕咕禽OC" --count 5
```

常用玩家查询包括：

```bash
erbs rank PLAYER
erbs stats PLAYER
erbs recent PLAYER
erbs radar PLAYER --count 20
erbs characters PLAYER
erbs teammates PLAYER
erbs best-match PLAYER
erbs hero-pool PLAYER
erbs equipment PLAYER
```

其他查询：

```bash
erbs leaderboard --page 1
erbs character 艾玛 --weapon Arcana
erbs item 烈阳
erbs routes 艾玛 --weapon Arcana
```

用户名或查询文本中含有空格时，请使用引号包裹。

### 保存 PNG

推荐使用 `path` 格式直接保存文件：

```bash
erbs overview "B站丨咕咕禽OC" --format path --output ./player.png
```

也可以把原始 PNG 字节写到标准输出：

```bash
erbs overview "B站丨咕咕禽OC" --format bytes > player.png
```

在可能改变二进制重定向内容的终端环境中，应优先使用 `--format path`。

Linux 缺少中文字体时，可安装 Noto Sans CJK，或传入字体路径：

```bash
erbs character 席琳 --format path --output ./celine.png --font-path /path/to/NotoSansCJK-Regular.ttc
```

完整 LoMu 风格命令、筛选参数与 Python 示例见 [DAK.GG 查询说明](DAK_QUERIES.zh-CN.md)。
旧绘图的显式调用方式见 [legacy](../src/erbs_plugin/legacy/README.md)。

## 4. Debug 图片预览

裸 `debug` 命令会重新渲染全部 24 个命令的默认图片，并生成浏览器可查看的总览：

```bash
erbs debug
```

输出目录默认为 `.debug/cards/`，其中包含：

- 24 张默认命令 PNG
- `manifest.json`
- 图片总览 `index.html`

`erbs debug cards` 是相同功能的兼容别名。默认样例玩家为 `B站丨咕咕禽OC`、`Preme`
和 `페이블`。

Debug 与普通查询共用当前用户私有目录中的 SQLite 查询数据库，因此修改绘图逻辑后反复渲染不会
重复请求网络。需要获取最新数据时显式刷新缓存：

```bash
erbs debug --refresh-data
erbs debug overview "B站丨咕咕禽OC" --refresh-data
```

可以调整输出目录和渲染缩放：

```bash
erbs debug --output-directory ./.debug/cards --scale 1.25
```

也可以执行真实查询，并把实际返回图片追加到同一总览：

```bash
erbs debug overview "B站丨咕咕禽OC"
erbs debug matches "B站丨咕咕禽OC" --count 10
```

真实 debug 查询的标准输出与普通命令一致；预览图片保存位置写到标准错误，不会污染 JSON
或 PNG 字节输出。

### 私有查询数据库与过期时间

每次成功查询都会写入 `ERBSConfig.private_database_path` 指向的 SQLite 数据库。默认位置由
`platformdirs` 选择，例如 Windows 下为
`%LOCALAPPDATA%\erbs-plugin\private-query-cache.sqlite3`。数据库仅保存于当前系统用户的私有
数据目录，缓存键包含接口、参数、语言和 API 地址，默认最多保留 512 条结果。

| 查询 | 默认 TTL | 查询 | 默认 TTL |
| --- | ---: | --- | ---: |
| `leaderboard` | 60 秒 | `matches` | 120 秒 |
| `recent` | 120 秒 | `best-match` | 120 秒 |
| `radar` | 180 秒 |  |  |
| `rank` | 180 秒 | `overview` | 300 秒 |
| `teammates` | 300 秒 | `multi` | 300 秒 |
| `compare` | 300 秒 | `stats` | 600 秒 |
| `routes` | 600 秒 | `characters` | 900 秒 |
| `hero-pool` | 900 秒 | `equipment` | 900 秒 |
| `skins` | 1800 秒 | `character` | 1800 秒 |
| `item` | 86400 秒 |  |  |
| `search` | 300 秒 | `character-stats` | 1800 秒 |
| `character-equipment` | 1800 秒 | `tier-stats` | 300 秒 |
| `tier-cutoffs` | 60 秒 | `help` | 不缓存 |

可通过 `ERBSConfig(query_cache_seconds={...})` 为每一种查询覆盖 TTL，通过
`private_database_path` 修改数据库位置。所有查询结果都会包含 `footer.updatedAt` 信息更新
时间；缓存命中时还会返回 `footer.cached=true` 和
`footer.notice="缓存命中，数据可能不是最新"`。玩家数据自带的上游同步时间保存在
`footer.sourceUpdatedAt`。

图片页脚会将 `footer.updatedAt` 转换为固定时区后显示。默认配置为
`ERBSConfig(render_timezone_name="CST", render_timezone_offset_hours=8)`，显示格式为
`2026-10-21 15:16 CST`。该转换只影响图片，不改变 JSON 中的
ISO 8601 时间。

## 5. Python 高层 API

推荐使用导出的异步查询函数：

```python
import asyncio

from erbs_plugin import player_overview


async def main() -> None:
    json_text = await player_overview("B站丨咕咕禽OC", format="json")
    print(json_text)

    image = await player_overview("B站丨咕咕禽OC", format="bytes")
    print(f"PNG bytes: {len(image)}")

    path = await player_overview(
        "B站丨咕咕禽OC",
        format="path",
        output="player.png",
    )
    print(path)


asyncio.run(main())
```

通用 `query()` 可以通过操作名访问同一组能力：

```python
from erbs_plugin import query

result = await query("matches", "B站丨咕咕禽OC", count=10, format="json")
```

可直接导入的查询函数包括：

- `player_overview`
- `rank`、`stats`、`matches`、`recent`、`radar`
- `characters`、`teammates`
- `best_match`、`hero_pool`、`equipment`
- `leaderboard`、`character`、`item`、`routes`
- `search`、`character_equipment`、`character_stats`、`tier_stats`、`tier_cutoffs`
- `execute_command`：解析并执行中文斜杠命令

### 输出格式

| `format` | 返回类型 | 说明 |
| --- | --- | --- |
| `"json"` | `str` | 默认值，不初始化图形引擎 |
| `"bytes"` | `bytes` | 返回完整 PNG 字节 |
| `"path"` | `Path` | 必须同时提供 `output`，通过临时文件原子替换 |

`output` 只允许与 `format="path"` 一起使用。

## 6. 复用客户端与渲染器

频繁查询时，应复用客户端与 Skia 渲染器，减少连接和字体、图片解析开销：

```python
import asyncio

from erbs_plugin import AsyncERBSClient, SkiaCardRenderer, player_overview


async def main() -> None:
    async with AsyncERBSClient() as client:
        async with SkiaCardRenderer(client.config) as renderer:
            first = await player_overview(
                "B站丨咕咕禽OC",
                format="bytes",
                client=client,
                renderer=renderer,
            )
            second = await player_overview(
                "Preme",
                format="bytes",
                client=client,
                renderer=renderer,
            )
            print(len(first), len(second))


asyncio.run(main())
```

调用方传入的 `client` 和 `renderer` 不会被查询函数自动关闭；调用方需要自行管理它们的
生命周期。未传入时，查询函数会创建并关闭内部资源。

## 7. 异常处理

所有库异常都继承自 `ERBSError`：

```python
from erbs_plugin import (
    AssetMissing,
    InvalidQuery,
    PlayerNotFound,
    RateLimited,
    RenderFailed,
    UpstreamUnavailable,
    player_overview,
)

try:
    result = await player_overview("PLAYER", format="bytes")
except PlayerNotFound:
    print("玩家不存在")
except InvalidQuery as exc:
    print(f"参数错误：{exc}")
except RateLimited:
    print("请求过于频繁")
except UpstreamUnavailable:
    print("DAK.GG 暂时不可用")
except AssetMissing as exc:
    print(f"本地图片资源缺失：{exc}")
except RenderFailed as exc:
    print(f"图片渲染失败：{exc}")
```

## 8. 常见问题

### PNG 渲染依赖或中文字体缺失

安装 `erbs-plugin[render]`。Linux 可安装 Noto Sans CJK，或通过 `--font-path` /
`ERBSConfig(render_font_path=...)` 指定支持所需文字的字体。

### 图片显示为占位图

执行资源更新和校验：

```bash
erbs assets update --directory ./assets
erbs assets check --directory ./assets
```

同时确认命令运行目录位于 `assets/` 的同级目录或其子目录中。

### Debug 图片缺失

确认能够访问 `cdn.dak.gg`，并检查资源清单；下载失败的图片使用占位图，其余部分继续渲染。

### 请求失败或返回限流

客户端默认启用进程内缓存，高层查询同时使用带独立 TTL 的私有 SQLite 缓存；网络请求仍有
有限重试和并发限制。遇到持续限流时，应降低调用频率，不要立即高并发重试。

## 9. 下一步

- 集成约定与资源所有权：[integration.md](integration.md)
- 开发、测试和 debug 工作流：[developer-help.md](developer-help.md)
- 项目概览：[README.md](../README.md)
