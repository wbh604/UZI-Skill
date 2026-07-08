# UZI Web / Docker 简易封装

这是 `UZI-Skill` 的轻量 Web 封装版本，参考 `daily_stock_analysis` 的 Docker 启动方式和 `ai-goofish-smart-monitor` 的本地 Web 管理体验。

当前 Web 版包含：

- 输入股票代码 / 名称
- 选择 `lite` / `medium` / `deep`
- 后台调用现有 `python run.py`
- 生成 `HTML` 报告
- 浏览器查看历史报告
- 批量提交多个标的并排队执行
- 可选钉钉群机器人通知
- 可选环境变量驱动的每日定时任务

> 定位：`daily_stock_analysis` 更适合自选股批量日报、行情监控和综合推送；`UZI Web` 更适合单只或少量重点股票的 HTML 深度报告。

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

# 可选：Web 默认分析深度：lite / medium / deep
UZI_WEB_DEFAULT_DEPTH=lite

# 可选：同时运行任务数。UZI 报告较重，建议保持 1。
UZI_WEB_MAX_PARALLEL_JOBS=1
UZI_WEB_MAX_QUEUE_SIZE=30

# 可选：禁用缓存，强制重新拉取
STOCK_NO_CACHE=
```

---

## 3. Web 页面使用

页面包含：

- 单票分析：输入 `600519.SH`、`NVDA`、`00700.HK` 等
- 批量分析：一行一个或逗号分隔，例如 `QQQ,NVDA,TSLA`
- 分析深度：
  - `lite`：快速初筛
  - `medium`：常规分析
  - `deep`：深度研究
- 强制重抓数据：对应 `--no-resume`
- 当前任务列表和日志
- 历史报告列表

生成成功后，点击“打开 HTML 报告”即可查看导出的 `index.html`。

---

## 4. 钉钉通知

支持钉钉群自定义机器人 Webhook。`.env` 示例：

```env
# 钉钉群机器人的完整 Webhook URL
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxxx

# 如果钉钉机器人开启了“加签”，填写 SEC 开头的密钥；未开启可留空
DINGTALK_SECRET=

# Web 页面提交任务时，是否默认勾选“完成后钉钉通知”
UZI_DINGTALK_NOTIFY_DEFAULT=false

# 如果做了公网反代，填写公网地址，用于钉钉消息里的报告链接
UZI_WEB_PUBLIC_BASE_URL=
```

钉钉机器人如果启用了关键词安全，建议关键词设置为：

```text
股票
```

UZI Web 的钉钉文本会自动包含“股票”关键词。

---

## 5. 定时任务

定时任务通过环境变量配置，适合每天固定时间跑少量重点标的。

```env
UZI_SCHEDULE_ENABLED=true
UZI_SCHEDULE_TIMES=21:30,23:30
UZI_SCHEDULE_TICKERS=QQQ,NVDA,TSLA
UZI_SCHEDULE_DEPTH=lite
UZI_SCHEDULE_NOTIFY=true
```

说明：

- 时间格式为 `HH:MM`，多个时间用英文逗号分隔。
- 定时任务使用容器内本地时间。
- 默认按队列执行，`UZI_WEB_MAX_PARALLEL_JOBS=1` 时会一只一只跑。
- 大量标的或日报类场景建议继续使用 `daily_stock_analysis`。

修改 `.env` 后重建容器：

```bash
docker compose -f docker/docker-compose.yml up -d --build --force-recreate
```

---

## 6. 持久化目录

Docker Compose 默认挂载这些目录：

```text
data/         Web 运行数据
web-reports/  Web 导出的 HTML 报告
cache/        UZI 数据缓存
reports/      UZI 原始报告目录
```

删除容器不会删除这些目录中的历史报告。

---

## 7. 常用命令

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

## 8. 当前版本边界

当前版本仍然保持轻量：

- 不做登录/多用户
- 不做复杂配置中心
- 不做报告清理按钮
- 不替代 Claude Code Skill
- 不定位为大规模股票池扫描器

后续如需要，可以继续扩展：

- 飞书/企业微信推送
- Web 页面保存 `.env` 配置
- 报告清理按钮
- Windows 一键启动脚本

---

## 9. 投资风险说明

本工具只用于学习、研究和复盘辅助，不构成投资建议。
