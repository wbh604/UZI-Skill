#!/usr/bin/env python3
"""UZI-Skill 一键运行入口 — 适用于 Claude Code / Codex / Cursor / 命令行 / 任何 agent。

用法:
    python run.py 002273.SZ                   # 本地分析，浏览器打开
    python run.py 600519.SH --remote          # 分析完用 Cloudflare Tunnel 映射公网
    python run.py AAPL --no-browser           # 不打开浏览器（Codex/CI 环境）
    python run.py 贵州茅台 --remote            # 中文名 + 远程查看

参数:
    第一个参数: 股票代码或中文名
    --remote     分析完后启动 HTTP 服务 + Cloudflare Tunnel，生成公网链接
    --no-browser 不自动打开浏览器（适合无 GUI 的服务器/Codex 环境）
    --port PORT  HTTP 服务端口（默认 8976）

运行完会输出:
    1. HTML 报告本地路径
    2. 如果 --remote: 一个 https://xxx.trycloudflare.com 公网链接
"""
from __future__ import annotations  # v2.6 · Python 3.9 兼容（默认 macOS python3）

import os
import sys
import argparse
import subprocess
import shutil
import threading
import time
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

# ─── 编码修复 ───
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# ─── 路径设置 ───
ROOT_DIR = Path(__file__).parent.resolve()
SCRIPTS_DIR = ROOT_DIR / "skills" / "deep-analysis" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
os.chdir(str(SCRIPTS_DIR))


# ─── .env 加载（v2.3，零依赖，不覆盖已存在的 shell env）──
def _load_dotenv():
    """Load KEY=VALUE pairs from $REPO/.env into os.environ.

    Deliberately simple (no quoting games, no variable interpolation) — enough
    to pick up MX_APIKEY and friends. Existing shell env vars take precedence,
    so `export MX_APIKEY=...` always wins.
    """
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")  # strip optional quotes
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception as e:
        print(f"⚠️  .env 读取失败（忽略）: {e}")


_load_dotenv()


def _get_version() -> str:
    """v2.6 · Read version from .claude-plugin/plugin.json so banner stays in sync."""
    try:
        import json
        manifest = ROOT_DIR / ".claude-plugin" / "plugin.json"
        if manifest.exists():
            return json.loads(manifest.read_text(encoding="utf-8")).get("version", "?")
    except Exception:
        pass
    return "?"


def detect_environment() -> dict:
    """检测当前运行环境。"""
    env = {
        "has_browser": True,
        "has_cloudflared": shutil.which("cloudflared") is not None,
        "is_codex": os.environ.get("CODEX") == "1" or os.environ.get("OPENAI_API_KEY") is not None,
        "is_ci": os.environ.get("CI") is not None,
        "is_docker": Path("/.dockerenv").exists(),
        "is_ssh": "SSH_CONNECTION" in os.environ,
        "platform": sys.platform,
    }
    # 无 GUI 环境自动 no-browser
    if env["is_codex"] or env["is_ci"] or env["is_docker"] or env["is_ssh"]:
        env["has_browser"] = False
    # Linux 无 DISPLAY 也不开浏览器
    if sys.platform == "linux" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        env["has_browser"] = False
    return env


# 国内 pypi 镜像按速度排序（清华通常最快；阿里云在清华故障时兜底）
PYPI_MIRRORS = [
    ("清华大学", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("阿里云", "https://mirrors.aliyun.com/pypi/simple/"),
    ("中科大", "https://pypi.mirrors.ustc.edu.cn/simple/"),
    ("豆瓣", "https://pypi.douban.com/simple/"),
]


def _pip_install(args: list, index_url: str | None = None) -> int:
    """Run pip install; return exit code. `index_url=None` means use default pypi."""
    cmd = [sys.executable, "-m", "pip", "install"] + args + ["--quiet"]
    if index_url:
        cmd += ["--index-url", index_url, "--trusted-host", index_url.split("/")[2]]
    return subprocess.run(cmd, check=False).returncode


def check_dependencies():
    """检查并安装缺失依赖。pypi 访问不通时自动切国内镜像重试（支持中国大陆网络环境）。"""
    required = ["akshare", "requests"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        return

    print(f"⚠️  缺少依赖: {', '.join(missing)}")
    req_file = ROOT_DIR / "requirements.txt"
    args = ["-r", str(req_file)] if req_file.exists() else missing

    # 第一次尝试：默认 pypi（海外/Codex/美国网络最快）
    print(f"   [1/{len(PYPI_MIRRORS) + 1}] 尝试默认 pypi.org ...")
    if _pip_install(args) == 0:
        print("   ✓ 依赖安装完成\n")
        return

    # 失败后：自动切国内镜像（通常是大陆网络环境）
    print(f"   ⚠️  默认 pypi 安装失败（可能因网络受限），尝试国内镜像...")
    for i, (name, url) in enumerate(PYPI_MIRRORS, start=2):
        print(f"   [{i}/{len(PYPI_MIRRORS) + 1}] 尝试 {name} 镜像 ({url}) ...")
        if _pip_install(args, index_url=url) == 0:
            print(f"   ✓ 依赖安装完成（via {name}）\n")
            return

    print(f"   ❌ 所有镜像都失败了。请手动安装：")
    print(f"      pip install -r requirements.txt \\")
    print(f"          -i https://pypi.tuna.tsinghua.edu.cn/simple")
    print(f"   或参考 README.md 的\"网络受限环境\"章节\n")


def serve_report(report_path: Path, port: int = 8976) -> HTTPServer:
    """启动 HTTP 服务器托管报告目录。"""
    report_dir = report_path.parent
    os.chdir(str(report_dir))

    handler = SimpleHTTPRequestHandler
    httpd = HTTPServer(("0.0.0.0", port), handler)

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    filename = report_path.name
    print(f"\n📡 本地 HTTP 服务已启动:")
    print(f"   http://localhost:{port}/{filename}")
    return httpd


def start_cloudflare_tunnel(port: int = 8976):
    """启动 Cloudflare Tunnel，返回公网 URL。"""
    if not shutil.which("cloudflared"):
        print("\n⚠️  未检测到 cloudflared，正在尝试安装...")
        if sys.platform == "win32":
            print("   请手动安装: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
            print("   或: winget install Cloudflare.cloudflared")
            return None
        elif sys.platform == "darwin":
            subprocess.run(["brew", "install", "cloudflared"], check=False)
        else:
            # Linux
            subprocess.run(["bash", "-c",
                            "curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /tmp/cloudflared && chmod +x /tmp/cloudflared && sudo mv /tmp/cloudflared /usr/local/bin/"],
                           check=False)

        if not shutil.which("cloudflared"):
            print("   ❌ cloudflared 安装失败，跳过远程映射")
            return None
        print("   ✓ cloudflared 安装成功")

    print(f"\n🌐 正在启动 Cloudflare Tunnel (端口 {port})...")

    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # 从 stderr 里抓公网 URL（cloudflared 输出在 stderr）
    public_url = None
    start_time = time.time()
    while time.time() - start_time < 30:
        line = proc.stderr.readline()
        if not line:
            time.sleep(0.1)
            continue
        if "trycloudflare.com" in line or "cfargotunnel.com" in line:
            import re
            match = re.search(r"(https://[a-zA-Z0-9\-]+\.trycloudflare\.com)", line)
            if match:
                public_url = match.group(1)
                break

    if public_url:
        print(f"   ✅ 公网地址: {public_url}")
        print(f"   📱 手机扫码或发送链接即可查看报告")
        print(f"   ⏹  按 Ctrl+C 停止服务")
    else:
        print(f"   ⚠️  Tunnel 启动中... 请检查 cloudflared 输出")

    return public_url


def _maybe_prompt_update() -> None:
    """v2.14.0 · CLI 启动时检测 GitHub 新版本 · interactive y/s/n.

    - 非 TTY（CI / Codex sandbox / 管道重定向）自动 skip
    - UZI_NO_UPDATE_CHECK=1 env 禁用
    - 网络异常 / GH API 限流 → silent skip（不阻塞正常流程）
    - 用户选 s · 记到 .cache/_global/update_check.json · 下一版本来之前不再弹
    """
    if not sys.stdin.isatty():
        return
    try:
        from lib.update_check import check_for_update, format_prompt, handle_answer
    except Exception:
        return
    try:
        info = check_for_update()
        if info is None:
            return
        print(format_prompt(info))
        try:
            ans = input("请选择 [y/s/n]（回车默认 n）: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        print(handle_answer(ans, info.latest))
        print()
    except Exception as _e:
        # update check 永远不阻塞主流程
        pass


def main():
    parser = argparse.ArgumentParser(
        description="游资（UZI）Skills · 个股深度分析",
        epilog="示例: python run.py 贵州茅台 --remote",
    )
    parser.add_argument("ticker", nargs="?", default="002273.SZ",
                        help="股票代码或中文名 (如 600519.SH / AAPL / 贵州茅台)")
    parser.add_argument("--remote", action="store_true",
                        help="分析完后用 Cloudflare Tunnel 映射公网链接")
    parser.add_argument("--no-browser", action="store_true",
                        help="不自动打开浏览器")
    parser.add_argument("--port", type=int, default=8976,
                        help="HTTP 服务端口 (默认 8976)")
    parser.add_argument("--force-name", metavar="CODE",
                        help="绕过中文名纠错直接使用指定代码 (如 --force-name 000582.SZ)")
    parser.add_argument("--no-resume", action="store_true",
                        help="v2.6 · 强制重抓所有 fetcher（默认 resume：复用 .cache/{ticker}/raw_data.json 已有维度）")
    parser.add_argument("--enable-xueqiu-login", action="store_true",
                        help="v2.7.1 · 启用 XueQiu Playwright 登录态抓取实盘比赛持仓（首次需 `python -m lib.xueqiu_browser login`）")
    parser.add_argument("--depth", choices=["lite", "medium", "deep"], default=None,
                        help="v2.10.2 · 思考深度 · lite(1-2min) / medium(5-8min · 默认) / deep(15-20min · 含 Bull-Bear 辩论 + Segmental)")
    args = parser.parse_args()

    # v2.10.5 · run.py 是 CLI 直跑入口（agent 流程走 stage1/stage2 直接调用，不经 run.py）。
    # 设 UZI_CLI_ONLY=1 让 self_review 对 agent_analysis.json 缺失 / 低 coverage 做宽容处理
    # （降级为 warning，仍出报告）。
    os.environ.setdefault("UZI_CLI_ONLY", "1")

    # v2.14.0 · 自动检测 GitHub 新版本 · interactive prompt(y/s/n) · 非 TTY 静默
    _maybe_prompt_update()

    # v2.10.2 · 深度选择（优先级: --depth > UZI_DEPTH env > UZI_LITE env > 默认 medium）
    try:
        sys.path.insert(0, str(Path(__file__).parent / "skills" / "deep-analysis" / "scripts"))
        from lib.analysis_profile import get_profile, apply_profile_to_env, format_banner
        profile = get_profile(args.depth) if args.depth else get_profile()
        apply_profile_to_env(profile)
        print(f"\n{format_banner(profile)}\n")
    except Exception as _e:
        print(f"⚠️ 无法加载 analysis_profile: {_e}")

    # v2.3 · --force-name 直接覆盖
    if args.force_name:
        print(f"   [force-name] {args.ticker} → {args.force_name}")
        args.ticker = args.force_name

    # v2.7.1 · XueQiu login opt-in
    if args.enable_xueqiu_login:
        os.environ["UZI_XQ_LOGIN"] = "1"
        print("🔓 启用 XueQiu 登录态（19_contests 维度抓实盘组合）")

    env = detect_environment()

    print()
    print("━" * 50)
    print(f"🎯 游资（UZI）Skills v{_get_version()} · 深度分析引擎")
    print(f"   目标: {args.ticker}")
    print(f"   环境: {'Codex' if env['is_codex'] else 'Docker' if env['is_docker'] else 'SSH' if env['is_ssh'] else '本地'}")
    print(f"   浏览器: {'✓' if env['has_browser'] and not args.no_browser else '✗ (headless)'}")
    print(f"   Cloudflare: {'✓ 已安装' if env['has_cloudflared'] else '✗ 未安装'}")
    if args.remote:
        print(f"   远程模式: ✓ (完成后映射公网)")
    print("━" * 50)
    print()

    # 检查依赖
    check_dependencies()

    # v2.3 · MX API 状态提示
    if os.environ.get("MX_APIKEY"):
        print(f"🔑 MX_APIKEY 已设置 · 将优先使用东财妙想 API")
    else:
        print(f"ℹ️  未设置 MX_APIKEY · 走默认 akshare/xueqiu 链（可在 .env 里配置）")

    # v2.6 · resume 状态提示 + Codex 自适配
    cache_root = SCRIPTS_DIR / ".cache" / args.ticker
    has_cache = cache_root.exists() and (cache_root / "raw_data.json").exists()
    if has_cache and not args.no_resume:
        print(f"♻️  resume 模式 · 复用 .cache/{args.ticker}/raw_data.json 已有维度（用 --no-resume 强制重抓）")
    elif args.no_resume:
        print(f"🔄 --no-resume · 强制重抓所有 22 个 fetcher")
        os.environ["UZI_NO_RESUME"] = "1"

    if env["is_codex"]:
        print(f"⚙️  Codex 环境检测：")
        print(f"   - mini_racer 锁已启用 (akshare 并行 V8 安全)")
        print(f"   - per-fetcher 90s timeout 启用")
        if not os.environ.get("MX_APIKEY"):
            print(f"   ⛔ 强烈建议设 MX_APIKEY · push2 在境外环境常被反向限制")
        print(f"   - resume 默认开启（网络不稳，断了能续）")

    # 运行分析（抑制 run_real_test 内部的自动开浏览器）
    os.environ["UZI_NO_AUTO_OPEN"] = "1"
    from run_real_test import main as run_analysis, stage1 as _stage1, stage2 as _stage2

    # v2.3 · 先过 stage1，捕获中文名解析失败场景，不静默跑出空报告
    from lib.market_router import is_chinese_name
    if is_chinese_name(args.ticker) and not args.force_name:
        stage1_result = _stage1(args.ticker)
        # v2.10.4 · ETF/指数/可转债早退：stage1 已写 _resolve_error.json + 成分股清单
        if isinstance(stage1_result, dict) and stage1_result.get("status") == "non_stock_security":
            print(f"\n{'━' * 50}")
            print(f"🔴 {args.ticker} 是 {stage1_result.get('label', '非个股标的')}，已跳过 stage2。")
            print(f"   请选择上面列出的成分股之一重跑。")
            print(f"{'━' * 50}")
            sys.exit(0)
        if isinstance(stage1_result, dict) and stage1_result.get("status") == "name_not_resolved":
            cands = stage1_result.get("candidates", [])
            print(f"\n{'━' * 50}")
            print(f"❌ 无法确定股票: {args.ticker!r}")
            if not cands:
                print(f"   没有找到相似候选。请用准确的股票代码（如 600519.SH）重试。")
                sys.exit(2)
            print(f"   找到 {len(cands)} 个候选:")
            for i, c in enumerate(cands[:5], 1):
                print(f"     [{i}] {c['name']:<12s}  {c['code']}   (距离 {c.get('distance', '?')})")
            # 交互式确认（若 TTY）— agent/CI 环境直接退出让上层决策
            if sys.stdin.isatty():
                try:
                    choice = input("\n   选择候选编号（1-5），或直接回车取消: ").strip()
                    if choice and choice.isdigit() and 1 <= int(choice) <= len(cands):
                        picked = cands[int(choice) - 1]
                        print(f"   ✓ 使用 {picked['name']} ({picked['code']})")
                        args.ticker = picked["code"]
                        # 用选定代码重跑 stage1 然后 stage2
                        _stage1(args.ticker)
                        _stage2(args.ticker)
                    else:
                        print("   已取消。")
                        sys.exit(2)
                except (EOFError, KeyboardInterrupt):
                    print("\n   已取消。")
                    sys.exit(2)
            else:
                # Non-interactive: surface structured error and exit 2
                import json as _json
                print(_json.dumps(stage1_result, ensure_ascii=False, indent=2))
                sys.exit(2)
        else:
            # stage1 已经成功跑完 — 用它返回的 resolved ticker 跑 stage2（cache 是以解析后代码命名的）
            resolved = stage1_result.get("ticker") if isinstance(stage1_result, dict) else None
            _stage2(resolved or args.ticker)
            # 对齐 args.ticker 以便后续 report_dir 查找
            if resolved:
                args.ticker = resolved
    else:
        result = run_analysis(args.ticker)
        # v2.10.4 · ETF/指数/可转债早退（stage1 已输出成分股清单，不生成报告）
        if isinstance(result, dict) and result.get("status") in ("non_stock_security", "name_not_resolved"):
            print(f"\n{'━' * 50}")
            status = result.get("status")
            if status == "non_stock_security":
                print(f"🔴 {args.ticker} 是 {result.get('label', '非个股标的')}，已跳过 stage2。")
                if result.get("top_holdings"):
                    print(f"   请从上方列出的成分股里选一只重跑，例如：python run.py {result['top_holdings'][0]['code']}")
                else:
                    print(f"   {result.get('what_to_do', '请改用个股代码重跑。')}")
            else:
                print(f"🔴 {args.ticker} 股票名无法解析")
            print(f"{'━' * 50}")
            sys.exit(0)

    # 找到生成的报告
    from datetime import datetime
    from lib.market_router import parse_ticker
    ti = parse_ticker(args.ticker)
    date = datetime.now().strftime("%Y%m%d")
    report_dir = SCRIPTS_DIR / "reports" / f"{ti.full}_{date}"
    standalone = report_dir / "full-report-standalone.html"

    if not standalone.exists():
        # 尝试找最新的报告
        reports_root = SCRIPTS_DIR / "reports"
        if reports_root.exists():
            dirs = sorted(reports_root.glob(f"{ti.full}_*"), reverse=True)
            for d in dirs:
                candidate = d / "full-report-standalone.html"
                if candidate.exists():
                    standalone = candidate
                    report_dir = d
                    break

    if not standalone.exists():
        print(f"\n❌ 报告文件未找到: {standalone}")
        return

    print(f"\n{'━' * 50}")
    print(f"📄 报告路径: {standalone}")
    print(f"   大小: {standalone.stat().st_size // 1024} KB")

    # 打开浏览器（本地模式）
    if env["has_browser"] and not args.no_browser and not args.remote:
        import webbrowser
        webbrowser.open(standalone.as_uri())
        print(f"   🌐 已在浏览器中打开")

    # 远程模式: HTTP server + Cloudflare Tunnel
    if args.remote:
        httpd = serve_report(standalone, args.port)
        filename = standalone.name
        public_url = start_cloudflare_tunnel(args.port)

        if public_url:
            full_url = f"{public_url}/{filename}"
            print(f"\n{'━' * 50}")
            print(f"📱 远程查看地址:")
            print(f"   {full_url}")
            print(f"{'━' * 50}")
            print(f"\n发送这个链接到手机就能看报告。")
            print(f"按 Ctrl+C 停止服务。\n")

            # 如果有浏览器也打开
            if env["has_browser"] and not args.no_browser:
                import webbrowser
                webbrowser.open(full_url)

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n⏹  服务已停止")
                httpd.shutdown()
        else:
            # cloudflared 失败，至少提供本地 HTTP
            print(f"\n   本地访问: http://localhost:{args.port}/{filename}")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n⏹  服务已停止")
                httpd.shutdown()
    elif not env["has_browser"] or args.no_browser:
        # 无浏览器环境，提示用户
        print(f"\n💡 提示: 当前环境无法打开浏览器")
        print(f"   方式 1: 下载文件到本地打开")
        print(f"   方式 2: python run.py {args.ticker} --remote  ← 生成公网链接，手机就能看")

    print(f"{'━' * 50}")
    print(f"✅ 完成!")


if __name__ == "__main__":
    main()
