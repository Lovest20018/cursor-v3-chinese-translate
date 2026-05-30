# -*- coding: utf-8 -*-
"""
Cursor 汉化工具
功能：
  1. 将翻译脚本注入 Cursor 的 workbench.html，实现界面中文化
  2. 从 cursor_translate_dic.txt 读取翻译词典并生成前端翻译脚本

用法：
  python CursorTranslate.py --apply     应用汉化
  python CursorTranslate.py --restore   恢复原始文件
  python CursorTranslate.py --extract-source-strings  从 Cursor 源码提取候选翻译词条
"""

import argparse
import base64
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import sys

CURRENT_PLATFORM = platform.system().lower()

DEFAULT_WINDOWS_USER_INSTALL_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Programs",
    "cursor",
)
DEFAULT_WINDOWS_SYSTEM_INSTALL_PATH = r"C:\Program Files\cursor"
DEFAULT_WINDOWS_USER_DATA_PATH = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "Cursor",
)
DEFAULT_MACOS_SYSTEM_INSTALL_PATH = "/Applications/Cursor.app"
DEFAULT_MACOS_USER_INSTALL_PATH = os.path.expanduser("~/Applications/Cursor.app")
DEFAULT_LINUX_INSTALL_PATHS = (
    "/usr/share/cursor",
    "/opt/Cursor",
    "/opt/cursor",
)

if CURRENT_PLATFORM == 'windows':
    # 优先检查用户级安装，如果不存在则检查系统级安装
    if os.path.exists(DEFAULT_WINDOWS_USER_INSTALL_PATH):
        CURSOR_INSTALL_PATH = DEFAULT_WINDOWS_USER_INSTALL_PATH
    elif os.path.exists(DEFAULT_WINDOWS_SYSTEM_INSTALL_PATH):
        CURSOR_INSTALL_PATH = DEFAULT_WINDOWS_SYSTEM_INSTALL_PATH
    else:
        CURSOR_INSTALL_PATH = DEFAULT_WINDOWS_USER_INSTALL_PATH  # 默认使用用户级路径
elif CURRENT_PLATFORM == 'linux':
    CURSOR_INSTALL_PATH = next(
        (path for path in DEFAULT_LINUX_INSTALL_PATHS if os.path.exists(path)),
        DEFAULT_LINUX_INSTALL_PATHS[0],
    )
elif CURRENT_PLATFORM == 'darwin':
    if os.path.exists(DEFAULT_MACOS_SYSTEM_INSTALL_PATH):
        CURSOR_INSTALL_PATH = DEFAULT_MACOS_SYSTEM_INSTALL_PATH
    elif os.path.exists(DEFAULT_MACOS_USER_INSTALL_PATH):
        CURSOR_INSTALL_PATH = DEFAULT_MACOS_USER_INSTALL_PATH
    else:
        CURSOR_INSTALL_PATH = DEFAULT_MACOS_SYSTEM_INSTALL_PATH
else:
    CURSOR_INSTALL_PATH = "/usr/share/cursor"

DEFAULT_CURSOR_INSTALL_PATH = CURSOR_INSTALL_PATH

if CURRENT_PLATFORM == 'windows':
    CURSOR_USER_DATA_PATH = DEFAULT_WINDOWS_USER_DATA_PATH
elif CURRENT_PLATFORM == 'linux':
    CURSOR_USER_DATA_PATH = os.path.expanduser("~/.cursor")
elif CURRENT_PLATFORM == 'darwin':
    CURSOR_USER_DATA_PATH = os.path.expanduser("~/Library/Application Support/Cursor")
else:
    CURSOR_USER_DATA_PATH = os.path.expanduser("~/.cursor")

APP_RELATIVE_DIR = os.path.join("resources", "app")
MACOS_APP_RELATIVE_DIR = os.path.join("Contents", "Resources", "app")
MACOS_CONTENTS_APP_RELATIVE_DIR = os.path.join("Resources", "app")
WORKBENCH_RELATIVE_DIR = os.path.join("out", "vs", "code", "electron-sandbox", "workbench")
WORKBENCH_SOURCE_RELATIVE_PATH = os.path.join("out", "vs", "workbench", "workbench.desktop.main.js")
WORKBENCH_HTML_NAME = "workbench.html"
TRANSLATION_JS_NAME = "cursor_hanhua.js"
TRANSLATION_DICTIONARY_NAME = "cursor_translate_dic.txt"
INJECTION_MARKER = "<!-- CURSOR_HANHUA_INJECTION -->"
BACKUP_SUFFIX = ".bak"
TOOL_VERSION = "1.0.0"
TOOL_MARKER = "CursorTranslate.py"

CHECKSUM_KEY = "vs/code/electron-sandbox/workbench/workbench.html"

SOURCE_EXTRACTION_CONTEXT_KEYWORDS = (
    "composer",
    "agent",
    "glass",
    "automation",
    "automations",
    "mcp",
    "skill",
    "skills",
    "subagent",
    "cursor",
    "plugin",
    "plugins",
)

SOURCE_EXTRACTION_PROTECTED_TEXTS = {
    "High",
    "Medium",
    "Low",
    "Extra High",
    "Max",
    "Canvas",
    "Memories",
    "GitHub",
    "Microsoft Teams",
    "Sentry",
    "Pager Duty",
    "Enter",
    "Escape",
    "Backspace",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "Tab",
    "HEAD",
    "UNSPECIFIED",
    "TIMEOUT",
    "ERROR",
    "AGENT",
    "PLAN",
}

SOURCE_EXTRACTION_FIELD_PATTERN = re.compile(
    r'(?:(?:label|title|tooltip|children|description|placeholder|aria-label|original)\s*:\s*|'
    r'"(?:aria-label|data-tooltip|title|placeholder)"\s*:\s*)'
    r'"((?:\\.|[^"\\])*)"',
)
SOURCE_EXTRACTION_QUOTED_STRING_PATTERN = re.compile(r'"((?:\\.|[^"\\])*)"')
SOURCE_EXTRACTION_CONTEXTUAL_QUOTED_FIELDS = (
    "children",
    "title",
    "label",
    "tooltip",
    "description",
    "placeholder",
    "aria-label",
)


def get_translation_dictionary_path():
    """获取翻译词典文本文件路径"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), TRANSLATION_DICTIONARY_NAME)


def parse_translation_entry(line, line_number):
    """解析单行翻译词条，支持引号内包含 => 的情况"""
    def find_separator_outside_quotes(text):
        """查找引号外的第一个 => 分隔符"""
        in_quotes = False
        escape_next = False
        i = 0
        while i < len(text) - 1:
            char = text[i]
            if escape_next:
                escape_next = False
                i += 1
                continue
            if char == '\\':
                escape_next = True
                i += 1
                continue
            if char == '"':
                in_quotes = not in_quotes
                i += 1
                continue
            if not in_quotes and text[i:i+2] == '=>':
                return i
            i += 1
        return -1

    separator_index = find_separator_outside_quotes(line)
    if separator_index == -1:
        raise ValueError(f"第 {line_number} 行缺少 => 分隔符")

    source_text = line[:separator_index].strip()
    translated_text = line[separator_index+2:].strip()

    def decode_dictionary_text(raw_text):
        if raw_text.startswith('"') and raw_text.endswith('"'):
            try:
                return json.loads(raw_text)
            except json.JSONDecodeError:
                return raw_text[1:-1]
        return raw_text

    source_text = decode_dictionary_text(source_text)
    translated_text = decode_dictionary_text(translated_text)

    if not source_text or not translated_text:
        raise ValueError(f"第 {line_number} 行键或值为空")

    return source_text, translated_text


def read_translation_dictionary():
    """从外部文本文件读取翻译词典"""
    dictionary_path = get_translation_dictionary_path()
    if not os.path.exists(dictionary_path):
        print(f"[错误] 未找到翻译词典文件: {dictionary_path}")
        sys.exit(1)

    dictionary_data = {}
    try:
        with open(dictionary_path, 'r', encoding='utf-8') as file:
            for line_number, line in enumerate(file, start=1):
                stripped_line = line.strip()
                if not stripped_line or stripped_line.startswith('#') or stripped_line.startswith('//'):
                    continue

                source_text, translated_text = parse_translation_entry(stripped_line, line_number)
                dictionary_data[source_text] = translated_text
    except Exception as error:
        print(f"[错误] 读取翻译词典失败: {error}")
        sys.exit(1)

    return dictionary_data


def generate_js_code(translation_dictionary_data):
    """生成包含翻译和实时刷新的 JavaScript 代码"""
    translation_dictionary_json = json.dumps(translation_dictionary_data, ensure_ascii=False)

    return '''\
/*
 * Cursor 汉化脚本
 * Auto-generated by ''' + TOOL_MARKER + ''' v''' + TOOL_VERSION + '''
 * Generated: ''' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '''
 * DO NOT EDIT THIS FILE MANUALLY
 */
(function () {
    'use strict';

    const translationDictionary = new Map(Object.entries(''' + translation_dictionary_json + '''));
    const normalizedTranslationDictionary = new Map();
    for (const [sourceText, translatedText] of translationDictionary.entries()) {
        const normalizedSourceText = normalizeTranslationWhitespace(sourceText);
        if (normalizedSourceText && !normalizedTranslationDictionary.has(normalizedSourceText)) {
            normalizedTranslationDictionary.set(normalizedSourceText, translatedText);
        }
    }
    const translationPatterns = [
        [/^(\\d+) requests? remaining$/i, "$1 次请求剩余"],
        [/^(\\d+) of (\\d+) requests?$/i, "$1 / $2 次请求"],
        [/^(\\d+) premium requests?$/i, "$1 次高级请求"],
        [/^(\\d+) files? indexed$/i, "$1 个文件已索引"],
        [/^Indexing (\\d+) files?$/i, "正在索引 $1 个文件"],
        [/^(\\d+) errors?$/i, "$1 个错误"],
        [/^(\\d+) warnings?$/i, "$1 个警告"],
        [/^Version (.+)$/i, "版本 $1"],
        [/^(\\d+) tools?$/i, "$1 个工具"],
        [/^(\\d+) resources?$/i, "$1 个资源"],
        [/^(\\d+) prompts?$/i, "$1 个提示词"],
        [/^Updated (.+) ago$/i, "$1前更新"],
        [/^(\\d+) seconds? ago$/i, "$1 秒前"],
        [/^(\\d+) minutes? ago$/i, "$1 分钟前"],
        [/^(\\d+) hours? ago$/i, "$1 小时前"],
        [/^(\\d+) days? ago$/i, "$1 天前"],
        [/^Auto-Run Mode Disabled by Team Admin$/i, "自动运行模式已被团队管理员禁用"],
        [/^Auto-Run Mode Controlled by Team Admin$/i, "自动运行模式由团队管理员控制"],
        [/^Auto-Run Mode Controlled by Team Admin \\(Sandbox Enabled\\)$/i, "自动运行模式由团队管理员控制（沙盒已启用）"],
        [/^Custom cron: (.+)$/i, "自定义 Cron：$1"],
        [/^Automatically index any new folders with fewer than ([\\d,]+) files\\.?$/i, "自动索引文件数少于 $1 的新文件夹。"],
        [/^MCP tools that can run automatically\\. Format: ['"]server:tool['"], ['"]server:\\*['"] for all tools from a server, ['"]\\*:tool['"] for a tool from any server, or ['"]\\*:\\*['"] for all tools from all servers\\.?$/i, "可自动运行的 MCP 工具。格式：'server:tool'；'server:*' 表示某个服务器的所有工具；'*:tool' 表示任意服务器中的某个工具；'*:*' 表示所有服务器的所有工具。"],
        [/^(\\d+) hooks?$/i, "$1 个钩子"],
        [/^(\\d+) automations?$/i, "$1 个自动化"],
        [/^(\\d+) rules?$/i, "$1 条规则"],
        [/^(\\d+) skills?$/i, "$1 个技能"],
        [/^(\\d+) commands?$/i, "$1 个命令"],
        [/^(\\d+) subagents?$/i, "$1 个子智能体"],
        [/^(\\d+) Queued$/i, "$1 条已排队"],
        [/^(.*?\\S)\\s+to Send$/i, "$1 发送"],
        [/^Thought briefly$/i, "短暂思考"],
        [/^Thought for ([\\d.]+)s$/i, "思考耗时 $1 秒"],
        [/^for ([\\d.]+)s$/i, "耗时 $1 秒"],
        [/^([\\d.]+)s$/i, "$1 秒"],
        [/^Completed (\\d+) of (\\d+)$/i, "已完成 $1 / $2"],
        [/^Completed (\\d+) of (\\d+) to-dos$/i, "已完成 $1 / $2 个待办"],
        [/^Started (\\d+) to-dos$/i, "已开始 $1 个待办"],
        [/^Added (\\d+) to-dos$/i, "已添加 $1 个待办"],
        [/^Cancelled (\\d+) to-dos$/i, "已取消 $1 个待办"],
        [/^Monitoring background (task|tasks)$/i, "正在监控后台任务"],
        [/^Monitored background (task|tasks)$/i, "已监控后台任务"]
    ];

    const editorAreaSelector = '.monaco-editor, .overflow-guard, .view-lines, .editor-scrollable, .inputarea, .rename-input';
    const skippedTags = new Set(['TEXTAREA', 'INPUT', 'SCRIPT', 'STYLE', 'CODE', 'PRE', 'NOSCRIPT']);
    const pendingNodes = [];
    let rescanCount = 0;
    let isTranslationScheduled = false;

    function normalizeTranslationWhitespace(text) {
        return text.replace(/\\s+/g, ' ').trim();
    }

    function lookupTranslation(text) {
        if (translationDictionary.has(text)) {
            return translationDictionary.get(text);
        }

        const normalizedText = normalizeTranslationWhitespace(text);
        if (normalizedText !== text && normalizedTranslationDictionary.has(normalizedText)) {
            return normalizedTranslationDictionary.get(normalizedText);
        }

        return null;
    }

    function translateAgentSummaryPart(part) {
        const trimmedPart = part.trim();
        const unitMatch = trimmedPart.match(/^(?:(explored|ran)\\s+)?(\\d+)\\s+(directory|directories|file|files|search|searches|fetch|fetches|command|commands|edit|edits|delete|deletes|agent|agents|browser action|browser actions)$/i);
        if (unitMatch) {
            const verb = (unitMatch[1] || '').toLowerCase();
            const count = unitMatch[2];
            const unit = unitMatch[3].toLowerCase();
            const unitTranslations = {
                directory: '个目录',
                directories: '个目录',
                file: '个文件',
                files: '个文件',
                search: '次搜索',
                searches: '次搜索',
                fetch: '次抓取',
                fetches: '次抓取',
                command: '条命令',
                commands: '条命令',
                edit: '处编辑',
                edits: '处编辑',
                delete: '处删除',
                deletes: '处删除',
                agent: '个 Agent',
                agents: '个 Agent',
                'browser action': '个浏览器操作',
                'browser actions': '个浏览器操作'
            };
            const translatedUnit = unitTranslations[unit];
            if (translatedUnit) {
                const translated = count + ' ' + translatedUnit;
                if (verb === 'explored') return '探索了 ' + translated;
                if (verb === 'ran') return '运行了 ' + translated;
                return translated;
            }
        }

        const statusMatch = trimmedPart.match(/^(\\d+)\\s+(complete|active)$/i);
        if (statusMatch) {
            return statusMatch[1] + (statusMatch[2].toLowerCase() === 'complete' ? ' 个已完成' : ' 个活动中');
        }

        if (/^lints$/i.test(trimmedPart)) return 'Lint 检查';
        return null;
    }

    function translateAgentSummaryDetails(text) {
        if (!text || /[\\u4e00-\\u9fff]/.test(text)) return null;
        const parts = text.split(/,\\s*/);
        if (parts.length === 0 || parts.length > 8) return null;

        const translatedParts = [];
        for (const part of parts) {
            const translatedPart = translateAgentSummaryPart(part);
            if (translatedPart === null) return null;
            translatedParts.push(translatedPart);
        }

        return translatedParts.join('、');
    }

    function translateSplitSettingDescription(element) {
        if (!element || !element.textContent || element.closest(editorAreaSelector)) return false;
        if (element.childNodes.length === 0 || element.childNodes.length > 12) return false;

        const normalizedText = normalizeTranslationWhitespace(element.textContent);
        const indexingMatch = normalizedText.match(/^Automatically index any new folders with fewer than ([\\d,]+) files\\.?$/i);
        if (indexingMatch) {
            element.textContent = '自动索引文件数少于 ' + indexingMatch[1] + ' 的新文件夹。';
            return true;
        }

        return false;
    }

    function translateTextNode(node) {
        const text = node.textContent;
        if (!text) return;

        const trimmedText = text.trim();
        if (!trimmedText || trimmedText.length > 2500) return;
        if (/^[\\d\\s.,;:!?@#$%^&*()\\-+=<>\\/\\\\|~`'"[\\]{}]+$/.test(trimmedText)) return;

        const translatedText = lookupTranslation(trimmedText);
        if (translatedText !== null) {
            const prefix = text.substring(0, text.indexOf(trimmedText));
            const suffix = text.substring(text.indexOf(trimmedText) + trimmedText.length);
            node.textContent = prefix + translatedText + suffix;
            return;
        }

        const translatedAgentSummary = translateAgentSummaryDetails(trimmedText);
        if (translatedAgentSummary !== null) {
            const prefix = text.substring(0, text.indexOf(trimmedText));
            const suffix = text.substring(text.indexOf(trimmedText) + trimmedText.length);
            node.textContent = prefix + translatedAgentSummary + suffix;
            return;
        }

        if (trimmedText.length > 500) return;

        if (/[\\u4e00-\\u9fff]/.test(trimmedText) && (trimmedText.match(/[\\u4e00-\\u9fff]/g) || []).length > trimmedText.length * 0.3) return;

        for (const [pattern, replacement] of translationPatterns) {
            if (pattern.test(trimmedText)) {
                node.textContent = text.replace(trimmedText, trimmedText.replace(pattern, replacement));
                return;
            }
        }

    }

    function translateAttributes(element) {
        for (const attributeName of ['title', 'aria-label', 'placeholder', 'aria-description', 'data-tooltip', 'data-title']) {
            const attributeValue = element.getAttribute(attributeName);
            if (!attributeValue) continue;

            const trimmedValue = attributeValue.trim();
            const translatedValue = lookupTranslation(trimmedValue);
            if (translatedValue !== null) {
                element.setAttribute(attributeName, translatedValue);
            }
        }
    }

    function getElementOwnText(element) {
        let ownText = '';
        for (const childNode of element.childNodes) {
            if (childNode.nodeType === Node.TEXT_NODE) {
                ownText += childNode.textContent;
            }
        }
        return ownText;
    }

    function translateElementOwnText(element) {
        if (!element || !element.childNodes || element.childNodes.length === 0) return;
        if (element.closest(editorAreaSelector)) return;

        const ownText = getElementOwnText(element);
        const trimmedText = ownText.trim();
        if (!trimmedText || trimmedText.length > 120) return;
        const translatedText = lookupTranslation(trimmedText);
        if (translatedText === null) return;

        for (const childNode of element.childNodes) {
            if (childNode.nodeType === Node.TEXT_NODE && childNode.textContent.includes(trimmedText)) {
                childNode.textContent = childNode.textContent.replace(trimmedText, translatedText);
                return;
            }
        }
    }

    function shouldSkipNode(node) {
        const element = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
        if (!element) return true;
        if (skippedTags.has(element.tagName)) return true;
        try {
            if (element.closest(editorAreaSelector)) return true;
        } catch (error) {}
        return false;
    }

    function translateTree(root) {
        const stack = [root];
        while (stack.length > 0) {
            const node = stack.pop();
            if (node.nodeType === Node.ELEMENT_NODE) {
                if (skippedTags.has(node.tagName)) {
                    translateAttributes(node);
                    continue;
                }
                if (node.classList && (node.classList.contains('monaco-editor') || node.classList.contains('overflow-guard') || node.classList.contains('view-lines') || node.classList.contains('editor-scrollable'))) continue;
                if (node.getAttribute('contenteditable') === 'true') continue;

                if (translateSplitSettingDescription(node)) continue;
                translateAttributes(node);
                translateElementOwnText(node);
                for (let index = node.childNodes.length - 1; index >= 0; index -= 1) {
                    stack.push(node.childNodes[index]);
                }
            } else if (node.nodeType === Node.TEXT_NODE && !shouldSkipNode(node)) {
                translateTextNode(node);
            }
        }
    }

    function enqueueNode(node) {
        pendingNodes.push(node);
        if (!isTranslationScheduled) {
            isTranslationScheduled = true;
            requestAnimationFrame(processPendingNodes);
        }
    }

    function processPendingNodes() {
        const nodesToProcess = pendingNodes.splice(0, pendingNodes.length);
        isTranslationScheduled = false;
        for (const node of nodesToProcess) {
            try {
                translateTree(node);
            } catch (error) {}
        }
    }

    function rescanDocument() {
        try {
            translateTree(document.body);
        } catch (error) {}
    }

    function scheduleStartupRescans() {
        const delays = [300, 800, 1500, 3000, 6000, 10000];
        for (const delay of delays) {
            setTimeout(rescanDocument, delay);
        }

        const intervalId = setInterval(function () {
            rescanCount += 1;
            rescanDocument();
            if (rescanCount >= 24) {
                clearInterval(intervalId);
            }
        }, 2500);
    }

    function handleMutations(mutations) {
        for (const mutation of mutations) {
            if (mutation.type === 'childList') {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.TEXT_NODE) {
                        enqueueNode(node);
                    }
                }
            } else if (mutation.type === 'characterData' && mutation.target.nodeType === Node.TEXT_NODE) {
                enqueueNode(mutation.target);
            }
        }
    }

    translateTree(document.body);
    scheduleStartupRescans();

    const observer = new MutationObserver(handleMutations);
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
    });
})();
'''


def resolve_cursor_app_path(cursor_path):
    """从安装入口路径解析到 Cursor 的 resources/app 目录。"""
    expanded_path = os.path.abspath(os.path.expanduser(cursor_path))
    base_name = os.path.basename(expanded_path)

    candidate_paths = [expanded_path]
    if expanded_path.lower().endswith(".app"):
        candidate_paths.append(os.path.join(expanded_path, MACOS_APP_RELATIVE_DIR))
    elif base_name == "Contents":
        candidate_paths.append(os.path.join(expanded_path, MACOS_CONTENTS_APP_RELATIVE_DIR))
    else:
        candidate_paths.append(os.path.join(expanded_path, APP_RELATIVE_DIR))

    for candidate_path in candidate_paths:
        if os.path.exists(os.path.join(candidate_path, "product.json")):
            return candidate_path

    if expanded_path.lower().endswith(".app"):
        return os.path.join(expanded_path, MACOS_APP_RELATIVE_DIR)
    if base_name == "Contents":
        return os.path.join(expanded_path, MACOS_CONTENTS_APP_RELATIVE_DIR)
    if base_name.lower() == "app":
        return expanded_path
    return os.path.join(expanded_path, APP_RELATIVE_DIR)


def get_cursor_app_path():
    """获取 Cursor resources/app 目录完整路径。"""
    return resolve_cursor_app_path(CURSOR_INSTALL_PATH)


def get_workbench_dir():
    """获取 workbench 目录完整路径"""
    return os.path.join(get_cursor_app_path(), WORKBENCH_RELATIVE_DIR)


def get_workbench_html_path():
    """获取 workbench.html 完整路径"""
    return os.path.join(get_workbench_dir(), WORKBENCH_HTML_NAME)


def get_workbench_source_path():
    """获取 Cursor 打包后的 workbench 主源码路径"""
    return os.path.join(get_cursor_app_path(), WORKBENCH_SOURCE_RELATIVE_PATH)


def get_cursor_skills_dirs():
    """获取可能存在的 Cursor 内置技能目录路径"""
    candidate_dirs = [
        os.path.join(CURSOR_USER_DATA_PATH, "skills-cursor"),
        os.path.join(os.path.expanduser("~"), ".cursor", "skills-cursor"),
    ]
    unique_dirs = []
    for candidate_dir in candidate_dirs:
        normalized_dir = os.path.abspath(os.path.expanduser(candidate_dir))
        if normalized_dir not in unique_dirs:
            unique_dirs.append(normalized_dir)
    return unique_dirs


def get_translation_js_path():
    """获取翻译 JS 文件完整路径"""
    return os.path.join(get_workbench_dir(), TRANSLATION_JS_NAME)


def get_workbench_backup_path():
    """获取 workbench.html 备份文件路径"""
    return get_workbench_html_path() + BACKUP_SUFFIX


def get_product_json_path():
    """获取 product.json 完整路径"""
    return os.path.join(get_cursor_app_path(), "product.json")


def get_product_backup_path():
    """获取 product.json 备份路径"""
    return get_product_json_path() + BACKUP_SUFFIX


def get_default_install_path_hint():
    if CURRENT_PLATFORM == 'windows':
        return r"%LocalAppData%\Programs\cursor (用户级) 或 C:\Program Files\cursor (系统级)"
    if CURRENT_PLATFORM == 'darwin':
        return "/Applications/Cursor.app 或 ~/Applications/Cursor.app"
    if CURRENT_PLATFORM == 'linux':
        return "、".join(DEFAULT_LINUX_INSTALL_PATHS)
    return DEFAULT_CURSOR_INSTALL_PATH


def print_help():
    print("[用法] python CursorTranslate.py --apply [--cursorDir=\"路径\"]")
    print("[用法] python CursorTranslate.py --restore [--cursorDir=\"路径\"]")
    print("[用法] python CursorTranslate.py --cleanup-legacy [--cursorDir=\"路径\"]")
    print("[用法] python CursorTranslate.py --extract-source-strings [--cursorDir=\"路径\"] [--limit=200]")
    print("[用法] python CursorTranslate.py --help")
    print(f"[默认] 当前平台默认安装目录: {get_default_install_path_hint()}")
    print("[说明] 不带任何参数时仅显示帮助信息，不执行任何操作")
    print("[说明] 如 Cursor 不在默认位置，可通过 --cursorDir 指定安装目录")
    print("[说明] --cleanup-legacy 清理早期版本遗留的语言包配置文件")
    print("[说明] --extract-source-strings 只读取源码并打印候选词条，不修改任何文件")


def parse_arguments():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--extract-source-strings', action='store_true')
    parser.add_argument('--cleanup-legacy', action='store_true')
    parser.add_argument('--help', action='store_true')
    parser.add_argument('--cursorDir', dest='cursor_dir')
    parser.add_argument('--limit', type=int, default=200)
    args, unknown_args = parser.parse_known_args()

    if unknown_args:
        print(f"\n[错误] 不支持的参数: {' '.join(unknown_args)}")
        print_help()
        sys.exit(1)

    selected_modes = [
        mode
        for mode, enabled in (
            ("--apply", args.apply),
            ("--restore", args.restore),
            ("--extract-source-strings", args.extract_source_strings),
            ("--cleanup-legacy", args.cleanup_legacy),
        )
        if enabled
    ]
    if len(selected_modes) > 1:
        print("\n[错误] --apply、--restore、--extract-source-strings 与 --cleanup-legacy 不能同时使用")
        print_help()
        sys.exit(1)

    if args.help or not selected_modes:
        print_help()
        return None, args.cursor_dir, args.limit

    return selected_modes[0], args.cursor_dir, args.limit


def resolve_cursor_paths(custom_cursor_dir=None):
    global CURSOR_INSTALL_PATH

    if custom_cursor_dir:
        CURSOR_INSTALL_PATH = os.path.abspath(os.path.expanduser(custom_cursor_dir))


def check_write_permission():
    """检查关键文件所在目录是否可写。"""
    paths_to_check = [
        ("workbench 目录", get_workbench_dir()),
        ("product.json 目录", os.path.dirname(get_product_json_path())),
    ]

    checked_dirs = set()
    for label, directory_path in paths_to_check:
        normalized_dir = os.path.abspath(directory_path)
        if normalized_dir in checked_dirs:
            continue
        checked_dirs.add(normalized_dir)

        test_file = os.path.join(normalized_dir, ".cursor_translate_write_test")
        try:
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except (PermissionError, OSError):
            print("\n[错误] 权限不足")
            print(f"[路径] {label}: {normalized_dir}")
            if CURRENT_PLATFORM == 'windows':
                print("[原因] 当前安装目录可能需要管理员权限才能修改文件")
                print("[解决] 请以管理员身份运行 PowerShell 或命令提示符后重试")
            else:
                print("[原因] 当前安装目录可能需要更高权限才能修改文件")
                print("[解决] 请使用 sudo 运行，或通过 --cursorDir 指定当前用户可写的 Cursor 安装目录")
            return False

    return True


def validate_cursor_installation():
    required_paths = [
        ("安装目录", CURSOR_INSTALL_PATH),
        ("product.json", get_product_json_path()),
        ("workbench.html", get_workbench_html_path()),
    ]

    missing_items = [label for label, path in required_paths if not os.path.exists(path)]
    if not missing_items:
        return

    print("\n[错误] Cursor 安装路径校验失败")
    print(f"[路径] 当前安装目录: {CURSOR_INSTALL_PATH}")
    for label, path in required_paths:
        if not os.path.exists(path):
            print(f"[缺失] {label}: {path}")

    print(f"[默认] 当前平台默认安装目录: {get_default_install_path_hint()}")
    print("[提示] 如果 Cursor 安装在其他位置，请使用 --cursorDir=\"实际路径\"")

    # Windows 系统级安装的额外提示
    if CURRENT_PLATFORM == 'windows' and CURSOR_INSTALL_PATH == DEFAULT_WINDOWS_SYSTEM_INSTALL_PATH:
        print("[注意] 检测到系统级安装路径，修改文件需要管理员权限")
        print("[建议] 请以管理员身份运行此脚本（右键 -> 以管理员身份运行）")

    sys.exit(1)


def validate_cursor_source_path():
    source_path = get_workbench_source_path()
    if os.path.exists(source_path):
        return source_path

    print("\n[错误] 未找到 Cursor 打包源码")
    print(f"[路径] 当前源码路径: {source_path}")
    print("[提示] 请确认 Cursor 安装目录是否正确，或使用 --cursorDir 指定")
    sys.exit(1)


def read_text_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()


def write_text_file(file_path, content):
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(content)


def read_json_file(file_path, default_value=None):
    if not os.path.exists(file_path):
        return default_value
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)


def write_json_file(file_path, data):
    parent_dir = os.path.dirname(file_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write('\n')


def decode_js_string(raw_text):
    try:
        return json.loads(f'"{raw_text}"')
    except json.JSONDecodeError:
        return raw_text


def is_cursor_source_context(source_text, start_index, end_index):
    context_start = max(0, start_index - 700)
    context_end = min(len(source_text), end_index + 700)
    context = source_text[context_start:context_end].lower()
    return any(keyword in context for keyword in SOURCE_EXTRACTION_CONTEXT_KEYWORDS)


def is_probable_ui_source_text(text):
    if not text or text in SOURCE_EXTRACTION_PROTECTED_TEXTS:
        return False
    if len(text) > 90:
        return False
    if any(control in text for control in ("\n", "\r", "\t")):
        return False
    if not re.search(r"[A-Za-z]", text):
        return False
    if re.search(r"^[a-z0-9_.:/\\-]+$", text):
        return False
    if re.search(r"^(?:cursor|workbench|editor|terminal|composer|agent|aiserver|vscode|github)\.", text, re.IGNORECASE):
        return False
    if re.search(r"^[a-z]+(?:_[a-z0-9]+)+$", text):
        return False
    if re.search(r"\.(?:js|ts|tsx|json|md|py|go|rs|java|cpp|html|css)$", text, re.IGNORECASE):
        return False
    if text.startswith(("/", "./", "../", "http://", "https://")):
        return False
    if "${" in text or "=>" in text:
        return False
    if text.isupper() and len(text.split()) <= 2:
        return False
    return True


def add_source_candidate(candidates, text, source_kind, offset):
    data = candidates.setdefault(text, {"count": 0, "sources": set(), "offset": offset})
    data["count"] += 1
    data["sources"].add(source_kind)


def extract_frontmatter_block(markdown_text):
    match = re.match(r'^---\s*\n(.*?)\n---', markdown_text, re.DOTALL)
    return match.group(1) if match else ""


def parse_frontmatter_description(frontmatter_text):
    lines = frontmatter_text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("description:"):
            continue

        value = line.split(":", 1)[1].strip()
        if value in (">-", ">", "|-", "|"):
            description_lines = []
            for next_line in lines[index + 1:]:
                if re.match(r'^\w[\w-]*:', next_line):
                    break
                stripped_line = next_line.strip()
                if stripped_line:
                    description_lines.append(stripped_line)
            return normalize_markdown_description(" ".join(description_lines))

        return normalize_markdown_description(value.strip().strip('"'))

    return ""


def normalize_markdown_description(text):
    return re.sub(r'\s+', ' ', text).strip()


def extract_skill_description_candidates(candidates, translation_dictionary_data):
    candidate_count = 0
    for skills_dir in get_cursor_skills_dirs():
        if not os.path.isdir(skills_dir):
            continue

        for dir_entry in sorted(os.listdir(skills_dir)):
            skill_path = os.path.join(skills_dir, dir_entry, "SKILL.md")
            if not os.path.exists(skill_path):
                continue
            try:
                skill_text = read_text_file(skill_path)
            except Exception:
                continue

            description = parse_frontmatter_description(extract_frontmatter_block(skill_text))
            if not description or description in translation_dictionary_data:
                continue

            add_source_candidate(candidates, description, "skill-description", skill_path)
            candidate_count += 1

    return candidate_count


def is_contextual_ui_string(source_text, start_index, end_index):
    prefix = source_text[max(0, start_index - 80):start_index]
    suffix = source_text[end_index:min(len(source_text), end_index + 80)]
    if any(re.search(rf'{field}\s*:\s*$', prefix) for field in SOURCE_EXTRACTION_CONTEXTUAL_QUOTED_FIELDS):
        return True
    if re.search(r'\?\s*$', prefix) and re.search(r'^\s*:', suffix):
        return True
    if re.search(r':\s*$', prefix) and re.search(r'^\s*[),}\]]', suffix):
        return True
    return False


def extract_source_translation_candidates(limit):
    source_path = validate_cursor_source_path()
    translation_dictionary_data = read_translation_dictionary()
    source_text = read_text_file(source_path)
    candidates = {}

    for match in SOURCE_EXTRACTION_FIELD_PATTERN.finditer(source_text):
        if not is_cursor_source_context(source_text, match.start(), match.end()):
            continue
        text = decode_js_string(match.group(1)).strip()
        if text in translation_dictionary_data or not is_probable_ui_source_text(text):
            continue
        add_source_candidate(candidates, text, "field", match.start())

    for match in SOURCE_EXTRACTION_QUOTED_STRING_PATTERN.finditer(source_text):
        if not is_cursor_source_context(source_text, match.start(), match.end()):
            continue
        if not is_contextual_ui_string(source_text, match.start(), match.end()):
            continue
        text = decode_js_string(match.group(1)).strip()
        if text in translation_dictionary_data or not is_probable_ui_source_text(text):
            continue
        if not re.search(r"^[A-Z][A-Za-z0-9 &'(),./:+-]*(?: [A-Z0-9][A-Za-z0-9 &'(),./:+-]*)*$", text):
            continue
        add_source_candidate(candidates, text, "quoted", match.start())

    extract_skill_description_candidates(candidates, translation_dictionary_data)

    ordered_candidates = sorted(
        candidates.items(),
        key=lambda item: (-item[1]["count"], item[0].lower()),
    )

    print(f"[源码] {source_path}")
    print(f"[词典] 已有 {len(translation_dictionary_data)} 条翻译")
    print(f"[候选] 发现 {len(ordered_candidates)} 条未翻译候选")
    print("[说明] 以下仅为候选，不会自动写入词典；请人工确认后补充。")

    for text, data in ordered_candidates[:max(0, limit)]:
        sources = ",".join(sorted(data["sources"]))
        print(f"{json.dumps(text, ensure_ascii=False)} => \"\"  // count={data['count']} source={sources} offset={data['offset']}")


def is_file_created_by_tool(file_path):
    """检查文件是否由本工具创建（通过检查工具标记）"""
    if not os.path.exists(file_path):
        return False
    try:
        content = read_text_file(file_path)
        return TOOL_MARKER in content
    except Exception:
        return False


def cleanup_legacy_language_pack():
    """清理早期版本写入的本地 VS Code 语言包配置，避免覆盖编辑器自带中文语言包

    只清理能明确确认由本工具创建的文件，无法确认来源的文件一律跳过。
    """
    languagepacks_path = os.path.join(CURSOR_USER_DATA_PATH, "languagepacks.json")
    languagepacks_backup_path = languagepacks_path + BACKUP_SUFFIX
    argv_path = os.path.join(CURSOR_USER_DATA_PATH, "argv.json")
    argv_backup_path = argv_path + BACKUP_SUFFIX
    legacy_pack_dir = os.path.join(CURSOR_USER_DATA_PATH, "cursor-local-zh-cn")
    clp_cache_dir = os.path.join(CURSOR_USER_DATA_PATH, "clp")
    cleaned_legacy_pack = False

    # 恢复 languagepacks.json 备份（只恢复确认由本工具修改的）
    if os.path.exists(languagepacks_backup_path):
        should_restore = False
        if os.path.exists(languagepacks_path):
            try:
                languagepacks_data = read_json_file(languagepacks_path, {})
                if isinstance(languagepacks_data, dict) and "zh-cn" in languagepacks_data:
                    translations = languagepacks_data.get("zh-cn", {}).get("translations", {})
                    # 如果当前文件包含 cursor-local-zh-cn 引用，说明是旧版本修改的
                    if any(isinstance(path, str) and "cursor-local-zh-cn" in path for path in translations.values()):
                        should_restore = True
            except Exception:
                pass

        if should_restore:
            shutil.copy2(languagepacks_backup_path, languagepacks_path)
            os.remove(languagepacks_backup_path)
            print(f"[清理] 已恢复语言包配置: {languagepacks_path}")
            cleaned_legacy_pack = True
        else:
            print(f"[跳过] 备份文件存在但未检测到本工具的修改标记，跳过恢复: {languagepacks_backup_path}")

    elif os.path.exists(languagepacks_path):
        try:
            languagepacks_data = read_json_file(languagepacks_path, {})
            if isinstance(languagepacks_data, dict) and "zh-cn" in languagepacks_data:
                translations = languagepacks_data.get("zh-cn", {}).get("translations", {})
                if any(isinstance(path, str) and "cursor-local-zh-cn" in path for path in translations.values()):
                    languagepacks_data.pop("zh-cn", None)
                    write_json_file(languagepacks_path, languagepacks_data)
                    print(f"[清理] 已移除旧本地语言包入口: {languagepacks_path}")
                    cleaned_legacy_pack = True
        except Exception as error:
            print(f"[警告] 清理语言包配置失败: {error}")

    # 跳过 argv.json.bak - 无法确认来源
    if os.path.exists(argv_backup_path):
        print(f"[跳过] argv.json.bak 存在但无法确认是否由本工具创建，跳过恢复: {argv_backup_path}")
        print(f"[提示] 如需手动恢复，请检查该文件内容后自行决定")

    # 删除旧的语言包目录（只删除明确由本工具创建的目录）
    if os.path.exists(legacy_pack_dir):
        marker_file = os.path.join(legacy_pack_dir, "package.json")
        should_delete = False

        if os.path.exists(marker_file):
            try:
                package_data = read_json_file(marker_file, {})
                # 检查是否包含本工具的标识
                if isinstance(package_data, dict):
                    # 旧版本的 package.json 包含特定的 localizedLanguageName
                    if package_data.get("localizedLanguageName") == "简体中文 (Cursor 汉化)":
                        should_delete = True
            except Exception:
                pass

        if should_delete:
            shutil.rmtree(legacy_pack_dir)
            print(f"[清理] 已删除旧本地语言包目录: {legacy_pack_dir}")
            cleaned_legacy_pack = True
        else:
            print(f"[跳过] 目录存在但无法确认是否由本工具创建，跳过删除: {legacy_pack_dir}")
            print(f"[提示] 如需手动删除，请检查目录内容后自行决定")

    # 删除语言包缓存（只在确认清理了语言包后才删除）
    if cleaned_legacy_pack and os.path.exists(clp_cache_dir):
        shutil.rmtree(clp_cache_dir)
        print(f"[清理] 已删除语言包缓存: {clp_cache_dir}")


def is_already_injected():
    """检查是否已经注入过翻译脚本"""
    workbench_html_path = get_workbench_html_path()
    if not os.path.exists(workbench_html_path):
        return False
    return INJECTION_MARKER in read_text_file(workbench_html_path)


def create_backup():
    """创建 workbench.html 的备份"""
    workbench_html_path = get_workbench_html_path()
    backup_path = get_workbench_backup_path()
    if not os.path.exists(backup_path):
        shutil.copy2(workbench_html_path, backup_path)
        print(f"[备份] 已创建备份: {backup_path}")
    else:
        print(f"[备份] 备份已存在: {backup_path}")


def write_translation_js(translation_dictionary_data):
    """将翻译 JavaScript 文件写入 Cursor 目录"""
    js_path = get_translation_js_path()
    js_content = generate_js_code(translation_dictionary_data)
    write_text_file(js_path, js_content)
    print(f"[写入] 脚本已写入: {js_path}")


def inject_into_html():
    """在 workbench.html 中注入脚本引用，失败时自动回滚"""
    workbench_html_path = get_workbench_html_path()
    backup_path = get_workbench_backup_path()
    js_path = get_translation_js_path()

    # 读取原始内容（用于可能的回滚）
    html_content = read_text_file(workbench_html_path)
    injected_code = f'\n\t{INJECTION_MARKER}\n\t<!-- Generated by {TOOL_MARKER} v{TOOL_VERSION} -->\n\t<script src="./{TRANSLATION_JS_NAME}"></script>\n'

    if '</body>' in html_content:
        html_content = html_content.replace('</body>', f'</body>\n{injected_code}')
    else:
        html_content = html_content.replace('</html>', f'{injected_code}\n</html>')

    # 写入注入后的内容
    write_text_file(workbench_html_path, html_content)
    print(f"[注入] 已在 workbench.html 中注入脚本引用")

    # 尝试更新 checksum
    if not update_checksum():
        print("[错误] 校验和更新失败，正在回滚...")
        # 回滚：从备份恢复 HTML
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, workbench_html_path)
            print(f"[回滚] 已从备份恢复 workbench.html")
        else:
            print("[警告] 备份文件不存在，无法自动回滚 HTML")

        # 删除已生成的 JS 文件
        if os.path.exists(js_path):
            os.remove(js_path)
            print(f"[回滚] 已删除 JS 文件")

        print("[错误] 注入失败，已回滚到原始状态")
        sys.exit(1)


def check_checksum_key_exists():
    """检查 product.json 中是否存在 checksum key，返回是否存在"""
    product_json_path = get_product_json_path()

    if not os.path.exists(product_json_path):
        print(f"[错误] 未找到 product.json: {product_json_path}")
        return False

    try:
        original_text = read_text_file(product_json_path)
        pattern = re.compile(r'("' + re.escape(CHECKSUM_KEY) + r'"\s*:\s*")([^"]*?)(")')
        match = pattern.search(original_text)
        if match:
            return True
        else:
            print(f"[错误] product.json 中未找到 workbench.html 的校验条目")
            return False
    except Exception as error:
        print(f"[错误] 读取 product.json 失败: {error}")
        return False


def update_checksum():
    """更新 product.json 中 workbench.html 的校验哈希值，返回是否成功"""
    product_json_path = get_product_json_path()
    workbench_html_path = get_workbench_html_path()

    if not os.path.exists(product_json_path):
        print(f"[错误] 未找到 product.json: {product_json_path}")
        return False

    with open(workbench_html_path, 'rb') as file:
        html_data = file.read()
    checksum = base64.b64encode(hashlib.sha256(html_data).digest()).decode('utf-8').rstrip('=')

    product_backup_path = get_product_backup_path()
    if not os.path.exists(product_backup_path):
        shutil.copy2(product_json_path, product_backup_path)

    original_text = read_text_file(product_json_path)
    pattern = re.compile(r'("' + re.escape(CHECKSUM_KEY) + r'"\s*:\s*")([^"]*?)(")')
    match = pattern.search(original_text)
    if match:
        updated_text = original_text[:match.start(2)] + checksum + original_text[match.end(2):]
        write_text_file(product_json_path, updated_text)
        print(f"[校验] 已更新 product.json 中的校验值")
        return True
    else:
        print(f"[错误] product.json 中未找到 workbench.html 的校验条目")
        return False


def restore_checksum():
    """恢复 product.json 的原始校验值"""
    product_json_path = get_product_json_path()
    product_backup_path = get_product_backup_path()
    if os.path.exists(product_backup_path):
        shutil.copy2(product_backup_path, product_json_path)
        os.remove(product_backup_path)
        print(f"[校验] 已恢复 product.json 原始校验值")


def remove_injected_script(html_content):
    """移除注入的脚本块，如果注入不完整则抛出错误"""
    lines = html_content.splitlines(keepends=True)
    updated_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if INJECTION_MARKER in line:
            # 找到 marker，查找接下来的两行是否是完整的注入块
            # 期望格式：
            # <!-- CURSOR_HANHUA_INJECTION -->
            # <!-- Generated by CursorTranslate.py vX.X.X -->
            # <script src="./cursor_hanhua.js"></script>

            lines_to_check = 2  # 需要检查后续两行
            if i + lines_to_check < len(lines):
                next_line_1 = lines[i + 1]
                next_line_2 = lines[i + 2]

                # 检查是否是完整的注入块（兼容旧版本没有 Generated by 注释的情况）
                has_tool_marker = f'Generated by {TOOL_MARKER}' in next_line_1
                script_line_index = i + 2 if has_tool_marker else i + 1

                if script_line_index < len(lines):
                    script_line = lines[script_line_index]
                    if f'<script src="./{TRANSLATION_JS_NAME}"></script>' in script_line:
                        # 完整注入块，跳过所有相关行
                        i = script_line_index + 1
                        continue

            # marker 存在但没有完整的 script 标签
            raise ValueError(
                f"检测到不完整的注入标记。找到 {INJECTION_MARKER} "
                f"但未找到对应的 <script src=\"./{TRANSLATION_JS_NAME}\"></script> 标签。"
                "HTML 可能已被手动修改，请检查 workbench.html 文件。"
            )

        updated_lines.append(line)
        i += 1

    return ''.join(updated_lines)


def restore_original():
    """恢复原始的 workbench.html"""
    workbench_html_path = get_workbench_html_path()
    backup_path = get_workbench_backup_path()
    js_path = get_translation_js_path()

    if os.path.exists(backup_path):
        shutil.copy2(backup_path, workbench_html_path)
        os.remove(backup_path)
        print(f"[恢复] 已从备份恢复: {workbench_html_path}")
    else:
        print("[恢复] 未找到备份文件，尝试手动移除注入...")
        html_content = read_text_file(workbench_html_path)
        write_text_file(workbench_html_path, remove_injected_script(html_content))
        print(f"[恢复] 已手动移除注入内容")

    restore_checksum()

    if os.path.exists(js_path):
        os.remove(js_path)
        print(f"[清理] 已删除脚本: {js_path}")

    print("[完成] 已恢复原始状态")


def main():
    """主程序入口"""
    print("=" * 60)
    print("  Cursor 汉化工具")
    print(f"  平台: {CURRENT_PLATFORM}")
    print(f"  时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    mode, custom_cursor_dir, source_candidate_limit = parse_arguments()
    resolve_cursor_paths(custom_cursor_dir)

    if mode is None:
        return

    if mode == '--extract-source-strings':
        extract_source_translation_candidates(source_candidate_limit)
        return

    if mode == '--cleanup-legacy':
        print("\n[模式] 清理早期版本遗留配置...")
        cleanup_legacy_language_pack()
        print("[完成] 清理完成")
        return

    validate_cursor_installation()

    if mode == '--restore':
        print("\n[模式] 恢复原始文件...")
        if not check_write_permission():
            sys.exit(1)
        restore_original()
        return

    print("\n[步骤 1/3] 读取翻译词典...")
    translation_dictionary_data = read_translation_dictionary()
    print(f"[词典] 已加载 {len(translation_dictionary_data)} 条翻译")

    if is_already_injected():
        print("\n[检测] 脚本已注入，正在更新...")

        # 预检：确保有写入权限
        if not check_write_permission():
            sys.exit(1)

        # 预检：确保 product.json 中存在 checksum key
        if not check_checksum_key_exists():
            print("[错误] 无法继续更新：product.json 校验条目缺失")
            sys.exit(1)

        write_translation_js(translation_dictionary_data)
        if not update_checksum():
            print("[错误] 脚本更新成功但校验和更新失败")
            sys.exit(1)
        print("\n[完成] 脚本已更新！重启 Cursor 生效。")
        return

    # 预检：确保有写入权限（在写入任何文件前）
    if not check_write_permission():
        sys.exit(1)

    # 预检：确保 product.json 中存在 checksum key（在写入任何文件前）
    if not check_checksum_key_exists():
        print("[错误] 无法继续注入：product.json 校验条目缺失")
        print("[建议] 请检查 Cursor 安装是否完整")
        sys.exit(1)

    print(f"\n[步骤 2/3] 创建备份并写入脚本...")
    create_backup()
    write_translation_js(translation_dictionary_data)

    print("[步骤 3/3] 注入 HTML 引用...")
    inject_into_html()

    print("\n" + "=" * 60)
    print("  [完成] Cursor 汉化注入成功！")
    print("  请重启 Cursor 以查看效果。")
    print("  如需恢复: python CursorTranslate.py --restore")
    print("  如需重新应用: python CursorTranslate.py --apply")
    print("=" * 60)


if __name__ == '__main__':
    main()
