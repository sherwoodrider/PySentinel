"""PySentinel 运行入口。

用法示例::

    python main.py                          # 跑全部用例
    python main.py -n auto                  # 自动按 CPU 核数并行
    python main.py -k relevance             # 只跑名字含 relevance 的用例
    python main.py -m "not ai"              # 跳过所有 AI 判定（快速冒烟）
    python main.py --reruns 2 --rerun-delay 1
    python main.py --no-ai --headed --parallel 4
    python main.py --allure                 # 生成 allure 结果目录

对比原版 ``pytest.main(["-s", "-k super"])``：
不再硬编码筛选项，支持并行、失败重试、环境切换与报告产出。
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def _plugin_available(*names: str) -> bool:
    """判断某个 pytest 插件是否已安装，避免拼出必然失败的参数。"""
    import importlib.util

    for name in names:
        try:
            if importlib.util.find_spec(name) is not None:
                return True
        except (ImportError, ValueError):
            continue
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="PySentinel",
        description="PySentinel 智能测试框架运行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sel = parser.add_argument_group("用例选择")
    sel.add_argument("-k", "--keyword", default=None, help="按表达式筛选用例名，如 -k relevance")
    sel.add_argument("-m", "--marker", default=None, help="按 marker 筛选，如 -m \"not ai\"")
    sel.add_argument("target", nargs="*", default=None, help="指定文件/目录，留空则用 pytest.ini 的 testpaths")

    run = parser.add_argument_group("执行策略")
    default_workers = os.cpu_count() or 1
    run.add_argument("-n", "--parallel", default=None, metavar="N",
                     help=f"并行 worker 数，auto 表示自动（当前 {default_workers} 核）")
    run.add_argument("--reruns", type=int, default=0, help="失败自动重试次数（需 pytest-rerunfailures）")
    run.add_argument("--rerun-delay", type=float, default=1.0, help="重试间隔秒数")
    run.add_argument("-x", "--exitfirst", action="store_true", help="首次失败即停止")
    run.add_argument("--lf", action="store_true", help="只跑上次失败的用例")
    run.add_argument("--timeout", type=int, default=None, help="单用例超时秒数（需 pytest-timeout）")

    env = parser.add_argument_group("环境与AI")
    env.add_argument("--no-ai", action="store_true", help="关闭 AI 分析与判定")
    env.add_argument("--headed", action="store_true", help="浏览器有头模式")
    env.add_argument("--env-file", default=None, help="指定配置文件路径")
    env.add_argument("--slow-threshold", type=float, default=10.0, help="慢用例阈值（秒）")

    rep = parser.add_argument_group("输出与报告")
    rep.add_argument("--allure", action="store_true", help="生成 allure 结果目录 allure-results")
    rep.add_argument("--html", default=None, metavar="PATH", help="生成 HTML 报告路径")
    rep.add_argument("-q", "--quiet", action="store_true", help="精简输出")
    rep.add_argument("-v", "--verbose", action="count", default=1, help="详细程度，可叠加 -vv")
    return parser


def build_args(args: argparse.Namespace) -> list:
    argv: list = []

    # --- 执行策略 ---
    if args.parallel:
        if _plugin_available("xdist", "pytest_xdist"):
            workers = multiprocessing.cpu_count() if args.parallel == "auto" else args.parallel
            # loadscope：同一 module/class 的用例分到同一 worker，避免会话级浏览器被反复创建
            argv += ["-n", str(workers), "--dist", "loadscope"]
        else:
            print("[warn] 未安装 pytest-xdist，忽略并行参数。pip install pytest-xdist")
    if args.reruns:
        if _plugin_available("rerunfailures", "pytest_rerunfailures"):
            argv += ["--reruns", str(args.reruns), "--reruns-delay", str(args.rerun_delay)]
        else:
            print("[warn] 未安装 pytest-rerunfailures，忽略重试参数。pip install pytest-rerunfailures")
    if args.timeout and _plugin_available("pytest_timeout"):
        argv += ["--timeout", str(args.timeout)]
    if args.exitfirst:
        argv.append("-x")
    if args.lf:
        argv.append("--lf")

    # --- 框架自有参数 ---
    if args.no_ai:
        argv.append("--no-ai")
    if args.headed:
        argv.append("--headed")
    if args.env_file:
        argv += ["--env-file", args.env_file]
    argv += ["--slow-threshold", str(args.slow_threshold)]

    # --- 选择 ---
    if args.keyword:
        argv += ["-k", args.keyword]
    if args.marker:
        argv += ["-m", args.marker]

    # --- 报告 ---
    if args.allure and _plugin_available("allure", "allure_pytest"):
        argv += ["--alluredir", str(PROJECT_ROOT / "allure-results")]
    elif args.allure:
        print("[warn] 未安装 allure-pytest，忽略 --allure。pip install allure-pytest")
    if args.html:
        argv += [f"--html={args.html}", "--self-contained-html"]

    # --- 输出 ---
    argv.append("-q" if args.quiet else "-" + "v" * min(args.verbose, 3))

    if args.target:
        argv += list(args.target)
    return argv


def main() -> int:
    args = build_parser().parse_args()
    argv = build_args(args)

    print(f"[PySentinel] pytest {' '.join(argv)}")
    started = time.perf_counter()

    import pytest

    exit_code = pytest.main(argv)

    elapsed = time.perf_counter() - started
    print(f"[PySentinel] 退出码={exit_code} 耗时={elapsed:.2f}s")

    if args.allure and (PROJECT_ROOT / "allure-results").exists():
        print("[PySentinel] 生成报告: allure generate allure-results -o allure-report --clean")

    return int(exit_code)


if __name__ == "__main__":
    sys.exit(main())
