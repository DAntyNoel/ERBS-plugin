# Third-party notices

- ERCraft, MIT License, https://github.com/adgjmptw2/ERCraft-main
  - Copyright (c) 2026 MINE9289.
  - The Python scoring core is adapted from commit
    `93dd2a13345c53e5a6fb271c92d42b9fb62c7761` (`roleScoreV3.ts`,
    `teamLuckRoleScore.ts`, `asymmetricMetricAdjustment.ts`, `damageTimeGlobal.ts`,
    `baselineStore.ts`, `productionAnalysisAxes.ts`, the robust aggregate constants,
    and the fine-grade/confidence configuration).
  - Five baseline/role/duration JSON artifacts are redistributed unchanged. Their checksums and
    source paths are in `src/erbs_plugin/scoring/data/provenance.json`.
    The upstream copyright and full permission notice are preserved in
    `src/erbs_plugin/scoring/data/LICENSE.txt` and included in built packages.
  - The local summary card references the public play-card layout at
    https://ercraft.net/player/dantynoel (inspected 2026-10-21). Drawing code is implemented
    in Python/Skia. Website character illustrations and fonts are not bundled; an explicit
    local 1024×1536 background can be supplied by the caller. The local card displays raw
    historical six-axis scores rather than ERCraft's current percentile grades or titles.

- IHAHBOT, Apache License 2.0, https://github.com/team-lument/IHAHBOT
  - Referenced for Eternal Return asset taxonomy and image-first output architecture.
- re-yano, MIT License, https://github.com/skeep194/re-yano
  - Referenced for separation between API/domain services and platform identity adapters.
- miao-plugin, MIT License, https://github.com/yoimiya-kokomi/miao-plugin
  - Referenced for shared HTML layout and local-resource container rendering patterns.
- EternalReturnLoMu, https://github.com/LuoRenMu/EternalReturnLoMu
  - Public command behavior and DAK.GG request/data contracts were inspected at commit
    `e04e650a9d8ce7f370171ef13c256baddf9896f3`. No license file was found in that snapshot.
    The Python collectors, parser and Skia layout are independently implemented; Kotlin source,
    templates and assets from that project are not redistributed.
- Rajdhani, SIL Open Font License 1.1, https://github.com/google/fonts/tree/main/ofl/rajdhani
  - Bundled in SemiBold and Bold weights for the archived HTML renderer under `legacy`.
- Eternal Return is a trademark of Nimble Neuron Corporation.
  - The bundled two-line Chinese/English wordmark is independently generated for this project; it
    is not an official Eternal Return logo and does not indicate endorsement by Nimble Neuron.

The ERBS-plugin templates are independently implemented. waves-plugin templates are not copied,
modified, or redistributed. This project is not affiliated with or endorsed by Nimble Neuron.
