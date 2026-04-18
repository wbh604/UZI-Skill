# 数据源 Providers 指南

UZI-Skill 采用多数据源 + 自动 failover 架构 (v2.10.3 起)。本文档列出**所有能接入**的 providers 及配置方法。

**v2.10.6**：providers chain 正式被 `data_sources._kline_a_share_chain` 调用（此前 0 采用）。诊断工具：
```bash
python -m lib.providers              # 看所有 provider 健康度
python -m lib.providers chain A      # 看 A 股每个维度的优先级链
UZI_PROVIDERS_KLINE=baostock,akshare python -m lib.providers chain A kline
```

## 优先级模型

每个 fetcher 请求时，按这个顺序尝试：

```
主源 akshare (0 key, 默认)
  ↓ 挂了
并行冗余 efinance (0 key, pip install efinance)
  ↓ 挂了
官方 API tushare (需 TUSHARE_TOKEN)
  ↓ 挂了
兜底 baostock (0 key, 已装)
```

可用 `UZI_PROVIDERS_<DIM>` 覆盖单维度优先级，如：
```bash
# 财务数据强制优先走 tushare（忽略 akshare）
export UZI_PROVIDERS_FINANCIALS=tushare,akshare
```

## 已实现的 Providers

### 🟢 `akshare` · 零配置主源

**状态**: 已随 `requirements.txt` 安装
**特色**: 覆盖最广（A/港/美股 + 基金 + 期货 + 宏观）
**限制**: 爬虫聚合，字段偶有不稳；GFW 代理时挂

### 🟢 `baostock` · 零配置兜底

**状态**: 已随 `requirements.txt` 安装
**特色**: 官方合作，A 股历史财报 + K 线稳定
**限制**: 仅 A 股 · 需要 `login()`

### 🟡 `efinance` · 零 key 并行冗余（推荐装）

**启用**:
```bash
pip install efinance
```

**特色**:
- 内部走东财 + 同花顺 + 新浪聚合爬虫
- 国内网络稳定性 ≥ akshare
- 覆盖 A/港/美股 + ETF + 基金 + 可转债
- 与 akshare 字段格式不同，作为失败冗余

**建议**: akshare 冷启动慢 / 代理不通时，efinance 常能救场

### 🟡 `tushare` · 官方 API（推荐注册）

**启用**:
```bash
# 1. 访问 https://tushare.pro 注册（免费 120 积分）
# 2. 个人中心 → 接口 TOKEN 复制
pip install tushare
export TUSHARE_TOKEN=your_token_here
```

**特色**:
- **字段质量最高** · ISO 清洗流程 · 官方授权
- **财报深度 5-10 年** · 利润表 / 资产负债表 / 现金流 三表齐全
- **机构级衍生数据** · 龙虎榜席位细节 / 北向实时 / 期货逐笔
- **国内网络稳定** · 走 tushare.pro HTTPS（不是 GFW 风险路径）

**限制**: 免费 120 积分够跑 50 次左右；常用接口需 2000+ 分（贡献数据 / 充值）

## 未实现但国内能用的 Providers

按 ROI 排，想加随时欢迎 PR：

### 零 key · 开源库

| Provider | pip 包 | 覆盖 | 亮点 |
|---|---|---|---|
| **adata** | `pip install adata` | A 股多源聚合 | 新兴开源，国内稳 |
| **AkTools HTTP** | `pip install aktools` | 同 akshare | HTTP 网关模式，可做远程共享 cache |
| **stockstats** | `pip install stockstats` | 技术指标 | 计算库，不是数据源 |

### 需要账号 · 券商 OpenAPI（免费）

| Provider | 账号条件 | 特色 |
|---|---|---|
| **富途 Futu OpenAPI** | 富途开户 | 港美股 + A 股实时 L2 盘口 |
| **长桥 Longbridge OpenAPI** | 长桥开户 | 港美股 · SDK 免费 |
| **老虎 Tiger API** | 老虎开户 | 美股为主 |
| **华泰 iQuant** | 华泰开户 | A 股量化环境 |

### 需要账号 · 研究平台（免费额度）

| Provider | 免费额度 | 特色 |
|---|---|---|
| **聚宽 JQData** | 100 次/日 | A 股研究，本地跑 |
| **米筐 RiceQuant** | 200 次/日 | 覆盖期货期权 |
| **QuantAxis** | 本地部署 | 量化框架 · 自建数据源 |

### 境外 · 美股专用（代理/VPN 才能用）

| Provider | 免费配额 | 特色 |
|---|---|---|
| **Financial Modeling Prep** | 250 次/日 | 美股 5 年财报 + 隐含 DCF |
| **Alpha Vantage** | 500 次/日 | 美股实时 + 技术指标 + 外汇 |
| **Polygon.io** | 5 次/分钟（历史） | 美股 tick-level |
| **OpenBB Platform** | 自身整合 10+ 源 | Python SDK `openbb` |
| **stooq.com** | 无限（直连 HTTP） | 美股/欧股日级历史 |

### 付费（不默认接，用户有授权时可自接）

Wind / 万得 · Choice · iFinD · Bloomberg · Refinitiv — 价钱不合理

## Health Check

查看当前所有 provider 的可用性：

```bash
cd skills/deep-analysis/scripts
python -c "from lib import providers; import json; print(json.dumps(providers.health_check(), ensure_ascii=False, indent=2))"
```

输出示例：
```json
{
  "akshare":  {"available": true,  "markets": ["A","H","U"], "requires_key": false, "status": "ok"},
  "efinance": {"available": false, "status": "unavailable"},
  "tushare":  {"available": false, "markets": ["A"], "requires_key": true, "status": "unavailable"},
  "baostock": {"available": true,  "markets": ["A"], "requires_key": false, "status": "ok"}
}
```

## 建议配置（国内用户）

**极简**（默认）：
```
akshare + baostock + DDGS
```

**标准**（推荐）：
```bash
pip install efinance
# akshare + efinance + baostock（+ DDGS）
```

**最稳**：
```bash
pip install efinance tushare
export TUSHARE_TOKEN=xxx
# 四层冗余，GFW 挂也能跑
```

**含境外**（需代理）：
```bash
pip install efinance tushare openbb
export TUSHARE_TOKEN=xxx
export FMP_API_KEY=xxx
```
