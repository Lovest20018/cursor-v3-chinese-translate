# -*- coding: utf-8 -*-
"""共享常量。"""

import os
import platform

CURRENT_PLATFORM = platform.system().lower()

TOOL_NAME = "cursor-v3-chinese-translate"
TOOL_VERSION = "2.0.0"
TOOL_MARKER = "CursorTranslate.py"
LEGACY_INJECTION_MARKER = "<!-- CURSOR_HANHUA_INJECTION -->"
INJECTION_MARKER = "<!-- CURSOR_V3_CHINESE_TRANSLATE_INJECTION -->"
INJECTION_BEGIN = "<!-- CURSOR_V3_CHINESE_TRANSLATE:BEGIN"
INJECTION_END = "<!-- CURSOR_V3_CHINESE_TRANSLATE:END -->"
TRANSLATION_JS_NAME = "cursor_hanhua.js"
TRANSLATION_DICTIONARY_NAME = "cursor_translate_dic.txt"
BACKUP_SUFFIX = ".bak"
MANIFEST_SCHEMA_VERSION = 2
RUNTIME_SYMBOL = "cursor-v3-chinese-translate.runtime"

APP_RELATIVE_DIR = os.path.join("resources", "app")
MACOS_APP_RELATIVE_DIR = os.path.join("Contents", "Resources", "app")
MACOS_CONTENTS_APP_RELATIVE_DIR = os.path.join("Resources", "app")
WORKBENCH_RELATIVE_DIR = os.path.join(
    "out", "vs", "code", "electron-sandbox", "workbench"
)
WORKBENCH_SOURCE_RELATIVE_PATH = os.path.join(
    "out", "vs", "workbench", "workbench.desktop.main.js"
)
MAIN_PROCESS_RELATIVE_PATH = os.path.join("out", "main.js")
NLS_MESSAGES_RELATIVE_PATH = os.path.join("out", "nls.messages.json")
WORKBENCH_HTML_NAME = "workbench.html"
PRODUCT_JSON_NAME = "product.json"
CHECKSUM_KEY = "vs/code/electron-sandbox/workbench/workbench.html"

DEFAULT_WINDOWS_USER_INSTALL_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local"),
    "Programs",
    "cursor",
)
DEFAULT_WINDOWS_SYSTEM_INSTALL_PATH = r"C:\Program Files\cursor"
DEFAULT_MACOS_SYSTEM_INSTALL_PATH = "/Applications/Cursor.app"
DEFAULT_MACOS_USER_INSTALL_PATH = os.path.expanduser("~/Applications/Cursor.app")
DEFAULT_LINUX_INSTALL_PATHS = (
    "/usr/share/cursor",
    "/opt/Cursor",
    "/opt/cursor",
    os.path.expanduser("~/.local/share/cursor"),
)

# 仅匹配明确的工具注入/补丁标记，避免命中业务文案中的普通单词
FOREIGN_MARKER_PATTERNS = (
    "COMETIX_CCURSOR_INJECTION",
    "ccursor-injection",
    "@cometix/ccursor",
    "cursor++",
    "cursorpp-byok",
    "CURSORPP_BYOK",
    "backup-byok",
    "cursor-always-local",
    "CURSOR_ALWAYS_LOCAL",
    "renderer-hook-injection",
    "CURSOR_HANHUA_INJECTION",
)

FOREIGN_BACKUP_HINTS = (
    "backup-byok",
    "backup-ccursor",
    "backup-cometix",
    "backup-always-local",
    ".ccursor",
    ".cometix",
)

NATIVE_MENU_TRANSLATION_KEYS = (
    "Undo",
    "Redo",
    "Cut",
    "Copy",
    "Paste",
    "Paste and Match Style",
    "Select All",
    "Delete",
    "Share",
    "Speech",
    "Start Speaking",
    "Stop Speaking",
    "AutoFill",
    "Emoji & Symbols",
)

# 模型强度 / 套餐 / 技术缩写：仅在模型选择器或技术上下文中保护
RUNTIME_PROTECTED_EXACT_TEXTS = (
    "Auto",
    "None",
    "Minimal",
    "High",
    "Medium",
    "Low",
    "Extra High",
    "Max",
    "Free",
    "Pro",
    "Business",
    "CLI",
    "SCM",
    "SDK",
    "API",
    "Slack",
    "Linear",
    "GitHub",
    "Microsoft Teams",
    "Sentry",
    "Pager Duty",
    "Canvas",
    "Memories",
)

# 退出码
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INCOMPATIBLE = 2
EXIT_CURSOR_RUNNING = 3
EXIT_NEEDS_RECOVERY = 4
