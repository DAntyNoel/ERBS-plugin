# 实战评分

评分来自公开仓库 [adgjmptw2/ERCraft-main](https://github.com/adgjmptw2/ERCraft-main)
提交 `93dd2a13345c53e5a6fb271c92d42b9fb62c7761` 的 `role-score.v3` 数值核心和
`production-analysis-axes.v1.1` 六维聚合。Python 实现位于 `src/erbs_plugin/scoring/`，
默认运行无需 Node 或 ERCraft 评分接口。

## 输入与缺失值

`score_match(raw_match)` 接受 DAK.GG 排位三排单局原始记录：

| 输入 | DAK 字段 |
|---|---|
| 模式 | `matchingMode=3`、`matchingTeamMode=3` |
| 当局段位 | `mmrAfter - mmrGain`，不使用当前个人资料段位 |
| 实验体与武器 | `characterNum`、`bestWeapon`（或 `weaponTypeId`） |
| 名次、时长 | `gameRank`、`playTime`（秒） |
| 五项指标 | `damageToPlayer`、`playerKill/playerAssistant/teamKill`、`playerDeaths`、`viewContribution`、`monsterKill` |

自动识别已核对的 DAK 赛季 39（S11）、41（S12）。赛前 RP 必须大于 0；
从高到低按 7600／6400／5000／3600／2400／1400／600 切分秘银以上／陨石／钻石／
铂金／黄金／白银／青铜，其余为黑铁。新赛季或历史其他赛季需传入明确的赛前基准段位：

```python
from erbs_plugin import score_match

result = score_match(raw_match, tier_key="platinum")
```

显式段位只指定比较基准，不取消排位三排检查。未知实验体武器组合、无赛前 RP、
未知赛季或没有可评分字段时，`score=null`，`missingReason` 说明原因。
字段缺失保持缺失，不能用 0 填充。团队零击杀只移除团战贡献，剩余权重重新归一化；
缺时长按原函数使用定位全局旧倍率，并在证据中标记回退。

## 单局计算

1. 按实验体＋武器从 113 条映射确定七种定位之一。
2. 在 1,130 条组合基准中查段位＋实验体＋武器；缺失时依次回退到
   段位＋实验体、段位＋定位、段位总体。JSON 保留回退层级及样本数。
3. 团战贡献为 `min((K + 0.7*A)/TK, 1)`，先保留 6 位小数。
4. 按定位和时长桶修正伤害、死亡、视野、野怪的期望值。桶中点为
   750／1050／1350／1650／1950 秒，桶内倍率为 `clip(秒数/中点, .75, 1.25)`。
   伤害另使用全局曲线：8—10 分钟从旧倍率过渡，10—20 分钟使用全局倍率，
   20—25 分钟过渡回旧倍率，其他时长使用旧倍率。
5. 正向指标原始分为 `clip(65 + 45*(实际-期望)/max(abs(期望),1e-6),20,100)`；
   死亡指标将差值反向。原始分先保留 4 位小数。
6. 非对称调整：小于 50 时 `raw+3.75`；50—65 使用斜率 .75；
   65—80 使用斜率 1.2；超过 80 使用 `83+1.35*(raw-80)`；最终截断在 30—95。
7. 用定位权重对存在的指标加权，角色分保留 4 位小数。
8. 名次基础修正为 `6,4,2,1,-1,-2,-4,-6`。正修正乘
   `.2+.8*clip((角色分-45)/20,0,1)`，前三名另加
   `2/1.5/1 * clip((角色分-75)/15,0,1)`；负修正乘
   `1-.75*clip((角色分-60)/25,0,1)`。修正保留 4 位，最终总分截断到 0—100、保留 2 位。

所有舍入按 JavaScript `Math.round` 的规则实现，避免 Python 银行家舍入造成差异。

| 定位 | 伤害 | 团战 | 死亡 | 视野 | 野怪 |
|---|---:|---:|---:|---:|---:|
| 普攻输出 | 32 | 24 | 10 | 18 | 16 |
| 技能输出 | 36 | 25 | 10 | 18 | 11 |
| 刺客 | 30 | 32 | 10 | 18 | 10 |
| 普攻斗士 | 27 | 28 | 15 | 17 | 13 |
| 技能斗士 | 30 | 29 | 15 | 17 | 9 |
| 坦克 | 12 | 35 | 20 | 30 | 3 |
| 辅助 | 7 | 38 | 20 | 33 | 2 |

## 雷达与展示

六个轴严格使用公开 `productionAnalysisAxes.ts` 中的定义及顺序：

| 轴 | 公开源码逻辑 |
|---|---|
| 生存 `survival` | 单局生存指标调整分的加权均值 |
| 交战 `combat` | 分别聚合伤害、团战贡献的分数及原定位权重，再按聚合权重归一化合成 |
| 运营 `macro` | 野怪击杀指标调整分的加权均值 |
| 支援 `support` | 视野指标调整分的加权均值 |
| 结果 `finish` | `matchGradeOutcomeScore`，v3 为 null，因此按原源码回退到最终单局评分 |
| 稳定性 `consistency` | `clip(100 - 2*总体标准差(最终单局评分),0,100)`；至少 2 场 |

各组件先按原函数保留 2 位，再合成轴分；实际值、期望值、比值、权重、贡献值、
样本数和缺失状态均保留在 `analysisAxes` 中。默认 overall 聚合所有可评分局，
每局权重为 1，包含部分指标缺失但仍有最终分的比赛；不只取完整五项比赛。
`overallScore` 为结果轴分，界面标注“结果表现”，并非六轴平均。

`RadarScorer.score(sample, scope="character")` 保留公开源码的实验体聚合规则：
至少 10 场时按最终单局分排序，首尾各 `ceil(n*.1)` 场权重分别 .15／.75，中部 1；
不足 10 场均权。稳定性仍按原函数使用未加权分布。此规则只适用于已经筛选到同一
实验体的样本。公开版本的高尾权重与当前网站不同，不能宣称是当前线上实现。

置信度复用 ERCraft `config.ts`：小于 5 场样本不足、5—9 暂定、10—19 低、
20—39 中、40 及以上高；不据此收缩实际分数。

默认取最近 20 场，最多 60 场。JSON 提供请求样本数、可评分数、完整场次数、
各项覆盖率和逐局完整证据；均无有效数据的轴显示 `—`，不绘制伪造的零分多边形。
战绩列表的 `performance` 使用同一引擎。缓存键包含单局、六维版本和接口备选设置，
旧八维或五维卡片不会继续命中。

单局公开历史字母门槛与现站存在差异，单局 JSON 的
`gradeVersion=ercraft-public-fine-cuts.v1` 明确标识其来源。本地六维采用公开历史生产逻辑，与当前网站的
`s12-six-axis-role-reference.v2` 有版本差异；后者的当前完整源码及比较分布尚未取得。
本地 JSON 不生成当前人群百分位或相对等级。

## 总结图本地字母等级

`summary` 在原有六维数值之上增加 S/A/B/C/D/E 显示等级，规则版本为
`local-six-axis-bands.v1`。它按单个轴的原始数值分数使用固定区间：

| 有效分数范围 | 总结图等级 |
|---|---|
| 70–100 | S |
| 55–<70 | A |
| 40–<55 | B |
| 25–<40 | C |
| 10–<25 | D |
| 0–<10 | E |

此等级是本地显示规则，不改变单局数值核心、六维聚合、逐轴样本数或缺失状态，
也不声称复用了 ERCraft 网站当前等级、百分位或称号规则。分数必须是 0–100 内的
有限数值；缺失、布尔值、NaN、无穷大及越界值均返回 `grade=null`，不会降为 E。

总结图 section 和每个 axis 都提供 `gradeVersion=local-six-axis-bands.v1`，
axis 同时保留 `score`、`sampleCount`、`status`，`percentile` 仍为 `null`。
卡片以字母等级为主，并保留数值分数与有效场数，标明实际最近样本口径及本地计算来源。
`summary` 不调用评分接口备选；原有雷达图 payload 与展示保持不变。
只有总结图查询缓存键增加 `summaryGradeVersion`，确保旧版纯数值总结不会继续命中；
其他查询的缓存键不变。

## 评分接口备选

本地计算始终优先，默认不调用 ERCraft。显式开启备选：

```python
from erbs_plugin import ERBSConfig, radar

config = ERBSConfig(ercraft_api_fallback=True)
json_text = await radar("playername", config=config, format="json")
```

只有本地任一轴缺失时才尝试。先读取公开 summary 的稳定玩家 ID 与当前显示赛季，
再请求 `/api/player-analysis/roles?scope=recent20`，附带 `cacheOnly=true`、
`x-er-cache-only: true`、`x-er-no-upstream: true`，不提交刷新或生成任务。
仅支持最近 20 场口径；其他 count 不偷偷换成 20 场或全赛季。

成功时整体使用报告中的六轴 `combinedScore`，保留原始百分位、等级、版本、赛季、
源版本及不完整标记，来源为 `ercraft-api-fallback`；不会混合部分本地轴与部分接口轴。
报告必须满足同一玩家 ID、显示赛季、recent20 范围且六轴数值完整。备选不可用、
超时或口径不符时保留本地评分与缺失状态，`fallbackReason` 记录原因。
当前站点可能返回“最近 20 场报告不可用”，因此备选不保证有数据。

## 来源与复核

基准快照元数据注明采集时间为 2026-06-19、7 天窗口。它是冻结历史数据，
不会自动覆盖新实验体、武器和补丁。原 MIT 许可和逐文件 SHA256 随安装包分发。

`tests/fixtures/ercraft-scoring-reference.json` 由未经修改的 TypeScript 函数直接生成，
包含 215 局线上数值已核对的原始输入与完整计算证据，以及 115 个时长、七种定位、
缺失字段和回退边界用例。测试比较完整输出；DAK 字段适配另逐局比较原线上分数。
215 局覆盖五类定位，不能据此宣称另外两类已经有线上样本验证。

`ercraft-six-axis-reference.json` 的 14 组测试由未经修改的
`buildProductionAnalysisAxesForRows` 直接产生，覆盖空样本、单场、20 场、215 场混合
定位、缺失指标及 9/10/11/20/21 场的实验体加权边界；本地逐字段比较完整六维输出。
参考六维用固定请求段位测试聚合，本插件实际逐局输入仍按赛前 RP 选基准。

```bash
uv sync --extra render --group dev
uv run pytest -q
uv run ruff check src tests
# 用指定提交的干净源码目录和既有归档重建参考，不联网：
node scripts/update_scoring_reference.mjs /path/to/ERCraft-main /path/to/ercraft-evidence
```
