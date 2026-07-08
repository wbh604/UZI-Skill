# UZI Web / Docker 部署说明

这是 `UZI-Skill` 的 DSA 风格 Web 底座封装：保留 UZI 原有 `run.py` 分析引擎，把 Web/API、任务队列、定时任务、钉钉通知和 Docker 部署拆成独立模块。

适用场景：

- 单只股票生成 UZI HTML 深度报告
- 少量重点票批量排队分析
- 每天固定时间自动跑重点票
- 生成报告后推送钉钉群
- 用 Docker 给普通用户做一键部署

---

## 1. 架构说明

```text
main.py
├─ --serve-only  -> server 服务：FastAPI / WebUI / API
└─ 默认模式      -> analyzer 服务：定时任务 / 后台提交分析

src/
├─ api/app.py                    Web/API 路由
├─ config.py                     环境变量和目录配置
└─ services/
   ├─ uzi_runner.py              调用原有 run.py
   ├─ job_queue.py               任务队列和批量分析
   ├─ scheduler.py               定时任务
   ├─ dingtalk_notifier.py       钉钉通知
   └─ models.py                  Job 数据结构
```

`web/app.py` 只保留兼容入口，真正的 FastAPI 应用在 `src/api/app.py`。

---

## 2. Docker 启动

### 只启动 Web 页面

```bash
docker compose -f docker/docker-compose.yml up -d --build server
```

打开：

```text
http://localhost:8977
```

### 启动 Web + 定时任务

```bash
docker compose -f docker/docker-compose.yml up -d --build server analyzer
```

服务说明：

```text
server    Web/API 服务，负责页面、手动单票、批量提交、报告查看
analyzer  定时任务服务，负责按 .env 配置自动提交分析任务
```

---

## 3. 目录规范

Docker Compose 默认挂载这些目录：

```text
data/       Web 运行数据
logs/       运行日志
reports/    HTML 报告导出目录
cache/      UZI 数据缓存
```

报告默认导出到：

```text
reports/jobs/<job_id>/index.html
```

---

## 4. 配置文件

复制配置文件：

```bash
cp .env.example .env
```

常用配置：

```env
UZI_WEB_PORT=8977
UZI_WEB_DEFAULT_DEPTH=lite
UZI_WEB_MAX_PARALLEL_JOBS=1
UZI_WEB_MAX_QUEUE_SIZE=30

# 可选：东财妙想 API Key，可提升中文名纠错和行情快照稳定性
MX_APIKEY=
```

---

## 5. Web 页面使用

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

## 6. 钉钉通知

支持钉钉群自定义机器人 Webhook。`.env` 示例：

```env
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxxx
DINGTALK_SECRET=
UZI_DINGTALK_NOTIFY_DEFAULT=false
UZI_WEB_PUBLIC_BASE_URL=
```

说明：

- `DINGTALK_SECRET` 只在机器人开启加签时填写。
- 钉钉机器人如果启用了关键词安全，建议关键词设置为 `股票`。
- UZI Web 的钉钉文本会自动包含“股票”关键词。
- 如果做公网反代，设置 `UZI_WEB_PUBLIC_BASE_URL`，钉钉消息里会带完整报告链接。

---

## 7. 定时任务

定时任务由 `analyzer` 服务执行，不放在 `server` 里。

`.env` 示例：

```env
UZI_SCHEDULE_ENABLED=true
UZI_SCHEDULE_TIMES=21:30,23:30
UZI_SCHEDULE_TICKERS=QQQ,NVDA,TSLA
UZI_SCHEDULE_DEPTH=lite
UZI_SCHEDULE_NOTIFY=true
```

启动：

```bash
docker compose -f docker/docker-compose.yml up -d --build analyzer
```

说明：

- 时间格式为 `HH:MM`，多个时间用英文逗号分隔。
- 定时任务使用容器内本地时间。
- 默认按队列执行，`UZI_WEB_MAX_PARALLEL_JOBS=1` 时会一只一只跑。
- 大量标的或日报类场景建议继续使用 `daily_stock_analysis`。

---

## 8. 常用命令

查看服务状态：

```bash
docker compose -f docker/docker-compose.yml ps
```

查看 Web 日志：

```bash
docker compose -f docker/docker-compose.yml logs -f server
```

查看定时任务日志：

```bash
docker compose -f docker/docker-compose.yml logs -f analyzer
```

重启：

```bash
docker compose -f docker/docker-compose.yml restart server analyzer
```

停止：

```bash
docker compose -f docker/docker-compose.yml down
```

修改 `.env` 后重建：

```bash
docker compose -f docker/docker-compose.yml up -d --build --force-recreate server analyzer
```

---

## 9. 当前版本边界

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

## 10. 投资风险说明

本工具只用于学习、研究和复盘辅助，不构成投资建议。
