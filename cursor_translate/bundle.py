# -*- coding: utf-8 -*-
"""Cursor 安装包路径解析、预检与只读诊断。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .constants import (
    APP_RELATIVE_DIR,
    CHECKSUM_KEY,
    CURRENT_PLATFORM,
    DEFAULT_LINUX_INSTALL_PATHS,
    DEFAULT_MACOS_SYSTEM_INSTALL_PATH,
    DEFAULT_MACOS_USER_INSTALL_PATH,
    DEFAULT_WINDOWS_SYSTEM_INSTALL_PATH,
    DEFAULT_WINDOWS_USER_INSTALL_PATH,
    EXIT_CURSOR_RUNNING,
    EXIT_INCOMPATIBLE,
    EXIT_NEEDS_RECOVERY,
    EXIT_OK,
    FOREIGN_BACKUP_HINTS,
    FOREIGN_MARKER_PATTERNS,
    INJECTION_BEGIN,
    INJECTION_MARKER,
    LEGACY_INJECTION_MARKER,
    MACOS_APP_RELATIVE_DIR,
    MACOS_CONTENTS_APP_RELATIVE_DIR,
    MAIN_PROCESS_RELATIVE_PATH,
    NLS_MESSAGES_RELATIVE_PATH,
    PRODUCT_JSON_NAME,
    TOOL_MARKER,
    TOOL_NAME,
    TOOL_VERSION,
    TRANSLATION_JS_NAME,
    WORKBENCH_HTML_NAME,
    WORKBENCH_RELATIVE_DIR,
    WORKBENCH_SOURCE_RELATIVE_PATH,
)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_cursor_app_path(cursor_path: str) -> str:
    """从多种入口解析到 resources/app。"""
    expanded_path = os.path.abspath(os.path.expanduser(cursor_path))
    base_name = os.path.basename(expanded_path)

    candidate_paths = [expanded_path]
    if expanded_path.lower().endswith(".app"):
        candidate_paths.append(os.path.join(expanded_path, MACOS_APP_RELATIVE_DIR))
    elif base_name == "Contents":
        candidate_paths.append(
            os.path.join(expanded_path, MACOS_CONTENTS_APP_RELATIVE_DIR)
        )
    else:
        candidate_paths.append(os.path.join(expanded_path, APP_RELATIVE_DIR))

    for candidate_path in candidate_paths:
        product_path = os.path.join(candidate_path, PRODUCT_JSON_NAME)
        if os.path.isfile(product_path):
            # 确认是 Cursor 包
            try:
                with open(product_path, "r", encoding="utf-8") as handle:
                    product = json.load(handle)
                name = str(product.get("nameShort") or product.get("name") or "").lower()
                app_name = str(product.get("applicationName") or "").lower()
                if "cursor" in name or "cursor" in app_name or product.get("version"):
                    return os.path.abspath(candidate_path)
            except Exception:
                # product.json 存在即作为候选
                return os.path.abspath(candidate_path)

    if expanded_path.lower().endswith(".app"):
        return os.path.abspath(os.path.join(expanded_path, MACOS_APP_RELATIVE_DIR))
    if base_name == "Contents":
        return os.path.abspath(
            os.path.join(expanded_path, MACOS_CONTENTS_APP_RELATIVE_DIR)
        )
    if base_name.lower() == "app":
        return expanded_path
    return os.path.abspath(os.path.join(expanded_path, APP_RELATIVE_DIR))


def default_install_candidates() -> List[str]:
    if CURRENT_PLATFORM == "windows":
        return [DEFAULT_WINDOWS_USER_INSTALL_PATH, DEFAULT_WINDOWS_SYSTEM_INSTALL_PATH]
    if CURRENT_PLATFORM == "darwin":
        return [DEFAULT_MACOS_SYSTEM_INSTALL_PATH, DEFAULT_MACOS_USER_INSTALL_PATH]
    if CURRENT_PLATFORM == "linux":
        return list(DEFAULT_LINUX_INSTALL_PATHS)
    return []


def discover_default_cursor_path() -> Optional[str]:
    for candidate in default_install_candidates():
        try:
            app_path = resolve_cursor_app_path(candidate)
            if os.path.isfile(os.path.join(app_path, PRODUCT_JSON_NAME)):
                return app_path
        except Exception:
            continue
    return None


@dataclass
class BundlePaths:
    resources_app: str
    workbench_html: str
    product_json: str
    translation_js: str
    workbench_desktop_main: str
    main_js: str
    nls_messages: str

    def required_for_apply(self) -> Dict[str, str]:
        return {
            "workbench.html": self.workbench_html,
            "product.json": self.product_json,
        }

    def optional_native(self) -> Dict[str, str]:
        return {
            "main.js": self.main_js,
            "nls.messages.json": self.nls_messages,
        }

    def all_known(self) -> Dict[str, str]:
        result = self.required_for_apply()
        result["cursor_hanhua.js"] = self.translation_js
        result["workbench.desktop.main.js"] = self.workbench_desktop_main
        result.update(self.optional_native())
        return result


@dataclass
class ConflictEvidence:
    kind: str
    path: str
    detail: str


@dataclass
class PreflightReport:
    resources_app: str
    version: Optional[str]
    commit: Optional[str]
    paths: BundlePaths
    checksum_key: str
    checksum_present: bool
    checksum_value: Optional[str]
    injection_anchor_count: int
    injection_anchor_valid: bool
    existing_tool_marker: bool
    legacy_marker: bool
    foreign_conflicts: List[ConflictEvidence] = field(default_factory=list)
    cursor_running: bool = False
    cursor_running_details: Tuple[str, ...] = ()
    writable: bool = False
    write_notes: Tuple[str, ...] = ()
    planned_writes: Tuple[str, ...] = ()
    status: str = "unknown"
    exit_code: int = EXIT_OK
    messages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "resources_app": self.resources_app,
            "version": self.version,
            "commit": self.commit,
            "checksum_key": self.checksum_key,
            "checksum_present": self.checksum_present,
            "checksum_value": self.checksum_value,
            "injection_anchor_count": self.injection_anchor_count,
            "injection_anchor_valid": self.injection_anchor_valid,
            "existing_tool_marker": self.existing_tool_marker,
            "legacy_marker": self.legacy_marker,
            "foreign_conflicts": [
                {"kind": c.kind, "path": c.path, "detail": c.detail}
                for c in self.foreign_conflicts
            ],
            "cursor_running": self.cursor_running,
            "writable": self.writable,
            "planned_writes": list(self.planned_writes),
            "status": self.status,
            "exit_code": self.exit_code,
            "messages": list(self.messages),
            "paths": {k: v for k, v in self.paths.all_known().items()},
        }


def build_paths(resources_app: str) -> BundlePaths:
    workbench_dir = os.path.join(resources_app, WORKBENCH_RELATIVE_DIR)
    return BundlePaths(
        resources_app=resources_app,
        workbench_html=os.path.join(workbench_dir, WORKBENCH_HTML_NAME),
        product_json=os.path.join(resources_app, PRODUCT_JSON_NAME),
        translation_js=os.path.join(workbench_dir, TRANSLATION_JS_NAME),
        workbench_desktop_main=os.path.join(
            resources_app, WORKBENCH_SOURCE_RELATIVE_PATH
        ),
        main_js=os.path.join(resources_app, MAIN_PROCESS_RELATIVE_PATH),
        nls_messages=os.path.join(resources_app, NLS_MESSAGES_RELATIVE_PATH),
    )


def read_product_metadata(product_json_path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    with open(product_json_path, "r", encoding="utf-8") as handle:
        product = json.load(handle)
    checksums = product.get("checksums") or {}
    checksum_value = None
    if isinstance(checksums, dict):
        checksum_value = checksums.get(CHECKSUM_KEY)
    return product.get("version"), product.get("commit"), checksum_value


def count_body_close_tags(html: str) -> int:
    return len(re.findall(r"</body\s*>", html, flags=re.IGNORECASE))


def detect_foreign_artifacts(paths: BundlePaths) -> List[ConflictEvidence]:
    evidence: List[ConflictEvidence] = []
    scan_files = [
        paths.workbench_html,
        paths.product_json,
        paths.main_js,
        paths.nls_messages,
        paths.translation_js,
    ]
    for file_path in scan_files:
        if not os.path.isfile(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read(512 * 1024)
        except Exception as error:
            evidence.append(
                ConflictEvidence("read-error", file_path, str(error))
            )
            continue

        lower = content.lower()
        for pattern in FOREIGN_MARKER_PATTERNS:
            if pattern.lower() in lower:
                # 忽略本工具自身标记
                if pattern.upper() in {
                    "CURSOR_HANHUA_INJECTION",
                } and (
                    INJECTION_MARKER in content
                    or TOOL_MARKER in content
                    or TOOL_NAME in content
                ):
                    # legacy 由单独字段处理
                    if LEGACY_INJECTION_MARKER in content and INJECTION_MARKER not in content:
                        continue
                if TOOL_NAME in content and pattern.lower() in {
                    "cursor_hanhua_injection",
                }:
                    continue
                if pattern.lower() in {"cursor_hanhua_injection"} and INJECTION_MARKER in content:
                    continue
                evidence.append(
                    ConflictEvidence(
                        "marker",
                        file_path,
                        f"检测到外部标记模式: {pattern}",
                    )
                )

    # 扫描旁路备份文件
    roots = {
        os.path.dirname(paths.workbench_html),
        os.path.dirname(paths.product_json),
        os.path.dirname(paths.main_js),
        paths.resources_app,
    }
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            names = os.listdir(root)
        except Exception:
            continue
        for name in names:
            lower_name = name.lower()
            if any(hint in lower_name for hint in FOREIGN_BACKUP_HINTS):
                evidence.append(
                    ConflictEvidence(
                        "foreign-backup",
                        os.path.join(root, name),
                        "检测到外部工具备份文件（将保留，不删除）",
                    )
                )
            elif lower_name.endswith(".bak") and TOOL_NAME not in lower_name:
                # 旁路 .bak 可能属于旧工具或其他补丁
                evidence.append(
                    ConflictEvidence(
                        "sidecar-bak",
                        os.path.join(root, name),
                        "检测到旁路 .bak 文件",
                    )
                )
    return evidence


def is_cursor_process_running(resources_app: Optional[str] = None) -> Tuple[bool, Tuple[str, ...]]:
    """检测 Cursor 主进程是否仍在运行。"""
    # 测试夹具可通过环境变量跳过（不用于生产安装路径）
    if os.environ.get("CURSOR_V3_TRANSLATE_SKIP_PROCESS_CHECK") == "1":
        return False, ()
    details: List[str] = []
    try:
        if CURRENT_PLATFORM == "windows":
            completed = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Cursor.exe"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            output = completed.stdout or ""
            if "Cursor.exe" in output:
                details.append("Cursor.exe")
                return True, tuple(details)
            return False, ()

        completed = subprocess.run(
            ["ps", "-ax", "-o", "pid=,comm="],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        output = completed.stdout or ""
        for line in output.splitlines():
            lower = line.lower()
            if "cursor" not in lower:
                continue
            # 忽略 helper / GPU / 本检测自身
            if any(
                noise in lower
                for noise in (
                    "cursoruiviewservice",
                    "crashpad",
                    "helper",
                    "gpu",
                    "plugin",
                    "renderer",
                    "pty",
                    "language_server",
                )
            ):
                continue
            # macOS 主程序通常是 .../Cursor.app/Contents/MacOS/Cursor
            if (
                "/contents/macos/cursor" in lower
                or lower.strip().endswith(" cursor")
                or re.search(r"\bcursor\b", lower)
            ):
                # 再过滤明显不是 GUI 主程序的
                if "cursortranslate" in lower or "python" in lower:
                    continue
                if "cursor helper" in lower:
                    continue
                details.append(line.strip())
        # 更精确：pgrep
        pgrep = subprocess.run(
            ["pgrep", "-lf", "Cursor"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        for line in (pgrep.stdout or "").splitlines():
            lower = line.lower()
            if "contents/macos/cursor" in lower and "helper" not in lower:
                if line.strip() not in details:
                    details.append(line.strip())
        return (len(details) > 0), tuple(details[:10])
    except Exception as error:
        details.append(f"process-check-error: {error}")
        return False, tuple(details)


def check_writable(paths: BundlePaths) -> Tuple[bool, Tuple[str, ...]]:
    notes: List[str] = []
    ok = True
    for label, path in {
        "workbench.html": paths.workbench_html,
        "product.json": paths.product_json,
    }.items():
        directory = os.path.dirname(path)
        if not os.path.isdir(directory):
            ok = False
            notes.append(f"{label} 目录不存在: {directory}")
            continue
        if not os.access(directory, os.W_OK):
            ok = False
            notes.append(f"{label} 目录不可写: {directory}")
        if os.path.exists(path) and not os.access(path, os.W_OK):
            ok = False
            notes.append(f"{label} 文件不可写: {path}")
    return ok, tuple(notes)


def preflight(
    cursor_dir: Optional[str] = None,
    *,
    require_not_running: bool = False,
    for_apply: bool = False,
) -> PreflightReport:
    if cursor_dir:
        resources_app = resolve_cursor_app_path(cursor_dir)
    else:
        discovered = discover_default_cursor_path()
        if not discovered:
            resources_app = resolve_cursor_app_path(
                default_install_candidates()[0]
                if default_install_candidates()
                else "."
            )
        else:
            resources_app = discovered

    paths = build_paths(resources_app)
    messages: List[str] = []
    exit_code = EXIT_OK
    status = "ok"

    version = commit = checksum_value = None
    checksum_present = False
    if os.path.isfile(paths.product_json):
        try:
            version, commit, checksum_value = read_product_metadata(paths.product_json)
            checksum_present = checksum_value is not None
        except Exception as error:
            messages.append(f"读取 product.json 失败: {error}")
            exit_code = EXIT_INCOMPATIBLE
            status = "incompatible"
    else:
        messages.append(f"未找到 product.json: {paths.product_json}")
        exit_code = EXIT_INCOMPATIBLE
        status = "incompatible"

    injection_anchor_count = 0
    injection_anchor_valid = False
    existing_tool_marker = False
    legacy_marker = False

    if os.path.isfile(paths.workbench_html):
        with open(paths.workbench_html, "r", encoding="utf-8") as handle:
            html = handle.read()
        injection_anchor_count = count_body_close_tags(html)
        injection_anchor_valid = injection_anchor_count >= 1
        existing_tool_marker = (
            INJECTION_MARKER in html
            or INJECTION_BEGIN in html
            or TOOL_NAME in html
            or (TOOL_MARKER in html and TRANSLATION_JS_NAME in html)
        )
        legacy_marker = (
            LEGACY_INJECTION_MARKER in html and INJECTION_MARKER not in html
        )
        if not injection_anchor_valid:
            messages.append("workbench.html 缺少 </body> 注入锚点")
            exit_code = EXIT_INCOMPATIBLE
            status = "incompatible"
    else:
        messages.append(f"未找到 workbench.html: {paths.workbench_html}")
        exit_code = EXIT_INCOMPATIBLE
        status = "incompatible"

    if for_apply and not checksum_present:
        messages.append(f"product.json 缺少 checksum key: {CHECKSUM_KEY}")
        exit_code = EXIT_INCOMPATIBLE
        status = "incompatible"

    foreign = detect_foreign_artifacts(paths)
    # 外部备份本身不是硬冲突，仅 marker 重叠时可能升级
    hard_conflicts = [
        item
        for item in foreign
        if item.kind == "marker"
        and os.path.basename(item.path) == WORKBENCH_HTML_NAME
        and LEGACY_INJECTION_MARKER not in item.detail
    ]
    # 若本工具 marker 与外部 HTML 注入共享同一锚点且为 legacy，则标记 needs-recovery 风格
    if legacy_marker and for_apply:
        messages.append(
            "检测到旧版 CURSOR_HANHUA_INJECTION（无 v2 manifest）。"
            "请先用旧工具恢复，或从官方 DMG 重装后再应用。"
        )
        exit_code = EXIT_NEEDS_RECOVERY
        status = "legacy-installation"

    running, running_details = is_cursor_process_running(resources_app)
    if running and require_not_running:
        messages.append("Cursor 仍在运行，拒绝写入")
        exit_code = EXIT_CURSOR_RUNNING
        status = "cursor-running"

    writable, write_notes = check_writable(paths)
    if for_apply and not writable:
        messages.append("目标目录不可写")
        exit_code = EXIT_INCOMPATIBLE if exit_code == EXIT_OK else exit_code
        status = "not-writable"

    planned = []
    if os.path.isfile(paths.workbench_html):
        planned.append(paths.workbench_html)
    planned.append(paths.translation_js)
    if os.path.isfile(paths.product_json):
        planned.append(paths.product_json)
    for optional_path in (paths.main_js, paths.nls_messages):
        if os.path.isfile(optional_path):
            planned.append(optional_path)

    return PreflightReport(
        resources_app=resources_app,
        version=version,
        commit=commit,
        paths=paths,
        checksum_key=CHECKSUM_KEY,
        checksum_present=checksum_present,
        checksum_value=checksum_value,
        injection_anchor_count=injection_anchor_count,
        injection_anchor_valid=injection_anchor_valid,
        existing_tool_marker=existing_tool_marker,
        legacy_marker=legacy_marker,
        foreign_conflicts=foreign,
        cursor_running=running,
        cursor_running_details=running_details,
        writable=writable,
        write_notes=write_notes,
        planned_writes=tuple(planned),
        status=status,
        exit_code=exit_code,
        messages=messages,
    )


def format_preflight_report(report: PreflightReport, *, include_plan: bool = False) -> str:
    lines = [
        f"Cursor path     : {report.resources_app}",
        f"Cursor version  : {report.version or 'unknown'}",
        f"Cursor commit   : {report.commit or 'unknown'}",
        f"Checksum key    : {report.checksum_key}",
        f"Checksum present: {report.checksum_present}",
        f"Injection anchor: count={report.injection_anchor_count} valid={report.injection_anchor_valid}",
        f"Tool marker     : {report.existing_tool_marker}",
        f"Legacy marker   : {report.legacy_marker}",
        f"Cursor running  : {report.cursor_running}",
        f"Writable        : {report.writable}",
        f"Status          : {report.status}",
        f"Exit code       : {report.exit_code}",
    ]
    lines.append("Resolved paths:")
    for label, path in report.paths.all_known().items():
        exists = "yes" if os.path.exists(path) else "no"
        lines.append(f"  - {label}: {path} [{exists}]")
    if report.foreign_conflicts:
        lines.append("Conflicts / foreign artifacts:")
        for item in report.foreign_conflicts:
            lines.append(f"  - [{item.kind}] {item.path}: {item.detail}")
    if report.messages:
        lines.append("Messages:")
        for message in report.messages:
            lines.append(f"  - {message}")
    if include_plan:
        lines.append("Planned writes:")
        for path in report.planned_writes:
            lines.append(f"  - {path}")
    return "\n".join(lines)
