# 自持续尾盘决策系统实现与验证报告

## 结论

截至 2026-08-04，离线无 Token 决策链、双源质量门、ETF/个股策略、共享 8,000 元组合、追加式报告、成本模拟、本地 CLI 和 Windows 调度安装器均已实现。离线终版验收产生 6,396.98 元组合，未超过 8,000 元。

当前状态为“离线验收通过、生产安全降级可运行、尚未达到真实前向模拟启动条件”。生产网关在缺少本地尾盘快照序列和完整历史上下文时会主动 `no_trade`/`blocked`，不会用不完整数据生成组合。

## 验证证据

执行命令：

```powershell
python -m pytest skills/deep-analysis/scripts/tests/tail_decision -q
python -m pytest skills/deep-analysis/scripts/tests/test_trading_calendar_safety.py skills/deep-analysis/scripts/tests/test_providers_chain.py -q
python skills/deep-analysis/scripts/run_tail_decision.py --phase final --as-of 2026-08-03T14:30:00+08:00 --offline-fixture --output-root .cache/tail-decision-acceptance
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_tail_decision_tasks.ps1 -WhatIf
```

本轮结果：

- 尾盘决策测试：38 项通过。
- 交易日历与既有 provider 链回归：11 项通过。
- 无 `TUSHARE_TOKEN` 终版 CLI：退出码 0，状态 `recommended`，总敞口 6,396.98 元。
- 审计产物：JSON 与 Markdown 各 1 份；敏感词扫描无匹配。
- 调度器：`-WhatIf` 列出 7 个任务，不执行注册。

## 需求映射

- 本地归档读取：`ArchiveReader` 单元测试通过；生产工作流接入仍待完成。
- 免费实时双源：东方财富、腾讯 provider 及跨源一致/偏差质量测试通过。
- ETF/隔夜个股候选：策略硬过滤和排序测试通过；真实生产上下文仍待接入。
- 账户风控：ETF 与个股共享 8,000 元，单标的不超过 4,000 元，按整手分配。
- 状态语义：全源失败为 `blocked`；单源为 `watch_only` 且零分配；无候选为 `no_trade`。
- 记录与脱敏：JSON/Markdown 只追加，同 run-id 禁止覆盖，敏感键递归脱敏。
- 成本与退出：最低佣金、滑点、股票卖出印花税、T+1 和不可成交条件有测试覆盖。
- 本地调度：七阶段任务、隐藏运行、日志目录、幂等更新和 `-WhatIf` 已验证。
- 禁止范围：未增加券商连接、自动下单、179 项全目录恢复或历史分钟线补抓。

## 已知限制与后续闸门

1. 免费生产网关尚未把每日 14:00—15:00 追加快照读取为真实尾盘特征。
2. 现有 Tushare 日线归档尚未接入生产 `InstrumentContext` 的历史特征构建。
3. `close`、`exit_open`、`exit_check` 尚未读取前一交易日组合并维护持久化退出账本。
4. Windows 任务仅完成 `-WhatIf` 验证，未在本报告中实际注册。
5. 真实 60 交易日前向模拟尚未开始；计划起始日为 2026-08-04，但必须在上述生产上下文和退出账本闸门通过后正式计数。

在这些限制关闭前，系统只能用于离线验收和观察，不应进入真实资金阶段。
