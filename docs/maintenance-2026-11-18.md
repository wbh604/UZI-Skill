# 社区更新审核（2026-11-18）

本轮审核覆盖 4 个 PR 和 2 个 Bug Issue。通过验收的改动以维护提交集成，不直接合并原 PR 分支。manifest 保持 v3.9.4。

## 接入与补修

- [PR #129](https://github.com/wbh604/UZI-Skill/pull/129)，对应 [#127](https://github.com/wbh604/UZI-Skill/issues/127)、[#128](https://github.com/wbh604/UZI-Skill/issues/128)：legacy Wave 2/3 改用已有的可终止子进程调度器，避免线程超时后 shutdown 继续等待。保留 per-fetcher 和批次超时、失败维度标记。
- PR 原实现等待整批进程返回后才保存。增加可选完成回调，在采集中每完成 3 个维度保存一次，批次完成再保存；回调异常仍清理活动子进程。首次 basic 采集沿用旧路径，不宣称整个 legacy 入口均有进程硬超时。
- 期货采集等原材料维度采集完毕后再构造参数，也支持已缓存的原材料，仍受 Wave 2 总预算限制。
- 护城河 scores 为 null、非对象、非有限数或越界时不崩溃；缺失评分不再伪装成默认分，行业吸引力不展示为真实百分比。有效 BCG 输入仍可单独判断；缺少份额或行业增速时显示未评估。
- [PR #123](https://github.com/wbh604/UZI-Skill/pull/123)：接入系统 Chrome/Edge 探测与 Playwright 调用，不采用 PR 附带的全仓版本升级。修正 macOS 包内可执行文件名中的空格，拒绝目录和不可执行文件；显式 UZI_BROWSER_PATH 无效时报配置错误，不静默改用其他浏览器。

## 浏览器配置

未配置时先查找系统 Chrome/Edge/Chromium，找不到则沿用 Playwright 自带 Chromium。不会操作日常浏览器用户资料；雪球仍使用独立的 UZI profile。

可选指定可执行文件：

```bash
export UZI_BROWSER_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

自定义浏览器版本与 Playwright 之间仍可能不兼容，不能承诺任意本地版本均可运行。参考 [Playwright 官方启动参数](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-option-executable-path)。

## 当次暂缓接入

后续处理见[资金流来源与统计口径](capital-flow-sources.md)和[日文 README](../README_JA.md)。以下保留原审核记录。

- [PR #124](https://github.com/wbh604/UZI-Skill/pull/124)：新浪资金流 fallback 方向可取，但当前实现把缺失、非法字段转成 0，可能制造有效零值；非 SZ 一律映射 SH，可能错查北交所；新浪与东财的分类阈值和单位不能仅凭字段名认定完全一致。需补齐字段有效性、市场白名单、日期排序与去重、单位和来源口径验证，再接入评分链。当前工作区未启用此备用源。
- [PR #126](https://github.com/wbh604/UZI-Skill/pull/126)：日文入口有价值，但正文仍有旧评委人数、过时架构与测试数量，以及对联网和输出可靠性的过强描述。需与当前中文文档同步后再发布，避免新增一份过时使用指南。当前工作区未新增日文 README。

## 验证与边界

验证结果：全量 `pytest skills/deep-analysis/scripts/tests -q --tb=short` 为 **1027 passed**。系统 Chrome 实际启动成功，合成竞争分析页面显示“未评估”且不绘制默认雷达图。

使用离线回归、合成数据和本地浏览器启动检查；不跑真实个股报告，不把测试通过等同于上游数据源可用、投资效果或收益验证。轮动输入、排名、持仓、报告和截图继续仅限本地；本轮不发布这些资料。
