# -*- coding: utf-8 -*-
"""
Cursor 汉化 + 用量监控工具
功能：
  1. 将翻译脚本注入 Cursor 的 workbench.html，实现设置页面中文化
  2. 自动从本地数据库读取认证令牌，调用 API 获取用量数据
  3. 在 Cursor 设置页面用户信息区域下方显示实时用量情况

用法：
  python CursorTranslate.py --apply     汉化 + 用量显示
  python CursorTranslate.py --restore   恢复原始文件
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
import sqlite3
import sys
import urllib.request

CURRENT_PLATFORM = platform.system().lower()

DEFAULT_WINDOWS_INSTALL_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Programs",
    "cursor",
)
DEFAULT_WINDOWS_USER_DATA_PATH = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "Cursor",
)

if CURRENT_PLATFORM == 'windows':
    CURSOR_INSTALL_PATH = DEFAULT_WINDOWS_INSTALL_PATH
elif CURRENT_PLATFORM == 'linux':
    CURSOR_INSTALL_PATH = "/usr/share/cursor"
else:
    CURSOR_INSTALL_PATH = "/usr/share/cursor"

DEFAULT_CURSOR_INSTALL_PATH = CURSOR_INSTALL_PATH

if CURRENT_PLATFORM == 'windows':
    CURSOR_USER_DATA_PATH = DEFAULT_WINDOWS_USER_DATA_PATH
elif CURRENT_PLATFORM == 'linux':
    CURSOR_USER_DATA_PATH = os.path.expanduser("~/.cursor")
else:
    CURSOR_USER_DATA_PATH = os.path.expanduser("~/.cursor")

WORKBENCH_RELATIVE_DIR = os.path.join("resources", "app", "out", "vs", "code", "electron-sandbox", "workbench")
WORKBENCH_HTML_NAME = "workbench.html"
TRANSLATION_JS_NAME = "cursor_hanhua.js"
TRANSLATION_DICTIONARY_NAME = "cursor_translate_dic.txt"
INJECTION_MARKER = "<!-- CURSOR_HANHUA_INJECTION -->"
BACKUP_SUFFIX = ".bak"

API_USAGE = "https://api2.cursor.sh/auth/usage"
API_USAGE_SUMMARY = "https://www.cursor.com/api/usage-summary"

STATE_DB_RELATIVE_PATH = os.path.join("User", "globalStorage", "state.vscdb")
ACCESS_TOKEN_KEY = "cursorAuth/accessToken"
EMAIL_KEY = "cursorAuth/cachedEmail"
CHECKSUM_KEY = "vs/code/electron-sandbox/workbench/workbench.html"
USAGE_CARD_ID = "cursor-usage-card"


def create_empty_usage_data():
    return {
        "total_used": 0,
        "total_limit": 2000,
        "remaining": 2000,
        "premium_used": 0,
        "premium_limit": 500,
        "total_percent_used": 0,
        "api_percent_used": 0,
        "billing_cycle_start": "",
        "billing_cycle_end": "",
        "updated_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "plan_type": "pro",
        "is_valid": False,
        "model_details": {}
    }


def read_access_token():
    """从 Cursor 本地 state.vscdb 数据库读取访问令牌和用户邮箱"""
    database_path = os.path.join(CURSOR_USER_DATA_PATH, STATE_DB_RELATIVE_PATH)
    if not os.path.exists(database_path):
        print(f"[警告] 未找到 Cursor 数据库: {database_path}")
        return None, None

    try:
        connection = sqlite3.connect(database_path)
        cursor = connection.cursor()

        cursor.execute("SELECT value FROM ItemTable WHERE key=?", (ACCESS_TOKEN_KEY,))
        result = cursor.fetchone()
        access_token = result[0] if result else None

        cursor.execute("SELECT value FROM ItemTable WHERE key=?", (EMAIL_KEY,))
        result = cursor.fetchone()
        email = result[0] if result else None

        connection.close()
        return access_token, email
    except Exception as error:
        print(f"[警告] 读取数据库失败: {error}")
        return None, None


def build_session_cookie(access_token):
    """从访问令牌构造 WorkosCursorSessionToken Cookie"""
    try:
        token_parts = access_token.split('.')
        if len(token_parts) < 2:
            return None

        payload_segment = token_parts[1]
        payload_segment += '=' * (-len(payload_segment) % 4)
        payload = json.loads(base64.b64decode(payload_segment).decode('utf-8'))
        user_id = payload.get('sub', '').replace('auth0|', '')
        return f"{user_id}::{access_token}"
    except Exception:
        return None


def fetch_json(url, headers):
    try:
        request = urllib.request.Request(url)
        for header_name, header_value in headers.items():
            request.add_header(header_name, header_value)
        response = urllib.request.urlopen(request, timeout=10)
        return json.loads(response.read().decode('utf-8'))
    except Exception as error:
        print(f"[警告] 请求失败 {url}: {error}")
        return None


def fetch_usage_summary(access_token):
    """调用 cursor.com/api/usage-summary 获取总用量摘要"""
    cookie_value = build_session_cookie(access_token)
    if not cookie_value:
        return None

    return fetch_json(
        API_USAGE_SUMMARY,
        {
            'Cookie': f'WorkosCursorSessionToken={cookie_value}',
            'Accept': 'application/json',
        },
    )


def fetch_premium_usage(access_token):
    """调用 api2.cursor.sh/auth/usage 获取高级请求用量"""
    return fetch_json(
        API_USAGE,
        {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        },
    )


def merge_usage_data(access_token):
    """整合所有用量数据为统一格式"""
    usage_data = create_empty_usage_data()

    summary = fetch_usage_summary(access_token)
    if summary and 'individualUsage' in summary:
        plan_usage = summary['individualUsage'].get('plan', {})
        usage_data["total_used"] = plan_usage.get('used', 0)
        usage_data["total_limit"] = plan_usage.get('limit', 2000)
        usage_data["remaining"] = plan_usage.get('remaining', 0)
        usage_data["total_percent_used"] = round(plan_usage.get('totalPercentUsed', 0), 1)
        usage_data["api_percent_used"] = round(plan_usage.get('apiPercentUsed', 0), 1)
        usage_data["plan_type"] = summary.get('membershipType', 'pro')
        usage_data["is_valid"] = True

        billing_cycle_start = summary.get('billingCycleStart', '')
        billing_cycle_end = summary.get('billingCycleEnd', '')
        if billing_cycle_start:
            usage_data["billing_cycle_start"] = billing_cycle_start[:10]
        if billing_cycle_end:
            usage_data["billing_cycle_end"] = billing_cycle_end[:10]

    premium_usage = fetch_premium_usage(access_token)
    if premium_usage:
        model_details = {}
        for model_name, model_info in premium_usage.items():
            if model_name == 'startOfMonth':
                continue
            model_details[model_name] = {
                "requests": model_info.get('numRequests', 0),
                "max_requests": model_info.get('maxRequestUsage', 0),
                "tokens": model_info.get('numTokens', 0),
            }
        usage_data["model_details"] = model_details

        if 'gpt-4' in premium_usage:
            usage_data["premium_used"] = premium_usage['gpt-4'].get('numRequests', 0)
            usage_data["premium_limit"] = premium_usage['gpt-4'].get('maxRequestUsage', 500)

        if not usage_data["billing_cycle_end"] and 'startOfMonth' in premium_usage:
            try:
                billing_start_date = datetime.datetime.fromisoformat(premium_usage['startOfMonth'].replace('Z', '+00:00'))
                usage_data["billing_cycle_start"] = billing_start_date.strftime('%Y-%m-%d')
                next_month = billing_start_date.month % 12 + 1
                next_year = billing_start_date.year + (billing_start_date.month // 12)
                billing_end_date = billing_start_date.replace(year=next_year, month=next_month)
                usage_data["billing_cycle_end"] = billing_end_date.strftime('%Y-%m-%d')
            except Exception:
                pass

        usage_data["is_valid"] = True

    return usage_data


def get_translation_dictionary_path():
    """获取翻译词典文本文件路径"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), TRANSLATION_DICTIONARY_NAME)


def parse_translation_entry(line, line_number):
    """解析单行翻译词条"""
    separator_index = line.find('=>')
    if separator_index == -1:
        raise ValueError(f"第 {line_number} 行缺少 => 分隔符")

    source_text, translated_text = [part.strip() for part in line.split('=>', 1)]

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


def generate_js_code(usage_data, translation_dictionary_data):
    """生成包含翻译、用量显示和实时刷新的完整 JavaScript 代码"""
    usage_json = json.dumps(usage_data, ensure_ascii=False)
    translation_dictionary_json = json.dumps(translation_dictionary_data, ensure_ascii=False)

    return '''\
/*
 * Cursor 汉化 + 用量监控脚本
 * Auto-generated by CursorTranslate.py
 * Generated: ''' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '''
 */
(function () {
    'use strict';

    const translationDictionary = new Map(Object.entries(''' + translation_dictionary_json + '''));
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
        [/^Automatically index any new folders with fewer than (\\d+) files$/i, "自动索引文件数少于 $1 的新文件夹"],
        [/^(\\d+) hooks?$/i, "$1 个钩子"],
        [/^(\\d+) automations?$/i, "$1 个自动化"],
        [/^(\\d+) rules?$/i, "$1 条规则"],
        [/^(\\d+) skills?$/i, "$1 个技能"],
        [/^(\\d+) commands?$/i, "$1 个命令"],
        [/^(\\d+) subagents?$/i, "$1 个子智能体"]
    ];

    const editorAreaSelector = '.monaco-editor, .overflow-guard, .view-lines, .editor-scrollable, .inputarea, .rename-input';
    const skippedTags = new Set(['TEXTAREA', 'INPUT', 'SCRIPT', 'STYLE', 'CODE', 'PRE', 'NOSCRIPT']);
    const usageData = ''' + usage_json + ''';
    const pendingNodes = [];
    let rescanCount = 0;
    const usageContainerSelectors = [
        '[class*="account"]',
        '[class*="profile"]',
        '[class*="user"]',
        '.settings-editor',
        '.pane-body'
    ];
    let isTranslationScheduled = false;

    function formatCompactNumber(value) {
        if (value >= 1e9) return (value / 1e9).toFixed(1) + 'B';
        if (value >= 1e6) return (value / 1e6).toFixed(1) + 'M';
        if (value >= 1e3) return (value / 1e3).toFixed(1) + 'K';
        return String(value);
    }

    function translateTextNode(node) {
        const text = node.textContent;
        if (!text) return;

        const trimmedText = text.trim();
        if (!trimmedText || trimmedText.length > 500) return;
        if (/^[\\d\\s.,;:!?@#$%^&*()\\-+=<>\\/\\\\|~`'"[\\]{}]+$/.test(trimmedText)) return;
        if (/[\\u4e00-\\u9fff]/.test(trimmedText) && (trimmedText.match(/[\\u4e00-\\u9fff]/g) || []).length > trimmedText.length * 0.3) return;

        if (translationDictionary.has(trimmedText)) {
            const prefix = text.substring(0, text.indexOf(trimmedText));
            const suffix = text.substring(text.indexOf(trimmedText) + trimmedText.length);
            node.textContent = prefix + translationDictionary.get(trimmedText) + suffix;
            return;
        }

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
            if (translationDictionary.has(trimmedValue)) {
                element.setAttribute(attributeName, translationDictionary.get(trimmedValue));
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
        if (element.id === 'cursor-usage-card') return;

        const ownText = getElementOwnText(element);
        const trimmedText = ownText.trim();
        if (!trimmedText || trimmedText.length > 120) return;
        if (!translationDictionary.has(trimmedText)) return;

        for (const childNode of element.childNodes) {
            if (childNode.nodeType === Node.TEXT_NODE && childNode.textContent.includes(trimmedText)) {
                childNode.textContent = childNode.textContent.replace(trimmedText, translationDictionary.get(trimmedText));
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
                if (node.id === 'cursor-usage-card') continue;

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
        try {
            renderUsageCard();
        } catch (error) {}
    }

    function rescanDocument() {
        try {
            translateTree(document.body);
            renderUsageCard();
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

    function buildModelDetailsHtml() {
        if (!usageData.model_details) return '';

        let html = '';
        for (const [modelName, detail] of Object.entries(usageData.model_details)) {
            html += '<div style="margin-top:4px;opacity:.85">' +
                modelName + '：' + detail.requests + ' / ' + detail.max_requests +
                '，Token ' + formatCompactNumber(detail.tokens || 0) +
                '</div>';
        }
        return html;
    }

    function buildUsageCardHtml() {
        return '' +
            '<div style="font-weight:600;margin-bottom:8px">用量监控</div>' +
            '<div>总用量：' + (usageData.total_used || 0) + ' / ' + (usageData.total_limit || 0) + '</div>' +
            '<div>高级请求：' + (usageData.premium_used || 0) + ' / ' + (usageData.premium_limit || 0) + '</div>' +
            '<div>剩余次数：' + (usageData.remaining || 0) + '</div>' +
            '<div>总使用率：' + (usageData.total_percent_used || 0) + '%</div>' +
            '<div>API 使用率：' + (usageData.api_percent_used || 0) + '%</div>' +
            '<div>计费周期：' + (usageData.billing_cycle_start || '-') + ' 至 ' + (usageData.billing_cycle_end || '-') + '</div>' +
            '<div>计划类型：' + (usageData.plan_type || '-') + '</div>' +
            '<div>更新时间：' + (usageData.updated_at || '-') + '</div>' +
            buildModelDetailsHtml();
    }

    function createUsageCardElement() {
        const card = document.createElement('div');
        card.id = 'cursor-usage-card';
        card.style.cssText = [
            'margin-top:12px',
            'padding:12px',
            'border:1px solid var(--vscode-widget-border)',
            'border-radius:8px',
            'background:var(--vscode-editorWidget-background)',
            'color:var(--vscode-foreground)',
            'font-size:12px',
            'line-height:1.6'
        ].join(';');
        card.innerHTML = buildUsageCardHtml();
        return card;
    }

    function findUsageContainer() {
        for (const selector of usageContainerSelectors) {
            const container = document.querySelector(selector);
            if (container) {
                return container;
            }
        }
        return null;
    }

    function renderUsageCard() {
        const existingCard = document.getElementById('cursor-usage-card');
        if (existingCard && existingCard.parentElement) {
            existingCard.replaceWith(createUsageCardElement());
            return;
        }

        const container = findUsageContainer();
        if (!container) return;

        container.appendChild(createUsageCardElement());
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
    renderUsageCard();
    scheduleStartupRescans();

    const observer = new MutationObserver(handleMutations);
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
    });
})();
'''


def get_workbench_dir():
    """获取 workbench 目录完整路径"""
    return os.path.join(CURSOR_INSTALL_PATH, WORKBENCH_RELATIVE_DIR)


def get_workbench_html_path():
    """获取 workbench.html 完整路径"""
    return os.path.join(get_workbench_dir(), WORKBENCH_HTML_NAME)


def get_translation_js_path():
    """获取翻译 JS 文件完整路径"""
    return os.path.join(get_workbench_dir(), TRANSLATION_JS_NAME)


def get_workbench_backup_path():
    """获取 workbench.html 备份文件路径"""
    return get_workbench_html_path() + BACKUP_SUFFIX


def get_product_json_path():
    """获取 product.json 完整路径"""
    return os.path.join(CURSOR_INSTALL_PATH, "resources", "app", "product.json")


def get_product_backup_path():
    """获取 product.json 备份路径"""
    return get_product_json_path() + BACKUP_SUFFIX


def get_default_install_path_hint():
    if CURRENT_PLATFORM == 'windows':
        return r"%LocalAppData%\Programs\cursor"
    return DEFAULT_CURSOR_INSTALL_PATH


def print_help():
    print("[用法] python CursorTranslate.py --apply [--cursorDir=\"路径\"]")
    print("[用法] python CursorTranslate.py --restore [--cursorDir=\"路径\"]")
    print("[用法] python CursorTranslate.py --help")
    print(f"[默认] 当前平台默认安装目录: {get_default_install_path_hint()}")
    print("[说明] 不带任何参数时仅显示帮助信息，不执行任何操作")
    print("[说明] 如 Cursor 不在默认位置，可通过 --cursorDir 指定安装目录")


def parse_arguments():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--help', action='store_true')
    parser.add_argument('--cursorDir', dest='cursor_dir')
    args, unknown_args = parser.parse_known_args()

    if unknown_args:
        print(f"\n[错误] 不支持的参数: {' '.join(unknown_args)}")
        print_help()
        sys.exit(1)

    selected_modes = [mode for mode, enabled in (("--apply", args.apply), ("--restore", args.restore)) if enabled]
    if len(selected_modes) > 1:
        print("\n[错误] --apply 与 --restore 不能同时使用")
        print_help()
        sys.exit(1)

    if args.help or not selected_modes:
        print_help()
        return None, args.cursor_dir

    return selected_modes[0], args.cursor_dir


def resolve_cursor_paths(custom_cursor_dir=None):
    global CURSOR_INSTALL_PATH

    if custom_cursor_dir:
        CURSOR_INSTALL_PATH = os.path.abspath(os.path.expanduser(custom_cursor_dir))


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


def cleanup_legacy_language_pack():
    """清理早期版本写入的本地 VS Code 语言包配置，避免覆盖编辑器自带中文语言包"""
    languagepacks_path = os.path.join(CURSOR_USER_DATA_PATH, "languagepacks.json")
    languagepacks_backup_path = languagepacks_path + BACKUP_SUFFIX
    argv_path = os.path.join(CURSOR_USER_DATA_PATH, "argv.json")
    argv_backup_path = argv_path + BACKUP_SUFFIX
    legacy_pack_dir = os.path.join(CURSOR_USER_DATA_PATH, "cursor-local-zh-cn")
    clp_cache_dir = os.path.join(CURSOR_USER_DATA_PATH, "clp")
    cleaned_legacy_pack = False

    if os.path.exists(languagepacks_backup_path):
        shutil.copy2(languagepacks_backup_path, languagepacks_path)
        os.remove(languagepacks_backup_path)
        print(f"[清理] 已恢复语言包配置: {languagepacks_path}")
        cleaned_legacy_pack = True
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

    if os.path.exists(argv_backup_path):
        shutil.copy2(argv_backup_path, argv_path)
        os.remove(argv_backup_path)
        print(f"[清理] 已恢复 argv.json: {argv_path}")

    if os.path.exists(legacy_pack_dir):
        shutil.rmtree(legacy_pack_dir)
        print(f"[清理] 已删除旧本地语言包目录: {legacy_pack_dir}")
        cleaned_legacy_pack = True

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


def write_translation_js(usage_data, translation_dictionary_data):
    """将翻译 + 用量 JavaScript 文件写入 Cursor 目录"""
    js_path = get_translation_js_path()
    js_content = generate_js_code(usage_data, translation_dictionary_data)
    write_text_file(js_path, js_content)
    print(f"[写入] 脚本已写入: {js_path}")


def inject_into_html():
    """在 workbench.html 中注入脚本引用"""
    workbench_html_path = get_workbench_html_path()
    html_content = read_text_file(workbench_html_path)
    injected_code = f'\n\t{INJECTION_MARKER}\n\t<script src="./{TRANSLATION_JS_NAME}"></script>\n'

    if '</body>' in html_content:
        html_content = html_content.replace('</body>', f'</body>\n{injected_code}')
    else:
        html_content = html_content.replace('</html>', f'{injected_code}\n</html>')

    write_text_file(workbench_html_path, html_content)
    print(f"[注入] 已在 workbench.html 中注入脚本引用")
    update_checksum()


def update_checksum():
    """更新 product.json 中 workbench.html 的校验哈希值"""
    product_json_path = get_product_json_path()
    workbench_html_path = get_workbench_html_path()

    if not os.path.exists(product_json_path):
        print(f"[警告] 未找到 product.json: {product_json_path}")
        return

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
    else:
        print(f"[警告] product.json 中未找到 workbench.html 的校验条目")


def restore_checksum():
    """恢复 product.json 的原始校验值"""
    product_json_path = get_product_json_path()
    product_backup_path = get_product_backup_path()
    if os.path.exists(product_backup_path):
        shutil.copy2(product_backup_path, product_json_path)
        os.remove(product_backup_path)
        print(f"[校验] 已恢复 product.json 原始校验值")


def remove_injected_script(html_content):
    updated_lines = []
    skip_script_line = False
    for line in html_content.splitlines(keepends=True):
        if INJECTION_MARKER in line:
            skip_script_line = True
            continue
        if skip_script_line and f'<script src="./{TRANSLATION_JS_NAME}"></script>' in line:
            skip_script_line = False
            continue
        if not skip_script_line:
            updated_lines.append(line)
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


def print_usage_summary(usage_data):
    if usage_data and usage_data.get("is_valid"):
        print(f"[用量] 总用量: {usage_data['total_used']} / {usage_data['total_limit']} 次")
        print(f"[用量] 高级请求: {usage_data['premium_used']} / {usage_data['premium_limit']} 次")
        print(f"[用量] 剩余: {usage_data['remaining']} 次")
        if usage_data.get('billing_cycle_start'):
            print(f"[用量] 计费周期: {usage_data['billing_cycle_start']} 至 {usage_data['billing_cycle_end']}")
    else:
        print("[用量] 获取用量数据失败，将仅汉化")


def main():
    """主程序入口"""
    print("=" * 60)
    print("  Cursor 汉化 + 用量监控工具")
    print(f"  平台: {CURRENT_PLATFORM}")
    print(f"  时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    mode, custom_cursor_dir = parse_arguments()
    resolve_cursor_paths(custom_cursor_dir)

    if mode is None:
        return

    validate_cursor_installation()
    cleanup_legacy_language_pack()

    if mode == '--restore':
        print("\n[模式] 恢复原始文件...")
        restore_original()
        return

    print("\n[步骤 1/4] 读取认证信息...")
    access_token, email = read_access_token()
    if access_token:
        print(f"[认证] 已找到令牌，邮箱: {email or '未知'}")
    else:
        print("[认证] 未找到认证令牌，将跳过用量获取（仅汉化）")

    if access_token:
        print("\n[步骤 2/4] 获取用量数据...")
        usage_data = merge_usage_data(access_token)
        print_usage_summary(usage_data)
    else:
        print("\n[步骤 2/4] 跳过用量获取（无令牌）")
        usage_data = create_empty_usage_data()

    print("\n[步骤 3/5] 读取翻译词典...")
    translation_dictionary_data = read_translation_dictionary()
    print(f"[词典] 已加载 {len(translation_dictionary_data)} 条翻译")

    if is_already_injected():
        print("\n[检测] 脚本已注入，正在更新...")
        write_translation_js(usage_data, translation_dictionary_data)
        update_checksum()
        print("\n[完成] 脚本已更新！重启 Cursor 生效。")
        return

    print(f"\n[步骤 4/5] 创建备份并写入脚本...")
    create_backup()
    write_translation_js(usage_data, translation_dictionary_data)

    print("[步骤 5/5] 注入 HTML 引用...")
    inject_into_html()

    print("\n" + "=" * 60)
    print("  [完成] Cursor 汉化 + 用量监控 注入成功！")
    print("  请重启 Cursor 以查看效果。")
    print("  如需恢复: python CursorTranslate.py --restore")
    print("  如需重新应用: python CursorTranslate.py --apply")
    print("=" * 60)


if __name__ == '__main__':
    main()
