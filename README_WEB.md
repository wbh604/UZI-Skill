# UZI Web / Docker 简易封装

这是 `UZI-Skill` 的轻量 Web 封装版本，参考 `daily_stock_analysis` 的 Docker 启动方式和 `ai-goofish-smart-monitor` 的本地 Web 管理体验，但第一版只保留最核心功能：

- 输入股票代码 / 名称
- 选择 `lite` / `medium` / `deep`
- 后台调用现有 `python run.py`
- 生成 `HTML` 报告
- 浏览器查看历史报告

> 定位：`daily_stock_analysis` 适合自选股批量分析、定时任务和钉钉日报；`UZI Web` 适合单只重点股票做深度 HTML 报告。

---

## 1. Docker 启动

在项目根目录执行：

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

打开：

```text
http://localhost:8977
```

---

## 2. 可选配置

可以在项目根目录创建 `.env`，Docker Compose 会读取其中变量并注入容器：

```env
# 可选：东财妙想 API Key，可提升中文名纠错和行情快照稳定性
MX_APIKEY=

# 可选：禁用缓存，强制重新拉取
STOCK_NO_CACHE=
```

---

## 3. Web 页面使用

页面包含：

- 股票代码输入框，例如：`600519.SH`、`NVDA`、`00700.HK`
- 分析深度：
  - `lite`：快速初筛
  - `medium`：常规分析
  - `deep`：深度研究
- 强制重抓数据：对应 `--no-resume`
- 当前任务日志
- 历史报告列表

生成成功后，点击“打开 HTML 报告”即可查看 `full-report-standalone.html` 导出的 `index.html`。

---

## 4. 持久化目录

Docker Compose 默认挂载这些目录：

```text
data/         Web 运行数据
web-reports/  Web 导出的 HTML 报告
cache/        UZI 数据缓存
reports/      UZI 原始报告目录
```

删除容器不会删除这些目录中的历史报告。

---

## 5. 常用命令

查看服务状态：

```bash
docker compose -f docker/docker-compose.yml ps
```

查看日志：

```bash
docker compose -f docker/docker-compose.yml logs -f uzi-web
```

重启：

```bash
docker compose -f docker/docker-compose.yml restart uzi-web
```

停止：

```bash
docker compose -f docker/docker-compose.yml down
```

---

## 6. 当前版本边界

第一版故意保持简单：

- 不做批量自选股分析
- 不做定时任务
- 不做登录/多用户
- 不做复杂配置中心
- 不替代 Claude Code Skill

后续如需要，可以继续扩展：

- 钉钉/飞书推送报告摘要
- 批量报告队列
- 报告清理按钮
- `.env` Web 配置页
- Windows 一键启动脚本

---

## 7. 投资风险说明

本工具只用于学习、研究和复盘辅助，不构成投资建议。
