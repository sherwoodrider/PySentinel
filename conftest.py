"""PySentinel 根 conftest —— 框架大脑。

在原版基础上补齐的工程化能力：

1. **统一资源生命周期**：HTTP 连接池 / embedding 模型 / LLM 缓存全部 session 级复用；
2. **失败自动留证**：UI 用例失败时截图 + 页面源码自动落盘；
3. **AI 根因分析**：失败用例自动把上下文投递给 LLM，结论写进日志与报告；
4. **结果闭环**：``TestResult`` 汇总 → JSON 持久化，并可选批量落 MySQL；
5. **性能可观测**：会话结束输出慢用例 TOP N 与外部请求指标；
6. **xdist 友好**：worker 自动区分产物文件名，并发安全。
"""
from __future__ import annotations

import datetime
import os
import time
from pathlib import Path
from typing import Generator, List, Optional, Tuple

import pytest

from src.common.artifacts import get_page
from src.common.cache import TTLCache
from src.config.settings import PROJECT_ROOT, get_settings
from src.test_log.logger import TestLog
from src.test_result.result import TestResult

# --------------------------------------------------------------------------- #
# 会话级全局状态（pytest-xdist 下每个 worker 是独立进程，无需加锁）
# --------------------------------------------------------------------------- #
_RESULT_COLLECTOR: Optional[TestResult] = None
_ARTIFACTS_DIR: str = ""
_SESSION_START = time.perf_counter()


def _maybe_import_mysql() -> None:
    """MySQL 依赖是可选的：缺失时提供会 skip 的占位 fixture，避免整个会话 ImportError。"""
    global db_connection, db_cursor  # noqa: PLW0603
    try:
        from src.mysql.conftest import db_connection as _conn, db_cursor as _cur  # type: ignore

        db_connection = _conn
        db_cursor = _cur
    except Exception:

        @pytest.fixture(scope="session")
        def db_connection():  # type: ignore[misc]
            pytest.skip("mysql-connector 依赖不可用")

        @pytest.fixture(scope="session")
        def db_cursor():  # type: ignore[misc]
            pytest.skip("mysql-connector 依赖不可用")


_maybe_import_mysql()


# --------------------------------------------------------------------------- #
# 命令行扩展
# --------------------------------------------------------------------------- #
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("pysentinel", "PySentinel 框架参数")
    group.addoption("--no-ai", action="store_true", default=False,
                    help="关闭全部 AI 增强能力（失败分析与判定均不再调用 LLM）")
    group.addoption("--slow-threshold", action="store", type=float, default=10.0,
                    help="慢用例阈值（秒），超时将在汇总中标出")
    group.addoption("--headed", action="store_true", default=False,
                    help="浏览器以有头模式运行（调试用）")
    group.addoption("--env-file", action="store", default=None,
                    help="指定配置文件路径（优先级最高）")


def pytest_configure(config: pytest.Config) -> None:
    config.pysentinel = {
        "no_ai": bool(config.getoption("--no-ai")),
        "slow_threshold": float(config.getoption("--slow-threshold")),
        "headed": bool(config.getoption("--headed")),
        "env_file": config.getoption("--env-file"),
    }
    if config.getoption("--no-ai"):
        os.environ["PYSENTINEL_DEEP_SEEK_AI_ANALYSIS"] = "0"
    env_file = config.getoption("--env-file")
    if env_file:
        os.environ["PYSENTINEL_CONFIG_FILE"] = str(Path(env_file).expanduser().resolve())

    config.addinivalue_line("markers", "ai: 依赖 LLM 判定的用例，可用 -m 'not ai' 快速跳过")
    config.addinivalue_line("markers", "flaky: 允许失败重试的不稳定用例")
    config.addinivalue_line("markers", "slow: 执行较慢的用例")


def _worker_suffix(config: pytest.Config) -> str:
    worker = getattr(config, "workerinput", None)
    return f"-{worker.get('workerid', 'worker')}" if worker else ""


# --------------------------------------------------------------------------- #
# Session 级资源
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def run_settings(pytestconfig: pytest.Config):
    """全局配置单例，整个会话只读一次盘。"""
    return get_settings(pytestconfig.getoption("--env-file"))


@pytest.fixture(scope="session")
def config_file(run_settings):
    """兼容旧代码的 ``config_file`` fixture。

    :class:`Settings` 已实现 ``get / getint / has_section / __contains__ / __getitem__``，
    旧的 ``config_file.get("deep_seek", "login_name")`` 写法无需任何改动。
    """
    return run_settings


@pytest.fixture(scope="session")
def log_folder(pytestconfig: pytest.Config) -> str:
    stamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    root = get_settings().raw_get("runtime", "log_root", str(PROJECT_ROOT / "logs"))
    folder = Path(root) / f"pysentinel_{stamp}{_worker_suffix(pytestconfig)}"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


@pytest.fixture(scope="session")
def artifacts_dir(log_folder: str) -> str:
    global _ARTIFACTS_DIR
    path = Path(log_folder) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    _ARTIFACTS_DIR = str(path)
    return _ARTIFACTS_DIR


@pytest.fixture(scope="session", autouse=True)
def test_log_handle(log_folder: str, pytestconfig: pytest.Config) -> TestLog:
    """会话级日志句柄。不再污染 root logger，多实例可安全共存。"""
    settings = get_settings()
    log = TestLog(
        log_file=os.path.join(log_folder, "pysentinel.log"),
        level=settings.raw_get("runtime", "log_level", "INFO"),
        console=settings.getbool("runtime", "log_console", False),
    )
    log.log_info("=" * 70)
    log.log_info(f"会话启动 | worker={_worker_suffix(pytestconfig) or 'master'}")
    log.log_info(f"配置摘要: {settings.as_dict(mask=True)}")
    yield log
    log.log_info(f"会话结束 | elapsed={time.perf_counter() - _SESSION_START:.2f}s")


@pytest.fixture(scope="session")
def llm_cache() -> TTLCache:
    """跨会话共享的 LLM 结果缓存 —— 重复提问零成本、零 token。"""
    ttl = float(get_settings().raw_get("judge", "cache_ttl", 86400.0))
    cache = TTLCache(
        maxsize=2048,
        ttl=ttl,
        persist_path=str(PROJECT_ROOT / ".cache" / "llm" / "shared_judge.json"),
    )
    yield cache
    cache.flush()


@pytest.fixture(scope="session")
def deep_seek_api(test_log_handle: TestLog, llm_cache: TTLCache):
    """整会话共享的 DeepSeek 客户端：复用连接池，配置只读一次。"""
    from src.deep_seek_api.api import DeepSeekApi

    enable_cache = get_settings().getbool("deep_seek", "enable_cache", True)
    api = DeepSeekApi(
        log_handle=test_log_handle,
        enable_cache=enable_cache,
        warm_cache=llm_cache if enable_cache else None,
    )
    yield api
    api.close()


@pytest.fixture(scope="session")
def response_judger_factory(llm_cache: TTLCache):
    """判定器工厂。

    使用方拿到工厂后按需实例化；底层 embedding 模型为**进程级单例**，
    会话内最多加载一次（旧实现每个用例都重载数百 MB 模型）。
    """
    default_strategy = str(get_settings().raw_get("judge", "strategy", "balanced"))

    def _factory(question: str, answer: str, strategy: Optional[str] = None):
        from src.model.check_relevance import ResponseJudger

        return ResponseJudger(
            question,
            answer,
            strategy=strategy or default_strategy,
            cache=llm_cache,
        )

    return _factory


@pytest.fixture(scope="session")
def data_base(test_log_handle: TestLog, db_cursor, db_connection):
    """持久化 DAO。数据库不可用时自动 skip，不拖垮整个会话。"""
    from src.mysql.sql_class import DatabaseManager

    return DatabaseManager(test_log_handle, db_cursor, db_connection)


@pytest.fixture(scope="session")
def test_result_handle(log_folder: str) -> TestResult:
    return TestResult(log_folder)


# --------------------------------------------------------------------------- #
# Function 级
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def log_test_case(request: pytest.FixtureRequest, test_log_handle: TestLog) -> Generator[None, None, None]:
    """记录用例进出，并把 AI 分析结果补写进日志。"""
    node = request.node
    started = time.perf_counter()
    test_log_handle.log_info(f"Enter {node.name} *****")

    yield

    elapsed = time.perf_counter() - started
    analysis = getattr(node, "_ai_analysis", None)
    if analysis:
        test_log_handle.log_info(f"[AI 分析] {node.name}")
        for line in str(analysis).splitlines():
            if line.strip():
                test_log_handle.log_info(f"    | {line}")
    test_log_handle.log_info(f"Quit {node.name} ***** elapsed={elapsed:.2f}s")


# --------------------------------------------------------------------------- #
# Hooks：结果收集 / 失败留证 / AI 分析
# --------------------------------------------------------------------------- #
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator[None, None, None]:
    outcome = yield
    report: pytest.TestReport = outcome.get_result()

    if report.failed:
        options = getattr(item.config, "pysentinel", {})
        # setup/teardown 阶段的报错通常是环境问题，AI 分析价值低且耗时 → 只在 call 阶段增强
        if report.when == "call":
            if not options.get("no_ai"):
                _attach_ai_analysis(item, call)
            _capture_screenshot(item)

    if report.when == "call" or (report.when != "call" and report.failed):
        _record_result(item, report)


def _record_result(item: pytest.Item, report: pytest.TestReport) -> None:
    if _RESULT_COLLECTOR is None:
        return
    # setup/teardown 失败归类为 error(call crash)，与业务断言失败区分
    outcome = report.outcome if report.when == "call" else "error"
    error_msg = ""
    if report.failed and report.longrepr is not None:
        lines = [ln for ln in report.longreprtext.splitlines() if ln.strip()]
        error_msg = lines[-1] if lines else ""

    _RESULT_COLLECTOR.record(
        case_name=item.name,
        outcome=outcome,
        duration=float(getattr(report, "duration", 0.0) or 0.0),
        error=error_msg,
        nodeid=item.nodeid,
        extra={"ai_analysis": getattr(item, "_ai_analysis", "")},
    )


def _attach_ai_analysis(item: pytest.Item, call: pytest.CallInfo) -> None:
    excinfo = getattr(call, "excinfo", None)
    if excinfo is None:
        return
    func = getattr(item, "function", None) or getattr(item, "obj", None)
    if func is None:
        return
    try:
        from src.deep_seek_api.check_error import _analyze

        analysis = _analyze(func, excinfo.value)
    except Exception as err:  # AI 永远不应改变测试结论
        analysis = f"[AI 分析不可用] {err}"
    item._ai_analysis = analysis  # type: ignore[attr-defined]


def _capture_screenshot(item: pytest.Item) -> None:
    """UI 用例失败留证：整页截图 + HTML 源码。"""
    if not _ARTIFACTS_DIR:
        return
    page = get_page(item.nodeid)
    if page is None:
        return
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in item.name)[:120]
    stamp = int(time.time())
    try:
        page.screenshot(path=os.path.join(_ARTIFACTS_DIR, f"{safe}_{stamp}.png"), full_page=True)
    except Exception:
        pass
    try:
        with open(os.path.join(_ARTIFACTS_DIR, f"{safe}_{stamp}.html"), "w", encoding="utf-8") as fp:
            fp.write(page.content())
    except Exception:
        pass


def pytest_sessionstart(session: pytest.Session) -> None:
    global _RESULT_COLLECTOR, _ARTIFACTS_DIR
    stamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    root = Path(get_settings().raw_get("runtime", "log_root", str(PROJECT_ROOT / "logs")))
    folder = root / f"pysentinel_{stamp}{_worker_suffix(session.config)}"
    folder.mkdir(parents=True, exist_ok=True)
    _ARTIFACTS_DIR = str(folder / "artifacts")
    Path(_ARTIFACTS_DIR).mkdir(parents=True, exist_ok=True)
    _RESULT_COLLECTOR = TestResult(str(folder), suite_name="PySentinel")


def pytest_collection_modifyitems(session: pytest.Session, config: pytest.Config, items: List[pytest.Item]) -> None:
    """按源码特征自动打标，便于 ``-m 'not ai'`` 一键跑快速冒烟。"""
    for item in items:
        nodeid = item.nodeid.lower()
        if "check_relevance" in nodeid or "judg" in nodeid or "deepseek" in nodeid:
            item.add_marker(pytest.mark.ai)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """会话收尾：汇总落盘 + 慢用例报告 + 外部请求指标 + 可选批量入库。"""
    collector = _RESULT_COLLECTOR
    if collector is None:
        return

    collector.get_common_dict()
    try:
        json_path = collector.result_to_json()
    except Exception as exc:  # pragma: no cover
        json_path = None
        print(f"[PySentinel] 结果落盘失败: {exc}")

    options = getattr(session.config, "pysentinel", {})
    threshold = float(options.get("slow_threshold", 10.0))

    print("\n" + "=" * 72)
    print(f"  {collector.summary_text()}")
    if json_path:
        print(f"  结果文件: {json_path}")

    _print_slow_cases(collector, threshold)
    _print_failures(collector)
    _print_http_metrics()
    print("=" * 72 + "\n")

    if get_settings().getbool("runtime", "persist_result", True):
        _persist_to_mysql(collector)


def _print_slow_cases(collector: TestResult, threshold: float) -> None:
    slow: List[Tuple[str, float]] = sorted(
        ((name, float(info.get("duration", 0.0))) for name, info in collector.result_dict.items()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    slow = [kv for kv in slow if kv[1] >= threshold][:10]
    if not slow:
        return
    print(f"  慢用例 TOP{len(slow)} (阈值 {threshold}s):")
    for name, sec in slow:
        print(f"    - {sec:>9.2f}s  {name}")


def _print_failures(collector: TestResult) -> None:
    failures = collector.failed_cases()
    if not failures:
        return
    print("  失败明细:")
    for case in failures[:20]:
        print(f"    x {case['name']} | {(case.get('error') or '')[:150]}")
        analysis = case.get("ai_analysis")
        if analysis:
            first = next((ln for ln in str(analysis).splitlines() if ln.strip()), "")
            print(f"      AI: {first[:150]}")


def _print_http_metrics() -> None:
    """输出外部 API 调用统计，定位"慢在网络还是慢在用例"。"""
    try:
        from src.deep_seek_api.api import DeepSeekApi

        metrics = DeepSeekApi._default_instance.metrics() if DeepSeekApi._default_instance else None
    except Exception:
        metrics = None
    if metrics and metrics.get("requests"):
        print(
            f"  LLM 请求: {metrics['requests']} 次, 失败 {metrics['failures']} 次, "
            f"平均 {metrics['avg_seconds']}s, 累计 {metrics['total_seconds']}s"
        )


def _persist_to_mysql(collector: TestResult) -> None:
    """一次性 executemany 落库，避免逐条网络往返。失败静默，不影响测试结论。"""
    settings = get_settings()
    if not settings.has_section("mysql") or settings.raw_get("mysql", "host") is None:
        return
    try:
        from src.mysql.conftest import get_pool
        from src.mysql.sql_class import DatabaseManager
        from src.test_log.logger import TestLog

        pool = get_pool()
        conn = pool.get_connection()
        cursor = conn.cursor()
        dao = DatabaseManager(TestLog(log_file="logs/db.log"), cursor, conn)
        rows = [
            {
                "test_case_name": name,
                "question": info.get("nodeid", name),
                "answer": info.get("ai_analysis", ""),
                "result": info.get("outcome", ""),
                "crash": info.get("crash", 0),
                "fail_info": info.get("error", ""),
                "duration": info.get("duration", 0.0),
            }
            for name, info in collector.result_dict.items()
        ]
        written = dao.insert_many(rows)
        conn.close()
        if written:
            print(f"  已写入 MySQL: {written} 条")
    except Exception as exc:
        print(f"  [PySentinel] 结果入库跳过（{type(exc).__name__}）: {str(exc)[:120]}")
