# ERBS-plugin 中文快速开始

ERBS-plugin 是一个独立、框架无关的《永恒轮回》数据查询与图片渲染库。它可以通过
命令行或 Python 异步 API 返回 JSON、PNG 字节或保存后的图片路径。

数据来自 DAK.GG 的公开接口。调用方负责决定如何保存、发送或展示最终结果。

## 1. 环境要求

- Python 3.12
- 生成 PNG 时需要本机已安装 Chrome、Edge 或 Chromium
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

运行时不会自动下载缺失图片。首次使用 PNG 或 debug 渲染前，建议在项目目录执行：

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

普通查询遇到未下载的远程图片时会使用内置占位图。默认 debug 样例使用严格的真实资源
引用，缺少必需图片时会抛出 `AssetMissing`，不会静默生成带占位图的预览。

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

找不到浏览器时，可以显式指定可执行文件：

```bash
erbs overview PLAYER --format path --output ./player.png --browser-path "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

也可以设置环境变量 `ERBS_RENDER_BROWSER`。

## 4. Debug 图片预览

裸 `debug` 命令会刷新全部 14 个用户可用接口的默认图片，并生成浏览器可查看的总览：

```bash
erbs debug
```

输出目录默认为 `.debug/cards/`，其中包含：

- 14 张默认接口 PNG
- `manifest.json`
- 图片总览 `index.html`

`erbs debug cards` 是相同功能的兼容别名。默认样例玩家为 `B站丨咕咕禽OC`、`Preme`
和 `페이블`。

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
- `rank`、`stats`、`matches`、`recent`
- `characters`、`teammates`
- `best_match`、`hero_pool`、`equipment`
- `leaderboard`、`character`、`item`、`routes`

### 输出格式

| `format` | 返回类型 | 说明 |
| --- | --- | --- |
| `"json"` | `str` | 默认值，不启动浏览器 |
| `"bytes"` | `bytes` | 返回完整 PNG 字节 |
| `"path"` | `Path` | 必须同时提供 `output`，通过临时文件原子替换 |

`output` 只允许与 `format="path"` 一起使用。

## 6. 复用客户端与渲染器

频繁查询时，应复用客户端和浏览器渲染器，减少连接和浏览器启动开销：

```python
import asyncio

from erbs_plugin import AsyncERBSClient, HtmlCardRenderer, player_overview


async def main() -> None:
    async with AsyncERBSClient() as client:
        async with HtmlCardRenderer(client.config) as renderer:
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

### PNG 渲染提示未找到浏览器

确认 Chrome、Edge 或 Chromium 已安装；随后使用 `--browser-path` 或
`ERBS_RENDER_BROWSER` 指定可执行文件。

### 图片显示为占位图

执行资源更新和校验：

```bash
erbs assets update --directory ./assets
erbs assets check --directory ./assets
```

同时确认命令运行目录位于 `assets/` 的同级目录或其子目录中。

### Debug 报 `AssetMissing`

默认 debug 预览不允许占位图。重新下载或更新 `./assets` 后再次运行 `erbs debug`。

### 请求失败或返回限流

客户端默认启用进程内缓存、有限重试和并发限制。遇到持续限流时，应降低调用频率，不要
立即高并发重试。

## 9. 下一步

- 集成约定与资源所有权：[docs/integration.md](docs/integration.md)
- 开发、测试和 debug 工作流：[docs/developer-help.md](docs/developer-help.md)
- 项目概览：[README.md](README.md)
