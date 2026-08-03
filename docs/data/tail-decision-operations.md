# 自持续尾盘决策系统运维指南

## 定位与边界

本系统提供本地决策支持、模拟记录和人工执行清单，不连接券商，不提交、撤销或修改任何真实订单。Tushare Token、周卡和高积分权限均不是日常运行依赖；Tushare 仅可作为以后明确启用的可选增强。

默认账户资产为 10,000 元，最大组合敞口为 8,000 元，单标的上限为 4,000 元。ETF 与个股共享同一个 8,000 元上限。

## 日常命令

在 `D:\work\gupiao\UZI-Skill` 下运行：

```powershell
python skills/deep-analysis/scripts/run_tail_decision.py --phase warmup
python skills/deep-analysis/scripts/run_tail_decision.py --phase preview
python skills/deep-analysis/scripts/run_tail_decision.py --phase final
python skills/deep-analysis/scripts/run_tail_decision.py --phase close
python skills/deep-analysis/scripts/run_tail_decision.py --phase exit_open
python skills/deep-analysis/scripts/run_tail_decision.py --phase exit_check
```

可用 `--as-of 2026-08-03T14:30:00+08:00` 固定时点，用 `--data-root` 指定历史归档，用 `--output-root` 指定报告根目录。验收或离线演练必须显式添加 `--offline-fixture`；该模式不发网络请求。

生产模式仅调用免费的东方财富和腾讯行情适配器。可在数据根目录放置 `tail_decision_universe.json`：

```json
{"etfs":["513050.SH"],"stocks":["600406.SH"]}
```

## 输出与状态

每次运行在标准输出写一行紧凑 JSON，并在以下目录追加 JSON 审计件和 Markdown 人工清单：

```text
<output-root>/reports/tail_decision/YYYYMMDD/<timestamp>_<run-id>.json
<output-root>/reports/tail_decision/YYYYMMDD/<timestamp>_<run-id>.md
```

状态含义：

- `recommended`：数据质量通过且存在受限组合；仍需人工确认和下单。
- `watch_only`：存在观察价值，但来源、时点或风险门槛不足；不得按实盘组合执行。
- `no_trade`：系统正常完成，策略主动不给组合。
- `blocked`：数据源、数据质量、系统或调度失败；不得解释为策略空仓。

## Windows 调度

先检查计划，不产生系统变更：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_tail_decision_tasks.ps1 -WhatIf
```

确认七个任务、Python 路径和时间后再安装或更新：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_tail_decision_tasks.ps1
```

脚本按固定任务名使用 `Register-ScheduledTask -Force`，因此重复执行会更新定义，不会生成重复任务。调度日志位于 `reports/tail_decision/scheduler`。

## `blocked` 恢复流程

1. 查看当次 JSON/Markdown 报告和 scheduler 日志中的机器原因。
2. 若为单源失败，先验证另一来源是否完整；单源结果最多为 `watch_only`。
3. 若为跨源价格偏差、过期行情或代码不一致，不得手工改成 `recommended`。
4. 检查系统时间、网络、数据根目录和本地交易日历边界。
5. 修复后以新的时点重新运行对应阶段；不要覆盖原 run-id 或删除失败记录。
6. 连续失败时保持空仓，并在恢复后重新开始前向样本计数。

## 版本与验证规则

- 阈值、因子、交易成本或退出规则变化必须提升 `strategy_version`，并形成新的前向实验。
- 已完成的决策和模拟记录只追加，不覆盖。
- 正式小额实盘前至少前向模拟 60 个交易日，并至少形成 40 笔可成交模拟订单。
- 放行门槛：扣除全部成本后净收益为正、Profit Factor 不低于 1.2、最大回撤不超过 8%，且 ETF 与个股分别报告。
- 2,000、4,000、8,000 元分阶段验证；不得通过降低门槛凑交易数。

## 当前安全限制

免费生产网关已具备双源行情和质量门，但在本地尾盘快照序列及历史特征尚未接入生产上下文时，会把 `production_ready` 保持为假并拒绝生成实盘组合。`close`、`exit_open`、`exit_check` 当前只保留阶段审计，持久化退出账本仍需后续里程碑完成。离线固定样本仅用于验收，不代表真实可交易信号。
