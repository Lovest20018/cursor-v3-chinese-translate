# -*- coding: utf-8 -*-
"""
Cursor V3 中文增强翻译工具

CLI 入口：负责参数解析、只读诊断、安装/恢复编排。
核心逻辑位于 cursor_translate/ 包中。
"""

from __future__ import annotations

import os
import sys

# 避免只读命令在仓库内生成 __pycache__
sys.dont_write_bytecode = True

import argparse
import datetime
import json
import platform
import re
import shutil
import tempfile
from typing import Dict, Optional, Tuple

from cursor_translate import TOOL_NAME, __version__
from cursor_translate.bundle import (
    build_paths,
    format_preflight_report,
    preflight,
    resolve_cursor_app_path,
    sha256_file,
)
from cursor_translate.constants import (
    APP_RELATIVE_DIR,
    BACKUP_SUFFIX,
    CHECKSUM_KEY,
    CURRENT_PLATFORM,
    DEFAULT_LINUX_INSTALL_PATHS,
    DEFAULT_MACOS_SYSTEM_INSTALL_PATH,
    DEFAULT_MACOS_USER_INSTALL_PATH,
    DEFAULT_WINDOWS_SYSTEM_INSTALL_PATH,
    DEFAULT_WINDOWS_USER_INSTALL_PATH,
    EXIT_CURSOR_RUNNING,
    EXIT_ERROR,
    EXIT_INCOMPATIBLE,
    EXIT_NEEDS_RECOVERY,
    EXIT_OK,
    INJECTION_MARKER,
    LEGACY_INJECTION_MARKER,
    MACOS_APP_RELATIVE_DIR,
    MACOS_CONTENTS_APP_RELATIVE_DIR,
    MAIN_PROCESS_RELATIVE_PATH,
    NATIVE_MENU_TRANSLATION_KEYS,
    NLS_MESSAGES_RELATIVE_PATH,
    RUNTIME_PROTECTED_EXACT_TEXTS,
    TOOL_MARKER,
    TOOL_VERSION,
    TRANSLATION_DICTIONARY_NAME,
    TRANSLATION_JS_NAME,
    WORKBENCH_HTML_NAME,
    WORKBENCH_RELATIVE_DIR,
    WORKBENCH_SOURCE_RELATIVE_PATH,
)
from cursor_translate.dictionary import (
    DictionaryError,
    load_dictionary_file,
    parse_translation_entry,
)
from cursor_translate.runtime import generate_js_code
from cursor_translate.transaction import (
    InstallTransaction,
    TransactionError,
    backup_root_dir,
    remove_tool_injection,
    restore_from_manifest,
    status_report,
    update_product_checksum_text,
    compute_workbench_checksum,
    atomic_write_text,
)

# ---------------------------------------------------------------------------
# 兼容旧测试与外部导入的全局状态
# ---------------------------------------------------------------------------

CURSOR_INSTALL_PATH = (
    DEFAULT_MACOS_SYSTEM_INSTALL_PATH
    if CURRENT_PLATFORM == "darwin"
    else (
        DEFAULT_WINDOWS_USER_INSTALL_PATH
        if CURRENT_PLATFORM == "windows"
        else DEFAULT_LINUX_INSTALL_PATHS[0]
    )
)
DEFAULT_CURSOR_INSTALL_PATH = CURSOR_INSTALL_PATH

# 兼容：旧 marker 名
# 新注入使用 INJECTION_MARKER；remove_injected_script 同时兼容旧标记
INJECTION_MARKER = INJECTION_MARKER  # noqa: F401 — re-export


def get_translation_dictionary_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        TRANSLATION_DICTIONARY_NAME,
    )


def read_translation_dictionary() -> Dict[str, str]:
    payload = load_dictionary_file(get_translation_dictionary_path())
    return dict(payload.entries)


def get_cursor_app_path() -> str:
    return resolve_cursor_app_path(CURSOR_INSTALL_PATH)


def get_workbench_dir() -> str:
    return os.path.join(get_cursor_app_path(), WORKBENCH_RELATIVE_DIR)


def get_workbench_html_path() -> str:
    return os.path.join(get_workbench_dir(), WORKBENCH_HTML_NAME)


def get_workbench_source_path() -> str:
    return os.path.join(get_cursor_app_path(), WORKBENCH_SOURCE_RELATIVE_PATH)


def get_main_process_path() -> str:
    return os.path.join(get_cursor_app_path(), MAIN_PROCESS_RELATIVE_PATH)


def get_nls_messages_path() -> str:
    return os.path.join(get_cursor_app_path(), NLS_MESSAGES_RELATIVE_PATH)


def get_main_process_backup_path() -> str:
    return get_main_process_path() + BACKUP_SUFFIX


def get_nls_messages_backup_path() -> str:
    return get_nls_messages_path() + BACKUP_SUFFIX


def get_native_resource_paths():
    return (
        ("main.js", get_main_process_path(), get_main_process_backup_path()),
        ("nls.messages.json", get_nls_messages_path(), get_nls_messages_backup_path()),
    )


def get_translation_js_path() -> str:
    return os.path.join(get_workbench_dir(), TRANSLATION_JS_NAME)


def get_workbench_backup_path() -> str:
    return get_workbench_html_path() + BACKUP_SUFFIX


def get_product_json_path() -> str:
    return os.path.join(get_cursor_app_path(), "product.json")


def get_product_backup_path() -> str:
    return get_product_json_path() + BACKUP_SUFFIX


def read_text_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as handle:
        return handle.read()


def write_text_file(file_path: str, content: str) -> None:
    atomic_write_text(file_path, content)


def write_translation_js(translation_dictionary_data=None) -> None:
    """兼容旧测试钩子：写入生成的翻译脚本。"""
    if translation_dictionary_data is None:
        translation_dictionary_data = read_translation_dictionary()
    js_content = generate_js_code(translation_dictionary_data, manifest_id="compat")
    write_text_file(get_translation_js_path(), js_content)
    print(f"[写入] 脚本已写入: {get_translation_js_path()}")


def inject_into_html() -> None:
    """兼容旧测试钩子；实际安装路径请使用事务式 apply。"""
    html_path = get_workbench_html_path()
    html = read_text_file(html_path)
    if INJECTION_MARKER in html or LEGACY_INJECTION_MARKER in html:
        html = remove_injected_script(html)
    from cursor_translate.runtime import build_injection_block

    injected = insert_injection_code(html, build_injection_block("compat"))
    write_text_file(html_path, injected)
    if not update_checksum(refresh_existing_backup=True):
        raise RuntimeError("checksum 更新失败")


def remove_injected_script(html_content: str) -> str:
    try:
        return remove_tool_injection(html_content)
    except TransactionError as error:
        raise ValueError(str(error)) from error


def insert_injection_code(html_content: str, injected_code: str) -> str:
    try:
        from cursor_translate.transaction import insert_injection_code as _insert

        return _insert(html_content, injected_code)
    except TransactionError as error:
        raise ValueError(str(error)) from error


def check_checksum_key_exists() -> bool:
    product_json_path = get_product_json_path()
    if not os.path.exists(product_json_path):
        print(f"[错误] 未找到 product.json: {product_json_path}")
        return False
    try:
        original_text = read_text_file(product_json_path)
        pattern = re.compile(
            r'("' + re.escape(CHECKSUM_KEY) + r'"\s*:\s*")([^"]*?)(")'
        )
        return bool(pattern.search(original_text))
    except Exception as error:
        print(f"[错误] 读取 product.json 失败: {error}")
        return False


def validate_cursor_installation() -> bool:
    report = preflight(CURSOR_INSTALL_PATH, for_apply=True)
    if report.exit_code != EXIT_OK and not report.checksum_present:
        for message in report.messages:
            print(f"[错误] {message}")
        return False
    if not os.path.isfile(report.paths.workbench_html):
        print(f"[错误] 未找到 workbench.html: {report.paths.workbench_html}")
        return False
    if not report.checksum_present:
        print(f"[错误] product.json 中未找到 workbench.html 的校验条目")
        return False
    return True


def get_rotated_backup_paths(backup_path: str):
    backup_dir = os.path.dirname(backup_path)
    backup_name = os.path.basename(backup_path)
    if not os.path.isdir(backup_dir):
        return []
    rotated_backup_pattern = re.compile(
        r"^" + re.escape(backup_name) + r"\.\d{14}(?:\.\d+)?$"
    )
    return [
        os.path.join(backup_dir, file_name)
        for file_name in os.listdir(backup_dir)
        if rotated_backup_pattern.match(file_name)
    ]


def cleanup_rotated_backups(backup_paths):
    for backup_path in backup_paths:
        for rotated_backup_path in get_rotated_backup_paths(backup_path):
            os.remove(rotated_backup_path)
            print(f"[清理] 已删除历史备份: {rotated_backup_path}")


def create_backup() -> None:
    """兼容旧测试：创建简单 .bak（新路径优先使用 versioned manifest）。"""
    for source, backup in (
        (get_workbench_html_path(), get_workbench_backup_path()),
        (get_product_json_path(), get_product_backup_path()),
    ):
        if os.path.isfile(source):
            prepare_backup_file(source, backup, os.path.basename(source), refresh_existing=True)


def prepare_backup_file(source_path, backup_path, label, refresh_existing=False):
    if os.path.exists(backup_path):
        if not refresh_existing:
            return
        if not are_files_identical(source_path, backup_path):
            rotate_existing_backup(backup_path)
    shutil.copy2(source_path, backup_path)
    print(f"[备份] 已备份 {label}: {backup_path}")


def are_files_identical(first_path, second_path) -> bool:
    if not (os.path.isfile(first_path) and os.path.isfile(second_path)):
        return False
    return sha256_file(first_path) == sha256_file(second_path)


def rotate_existing_backup(backup_path: str) -> None:
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    rotated = f"{backup_path}.{stamp}"
    index = 1
    while os.path.exists(rotated):
        rotated = f"{backup_path}.{stamp}.{index}"
        index += 1
    os.replace(backup_path, rotated)


def restore_original(keep_backups: bool = False) -> None:
    report = preflight(CURSOR_INSTALL_PATH, require_not_running=True, for_apply=False)
    try:
        result = restore_from_manifest(
            report, keep_backups=keep_backups or True
        )
        print(f"[完成] 已恢复 manifest={result.get('manifest_id')}")
        for path in result.get("restored", []):
            print(f"[恢复] {path}")
    except TransactionError as error:
        # 回退：尝试 legacy .bak
        print(f"[提示] 版本化恢复不可用: {error}")
        _legacy_restore(keep_backups=keep_backups)


def _legacy_restore(keep_backups: bool = False) -> None:
    workbench_html_path = get_workbench_html_path()
    backup_path = get_workbench_backup_path()
    js_path = get_translation_js_path()
    product_backup = get_product_backup_path()
    native_backups = [
        native_backup for _label, _resource_path, native_backup in get_native_resource_paths()
    ]

    if os.path.exists(backup_path):
        shutil.copy2(backup_path, workbench_html_path)
        if not keep_backups:
            os.remove(backup_path)
        print(f"[恢复] 已从 legacy 备份恢复: {workbench_html_path}")
    else:
        if os.path.isfile(workbench_html_path):
            html = read_text_file(workbench_html_path)
            write_text_file(workbench_html_path, remove_injected_script(html))
            print("[恢复] 已手动移除注入内容")

    if os.path.exists(product_backup):
        shutil.copy2(product_backup, get_product_json_path())
        if not keep_backups:
            os.remove(product_backup)

    for _label, resource_path, native_backup in get_native_resource_paths():
        if os.path.exists(native_backup):
            shutil.copy2(native_backup, resource_path)
            if not keep_backups:
                os.remove(native_backup)

    if os.path.exists(js_path):
        os.remove(js_path)
        print(f"[清理] 已删除脚本: {js_path}")

    if not keep_backups:
        cleanup_rotated_backups([backup_path, product_backup, *native_backups])

    print("[完成] legacy 恢复结束")


def update_checksum(refresh_existing_backup: bool = False) -> bool:
    product_json_path = get_product_json_path()
    workbench_html_path = get_workbench_html_path()
    if not os.path.exists(product_json_path):
        print(f"[错误] 未找到 product.json: {product_json_path}")
        return False
    with open(workbench_html_path, "rb") as handle:
        html_data = handle.read()
    checksum = compute_workbench_checksum(html_data)
    original_text = read_text_file(product_json_path)
    try:
        updated = update_product_checksum_text(original_text, checksum)
    except TransactionError as error:
        print(f"[错误] {error}")
        return False
    if refresh_existing_backup:
        prepare_backup_file(
            product_json_path, get_product_backup_path(), "product.json", refresh_existing=True
        )
    write_text_file(product_json_path, updated)
    print("[校验] 已更新 product.json 中的校验值")
    return True


def cleanup_legacy_language_pack() -> None:
    """清理早期版本可能写入的 languagepacks 残留（仅本工具标记）。"""
    print("[清理] 检查遗留语言包配置...")
    print("[清理] 完成（当前版本不再写入 languagepacks.json）")


def is_already_injected() -> bool:
    path = get_workbench_html_path()
    if not os.path.isfile(path):
        return False
    content = read_text_file(path)
    return INJECTION_MARKER in content or LEGACY_INJECTION_MARKER in content


# ---------------------------------------------------------------------------
# 源码候选提取（只读）
# ---------------------------------------------------------------------------

SOURCE_EXTRACTION_CONTEXT_KEYWORDS = (
    "label",
    "title",
    "tooltip",
    "placeholder",
    "aria-label",
    "description",
    "children",
)

SOURCE_EXTRACTION_PROTECTED_TEXTS = set(RUNTIME_PROTECTED_EXACT_TEXTS) | {
    "Enter",
    "Escape",
    "Backspace",
    "Tab",
    "HEAD",
}

SOURCE_EXTRACTION_QUOTED_STRING_PATTERN = re.compile(r'"((?:\\.|[^"\\])*)"')


def decode_js_string(raw_text: str) -> str:
    try:
        return json.loads(f'"{raw_text}"')
    except Exception:
        return raw_text.encode("utf-8").decode("unicode_escape")


def is_probable_ui_source_text(text: str) -> bool:
    if not text or len(text) < 2 or len(text) > 120:
        return False
    if text in SOURCE_EXTRACTION_PROTECTED_TEXTS:
        return False
    if re.fullmatch(r"[\W\d_]+", text):
        return False
    if re.search(r"https?://|\\|/Users/|[A-Za-z]:\\", text):
        return False
    if re.search(r"[{}<>;=]|function |const |var ", text):
        return False
    if not re.search(r"[A-Za-z]", text):
        return False
    return True


def extract_source_translation_candidates(limit: int = 200):
    source_path = get_workbench_source_path()
    if not os.path.isfile(source_path):
        print(f"[错误] 未找到 workbench 源码: {source_path}")
        return []
    dictionary = read_translation_dictionary()
    with open(source_path, "r", encoding="utf-8", errors="ignore") as handle:
        content = handle.read()
    candidates = []
    seen = set()
    for match in SOURCE_EXTRACTION_QUOTED_STRING_PATTERN.finditer(content):
        raw = match.group(1)
        try:
            text = decode_js_string(raw)
        except Exception:
            continue
        if not is_probable_ui_source_text(text):
            continue
        if text in dictionary or text in seen:
            continue
        # 简单上下文启发
        start = max(0, match.start() - 80)
        window = content[start : match.start()].lower()
        if not any(key in window for key in SOURCE_EXTRACTION_CONTEXT_KEYWORDS):
            # 仍接受标题样式短语
            if not re.match(r"^[A-Z][\w\s,&/'-]{1,80}$", text):
                continue
        seen.add(text)
        candidates.append(text)
        if len(candidates) >= limit:
            break
    return candidates


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_help() -> None:
    print("[用法] python CursorTranslate.py --apply [--cursorDir=路径]")
    print("[用法] python CursorTranslate.py --restore [--cursorDir=路径] [--keep-backups]")
    print("[用法] python CursorTranslate.py --check [--cursorDir=路径]")
    print("[用法] python CursorTranslate.py --status [--cursorDir=路径]")
    print("[用法] python CursorTranslate.py --dry-run [--cursorDir=路径]")
    print("[用法] python CursorTranslate.py --cleanup-legacy [--cursorDir=路径]")
    print("[用法] python CursorTranslate.py --extract-source-strings [--cursorDir=路径] [--limit=200]")
    print("[用法] python CursorTranslate.py --help")
    print(f"[工具] {TOOL_NAME} v{TOOL_VERSION}")
    print(f"[备份] {backup_root_dir()}")


def parse_arguments():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--extract-source-strings", action="store_true")
    parser.add_argument("--cleanup-legacy", action="store_true")
    parser.add_argument("--help", action="store_true")
    parser.add_argument("--keep-backups", action="store_true")
    parser.add_argument("--cursorDir", dest="cursor_dir")
    parser.add_argument("--limit", type=int, default=200)
    args, unknown_args = parser.parse_known_args()

    if unknown_args:
        print(f"\n[错误] 不支持的参数: {' '.join(unknown_args)}")
        print_help()
        sys.exit(EXIT_ERROR)

    selected_modes = [
        mode
        for mode, enabled in (
            ("--apply", args.apply),
            ("--restore", args.restore),
            ("--check", args.check),
            ("--status", args.status),
            ("--dry-run", args.dry_run),
            ("--extract-source-strings", args.extract_source_strings),
            ("--cleanup-legacy", args.cleanup_legacy),
        )
        if enabled
    ]
    if len(selected_modes) > 1:
        print("\n[错误] 不能同时使用多个互斥模式")
        print_help()
        sys.exit(EXIT_ERROR)

    if args.keep_backups and not args.restore:
        print("\n[错误] --keep-backups 只能与 --restore 一起使用")
        print_help()
        sys.exit(EXIT_ERROR)

    if args.help or not selected_modes:
        print_help()
        return None, args.cursor_dir, args.limit, args.keep_backups

    return selected_modes[0], args.cursor_dir, args.limit, args.keep_backups


def resolve_cursor_paths(custom_cursor_dir=None):
    global CURSOR_INSTALL_PATH
    if custom_cursor_dir:
        CURSOR_INSTALL_PATH = os.path.abspath(os.path.expanduser(custom_cursor_dir))


def run_check(cursor_dir: Optional[str]) -> int:
    report = preflight(cursor_dir, require_not_running=False, for_apply=False)
    print(format_preflight_report(report, include_plan=True))
    return report.exit_code if report.exit_code in {
        EXIT_OK, EXIT_INCOMPATIBLE, EXIT_CURSOR_RUNNING, EXIT_NEEDS_RECOVERY
    } else report.exit_code


def run_status(cursor_dir: Optional[str]) -> int:
    report = preflight(cursor_dir, require_not_running=False, for_apply=False)
    status = status_report(report)
    print(format_preflight_report(report, include_plan=False))
    print(f"Install state  : {status['state']}")
    print(f"Manifest id    : {status.get('manifest_id')}")
    return status["exit_code"]


def run_dry_run(cursor_dir: Optional[str]) -> int:
    report = preflight(cursor_dir, require_not_running=False, for_apply=True)
    print(format_preflight_report(report, include_plan=True))
    if report.exit_code not in {EXIT_OK, EXIT_CURSOR_RUNNING}:
        # dry-run 仍输出计划尝试
        if report.exit_code in {EXIT_INCOMPATIBLE, EXIT_NEEDS_RECOVERY}:
            print("[dry-run] 预检未通过，不生成写入计划")
            return report.exit_code
    try:
        dictionary = load_dictionary_file(get_translation_dictionary_path())
        plan = InstallTransaction(report, dictionary, dry_run=True).build_plan()
    except Exception as error:
        print(f"[dry-run] 构建计划失败: {error}")
        return EXIT_ERROR
    print("Patch plan:")
    for op in plan.operations:
        print(
            f"  - {op.action:6} {op.relative_path} "
            f"sha { (op.original_sha256 or '-')[:12] } -> { (op.result_sha256 or '-')[:12] }"
        )
    print(f"Manifest id (planned): {plan.manifest_id}")
    print(f"Backup root: {backup_root_dir()}")
    return EXIT_OK if not report.cursor_running else EXIT_CURSOR_RUNNING


def run_apply(cursor_dir: Optional[str]) -> int:
    report = preflight(cursor_dir, require_not_running=True, for_apply=True)
    print(format_preflight_report(report, include_plan=True))
    if report.cursor_running:
        print("[错误] Cursor 仍在运行，请完全退出后再执行 --apply")
        return EXIT_CURSOR_RUNNING
    if report.exit_code != EXIT_OK:
        print("[错误] 预检失败，零写入")
        for message in report.messages:
            print(f"  - {message}")
        return report.exit_code
    try:
        dictionary = load_dictionary_file(get_translation_dictionary_path())
    except DictionaryError as error:
        print(f"[错误] 词典无效: {error}")
        return EXIT_ERROR
    try:
        plan = InstallTransaction(report, dictionary, dry_run=False).apply()
    except TransactionError as error:
        print(f"[错误] 安装失败并已回滚: {error}")
        return error.exit_code
    print(f"[完成] 已应用汉化 manifest={plan.manifest_id}")
    print(f"[备份] {os.path.join(backup_root_dir(), InstallTransaction(report, dictionary).identity, plan.manifest_id)}")
    for op in plan.operations:
        print(f"[写入] {op.action} {op.absolute_path}")
    return EXIT_OK


def run_restore(cursor_dir: Optional[str], keep_backups: bool) -> int:
    report = preflight(cursor_dir, require_not_running=True, for_apply=False)
    if report.cursor_running:
        print("[错误] Cursor 仍在运行，请完全退出后再执行 --restore")
        return EXIT_CURSOR_RUNNING
    try:
        result = restore_from_manifest(report, keep_backups=True)
        print(f"[完成] 已恢复 manifest={result.get('manifest_id')}")
        for path in result.get("restored", []):
            print(f"[恢复] {path}")
        if keep_backups:
            print("[备份] 已保留版本化备份 manifest")
        return EXIT_OK
    except TransactionError as error:
        print(f"[错误] {error}")
        return error.exit_code


def main() -> None:
    print("=" * 60)
    print("  Cursor 汉化工具")
    print(f"  工具: {TOOL_NAME} v{TOOL_VERSION}")
    print(f"  平台: {CURRENT_PLATFORM}")
    print(f"  时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    mode, custom_cursor_dir, source_candidate_limit, keep_backups = parse_arguments()
    if mode is None:
        return

    resolve_cursor_paths(custom_cursor_dir)

    if mode == "--check":
        sys.exit(run_check(custom_cursor_dir or CURSOR_INSTALL_PATH))
    if mode == "--status":
        sys.exit(run_status(custom_cursor_dir or CURSOR_INSTALL_PATH))
    if mode == "--dry-run":
        sys.exit(run_dry_run(custom_cursor_dir or CURSOR_INSTALL_PATH))
    if mode == "--apply":
        sys.exit(run_apply(custom_cursor_dir or CURSOR_INSTALL_PATH))
    if mode == "--restore":
        sys.exit(run_restore(custom_cursor_dir or CURSOR_INSTALL_PATH, keep_backups))
    if mode == "--cleanup-legacy":
        cleanup_legacy_language_pack()
        return
    if mode == "--extract-source-strings":
        resolve_cursor_paths(custom_cursor_dir)
        candidates = extract_source_translation_candidates(source_candidate_limit)
        print(f"[提取] 候选 {len(candidates)} 条（未写入词典）")
        for item in candidates:
            print(f'"{item}" => ""')
        return


if __name__ == "__main__":
    main()
