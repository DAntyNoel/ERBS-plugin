# ERCraft 六维实战评分雷达

本目录将最近排位三排原始记录、逐局评分和雷达展示分开：

- `data.py`：分页查询、过滤模式、去重；保留 `aggregate_radar_metrics` 原始统计兼容接口。
- `scoring.py`：调用 `scoring/axes.py`，按公开源码聚合生存、交战、运营、支援、结果、稳定性。
- `models.py`：样本、维度、覆盖率及逐局评分。
- `presentation.py`：按维度数计算等间距 SVG 坐标，缺失分数保持 `null`。

旧 `style-v1` 八维校准和过渡五维均值雷达已替换。默认最近 20 场、最多 60 场；
每局先按当局段位、实验体武器和时长评分，再按 `production-analysis-axes.v1.1` 聚合。
没有按样本量收缩评分，也不以固定零分填补缺失项。默认完全本地计算；
可选 `ercraft_api_fallback=True` 仅在本地缺项时读取当前接口的完整 recent20 报告，
来源和版本单独标识，不混用两条管道。

完整公式、输入限制、历史基准来源和测试方法见 [评分说明](../../../docs/SCORING.zh-CN.md)。
