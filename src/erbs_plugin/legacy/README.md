# 旧绘图归档

默认 PNG 渲染现使用 `erbs_plugin.rendering.SkiaCardRenderer`。
此目录保留迁移前的图形实现与资源，供回溯或显式兼容使用：

- `rendering/html.py`：浏览器生命周期、HTML 渲染、本地资源嵌入。
- `rendering/templates/`：完整 HTML 与 CSS。
- `rendering/theme/`：旧主题图片、GIF、Rajdhani 字体及其许可。
- `radar.py`：旧雷达图 SVG 坐标与多边形生成，仅在旧渲染器中调用。
- `radar-presentation-original.py.txt`：迁移前雷达展示模块原文。
- `test_html_renderer.original.py.txt`：迁移前 HTML 渲染测试原文。
- `rendering-original-sha256.json`：迁移前 `rendering/` 文件的 SHA-256 清单。

旧渲染器仅调整了包路径、资源路径、依赖提示和雷达几何适配；模板及主题资源保持原样。
SHA-256 清单记录原始状态，已调整导入的 Python 文件不应再与原始摘要相等。
`TextRenderer` 继续用于 JSON，属于当前的数据输出层。

## 显式使用

```bash
pip install 'erbs-plugin[legacy-render]'
```

旧绘图仍需要已安装的 Chrome、Edge 或 Chromium；可通过 `browser_path` 或
`ERBS_RENDER_BROWSER` 配置。旧渲染器保持仅使用本地素材的行为。

```python
from erbs_plugin import AsyncERBSClient, ERBSConfig, player_overview
from erbs_plugin.legacy.rendering import HtmlCardRenderer

config = ERBSConfig(asset_directory="./assets")
async with AsyncERBSClient(config) as client:
    async with HtmlCardRenderer(config) as renderer:
        png = await player_overview(
            "PLAYER", format="bytes", client=client, renderer=renderer,
        )
```

旧模板用于兼容原有卡片，新增角色出装等布局应使用默认 Skia 渲染器。
旧模块不会被默认的 PNG 查询初始化；`legacy-render` 与 `render` 两组依赖相互独立。
