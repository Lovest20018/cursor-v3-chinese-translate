/*
 * Cursor V3 Chinese Translate runtime
 * Auto-generated — DO NOT EDIT MANUALLY
 */
(function () {
    'use strict';

    const TOOL_NAME = __TOOL_NAME__;
    const TOOL_VERSION = __TOOL_VERSION__;
    const MANIFEST_ID = __MANIFEST_ID__;
    const RUNTIME_SYMBOL = Symbol.for('cursor-v3-chinese-translate.runtime');
    const TEST_MODE = Boolean(globalThis.__CURSOR_V3_TRANSLATE_TEST__);

    const translationDictionary = new Map(Object.entries(__TRANSLATION_DICTIONARY__));
    const normalizedTranslationDictionary = new Map();
    for (const [sourceText, translatedText] of translationDictionary.entries()) {
        const normalizedSourceText = normalizeTranslationWhitespace(sourceText);
        if (normalizedSourceText && !normalizedTranslationDictionary.has(normalizedSourceText)) {
            normalizedTranslationDictionary.set(normalizedSourceText, translatedText);
        }
    }
    const protectedExactTexts = new Set(__PROTECTED_EXACT_TEXTS__);

    // 有限、锚定的动态模式；禁止宽泛句子匹配
    const translationPatterns = [
        [/^(\d+) requests? remaining$/i, '$1 次请求剩余'],
        [/^(\d+) of (\d+) requests?$/i, '$1 / $2 次请求'],
        [/^(\d+) premium requests?$/i, '$1 次高级请求'],
        [/^(\d+) files? indexed$/i, '$1 个文件已索引'],
        [/^Indexing (\d+) files?$/i, '正在索引 $1 个文件'],
        [/^(\d+) errors?$/i, '$1 个错误'],
        [/^(\d+) warnings?$/i, '$1 个警告'],
        [/^Version (.+)$/i, '版本 $1'],
        [/^(\d+) tools?$/i, '$1 个工具'],
        [/^(\d+) resources?$/i, '$1 个资源'],
        [/^(\d+) prompts?$/i, '$1 个提示词'],
        [/^New Agent in (.+)$/i, '在 $1 中新建智能体'],
        [/^Updated (.+) ago$/i, '$1前更新'],
        [/^(\d+) seconds? ago$/i, '$1 秒前'],
        [/^(\d+) minutes? ago$/i, '$1 分钟前'],
        [/^(\d+) hours? ago$/i, '$1 小时前'],
        [/^(\d+) days? ago$/i, '$1 天前'],
        [/^(\d+) hooks?$/i, '$1 个钩子'],
        [/^(\d+) automations?$/i, '$1 个自动化'],
        [/^(\d+) rules?$/i, '$1 条规则'],
        [/^(\d+) skills?$/i, '$1 个技能'],
        [/^(\d+) commands?$/i, '$1 个命令'],
        [/^(\d+) subagents?$/i, '$1 个子智能体'],
        [/^(\d+) Queued$/i, '$1 条已排队'],
        [/^Thought briefly$/i, '短暂思考'],
        [/^Thought for ([\d.]+)s$/i, '思考耗时 $1 秒'],
        [/^Worked for ([\d.]+)s$/i, '工作耗时 $1 秒'],
        [/^Done • (.+)$/i, '已完成 • $1'],
        [/^Completed (\d+) of (\d+)$/i, '已完成 $1 / $2'],
        [/^Completed (\d+) of (\d+) to-dos$/i, '已完成 $1 / $2 个待办'],
        [/^Automatically index any new folders with fewer than ([\d,]+) files\.?$/i, '自动索引文件数少于 $1 的新文件夹。']
    ];

    const ATTR_NAMES = ['title', 'aria-label', 'placeholder', 'aria-placeholder', 'aria-description'];
    const skippedTags = new Set(['TEXTAREA', 'INPUT', 'SCRIPT', 'STYLE', 'CODE', 'PRE', 'NOSCRIPT', 'CANVAS', 'SVG', 'IFRAME', 'WEBVIEW']);
    const editorAreaSelector = [
        '.monaco-editor',
        '.overflow-guard',
        '.view-lines',
        '.editor-scrollable',
        '.inputarea',
        '.rename-input',
        '.xterm',
        '.terminal',
        '.terminal-wrapper',
        '.monaco-diff-editor',
        '.diffOverview',
        '.webview',
        'webview',
        'iframe',
        '.interactive-session',
        '.chat-editor-container',
        '.composer-human-message',
        '.aislash-editor-input'
    ].join(', ');

    const textState = new WeakMap();
    const attrState = new WeakMap();
    const pendingNodes = new Set();
    const maxPendingNodes = 500;
    const maxNodesPerFrame = 120;
    let isTranslationScheduled = false;
    let observer = null;
    let applyingWrite = false;

    const metrics = {
        observerCount: 0,
        queueHighWater: 0,
        processedNodes: 0,
        selfMutationsIgnored: 0,
        rootRescans: 0,
        translations: 0
    };

    function normalizeTranslationWhitespace(text) {
        return String(text || '').replace(/\s+/g, ' ').trim();
    }

    function isMostlyChinese(text) {
        if (!text) return false;
        const chars = text.match(/[\u4e00-\u9fff]/g);
        if (!chars) return false;
        return chars.length > text.length * 0.3;
    }

    function lookupTranslation(text, context) {
        if (!text) return null;
        const normalized = normalizeTranslationWhitespace(text);
        if (!normalized) return null;

        // 模型选择器 / 技术上下文中保护短标识
        if (
            (context === 'model-provider-picker' || context === 'protected-technical') &&
            protectedExactTexts.has(normalized)
        ) {
            return null;
        }
        // 非自然语言上下文时也保护
        if (context !== 'cursor-settings' && context !== 'cursor-command-ui' && protectedExactTexts.has(normalized)) {
            return null;
        }

        if (translationDictionary.has(text)) {
            return translationDictionary.get(text);
        }
        if (translationDictionary.has(normalized)) {
            return translationDictionary.get(normalized);
        }
        if (normalizedTranslationDictionary.has(normalized)) {
            return normalizedTranslationDictionary.get(normalized);
        }
        return null;
    }

    function translateByPattern(text, context) {
        if (!text || context === 'protected-input' || context === 'protected-editor' ||
            context === 'protected-conversation' || context === 'vscode-settings' ||
            context === 'model-provider-picker' || context === 'unknown') {
            return null;
        }
        if (text.length > 200) return null;
        for (const [pattern, replacement] of translationPatterns) {
            if (pattern.test(text)) {
                // 重置 lastIndex 保险
                pattern.lastIndex = 0;
                if (!pattern.test(text)) continue;
                pattern.lastIndex = 0;
                return text.replace(pattern, replacement);
            }
        }
        return null;
    }

    function translateText(text, context) {
        const exact = lookupTranslation(text, context);
        if (exact !== null) return exact;
        return translateByPattern(text, context);
    }

    function closestElement(node) {
        if (!node) return null;
        return node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    }

    function hasSelector(element, selector) {
        try {
            return Boolean(element && element.closest && element.closest(selector));
        } catch (_error) {
            return false;
        }
    }

    function isEditable(element) {
        if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;
        if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') return true;
        if (element.isContentEditable || element.getAttribute('contenteditable') === 'true') return true;
        const role = (element.getAttribute('role') || '').toLowerCase();
        return role === 'textbox' || role === 'searchbox' || role === 'combobox';
    }

    function isModelProviderContext(element) {
        if (!element) return false;
        try {
            const option = element.closest('[role="option"], [role="menuitem"], [role="menuitemradio"]');
            if (option) {
                const list = option.closest('[role="listbox"], [role="menu"], [role="list"]');
                if (list) {
                    const label = ((list.getAttribute('aria-label') || '') + ' ' + (list.getAttribute('title') || '')).toLowerCase();
                    if (/model|provider|model picker|models/.test(label)) return true;
                    // 模型列表常见：短标识 + 技术名
                    const text = normalizeTranslationWhitespace(option.textContent || '');
                    if (/^(gpt|claude|gemini|o\d|cursor-small|cursor-fast|sonnet|opus)/i.test(text)) return true;
                    if (protectedExactTexts.has(text)) return true;
                }
            }
            if (element.closest('[data-fixture="model-picker"], .cursor-model-picker, .model-picker')) {
                return true;
            }
        } catch (_error) {}
        return false;
    }

    function findCursorSettingsRoot(element) {
        if (!element || !element.closest) return null;
        // 稳定类名优先（Cursor 3.11 实测）
        const label = element.closest('.cursor-settings-sidebar-cell-label, .cursor-settings-layout-main, .cursor-settings-pane-content, .cursor-settings-section, .cursor-settings-cell');
        if (!label) {
            // 允许从任意子节点向上找 layout
            const layout = element.closest('.cursor-settings-layout-main');
            return layout;
        }
        const layout = label.closest('.cursor-settings-layout-main') || label.closest('[data-fixture="cursor-settings"]');
        if (layout) return layout;

        // 回退契约：>=3 个 sidebar nav cell + Search Settings 输入框
        const navCell = element.closest('.cursor-settings-sidebar-nav-cell, .cursor-settings-sidebar-cell');
        if (!navCell) return null;
        const navParent = navCell.parentElement;
        if (!navParent) return null;
        const navCount = navParent.querySelectorAll('.cursor-settings-sidebar-nav-cell, .cursor-settings-sidebar-cell-label').length;
        if (navCount < 3) return null;
        let root = navParent;
        for (let depth = 0; depth < 6 && root; depth += 1) {
            const hasSearch = root.querySelector(
                'input[placeholder="Search settings"], input[placeholder="Search Settings"], input[aria-label="Search Settings"], input[aria-label="Search settings"]'
            );
            if (hasSearch) return root;
            root = root.parentElement;
        }
        return navParent.parentElement || navParent;
    }

    function isVscodeSettings(element) {
        return hasSelector(element, '.settings-editor, .settings-header, .settings-toc-container, .settings-body, .setting-item');
    }

    function isProtectedConversation(element) {
        return hasSelector(
            element,
            [
                '.composer-human-message',
                '.aislash-editor-input',
                '.chat-message-container',
                '.interactive-session',
                '[data-message-role]',
                '.markdown-content',
                '.anysphere-markdown-container-root'
            ].join(', ')
        );
    }

    function classifyNode(node) {
        const element = closestElement(node);
        if (!element) return 'unknown';

        if (isEditable(element) && element.tagName !== 'BUTTON') {
            // 搜索框 placeholder 仍可翻译属性；当前值不翻译
            if (node.nodeType === Node.TEXT_NODE && isEditable(element)) {
                return 'protected-input';
            }
        }
        if (hasSelector(element, editorAreaSelector) || skippedTags.has(element.tagName)) {
            if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
                return 'protected-input';
            }
            if (skippedTags.has(element.tagName) && element.tagName !== 'INPUT') {
                return 'protected-editor';
            }
            return 'protected-editor';
        }
        if (isProtectedConversation(element)) return 'protected-conversation';
        if (isVscodeSettings(element) && !findCursorSettingsRoot(element)) return 'vscode-settings';
        if (isModelProviderContext(element)) return 'model-provider-picker';
        if (findCursorSettingsRoot(element)) return 'cursor-settings';

        // Cursor 命令 UI：菜单/对话框/tooltip
        try {
            if (element.closest('[role="menu"], [role="dialog"], [role="listbox"], .monaco-menu, .context-view, .tooltip-content, .cursor-settings-inline-banner')) {
                // 若属于 VS Code 原生且非 Cursor settings，仍可能翻译有限词条
                if (isVscodeSettings(element)) return 'vscode-settings';
                return 'cursor-command-ui';
            }
        } catch (_error) {}

        // 默认：允许对已知词典做翻译（覆盖 Agents Window 顶栏等），
        // 但模型/受保护上下文已在上面拦截
        return 'cursor-command-ui';
    }

    function shouldTranslateContext(context) {
        return context === 'cursor-settings' || context === 'cursor-command-ui';
    }

    function applyTextNode(node, context) {
        if (!node || node.nodeType !== Node.TEXT_NODE) return;
        if (!shouldTranslateContext(context) && context !== 'cursor-settings') return;

        const raw = node.textContent;
        if (raw == null) return;
        const trimmed = raw.trim();
        if (!trimmed || trimmed.length > 2500) return;
        if (/^[\d\s.,;:!?@#$%^&*()\-+=<>\/\\|~`'"[\]{}]+$/.test(trimmed)) return;

        const state = textState.get(node);
        if (state && state.applied === raw) {
            metrics.selfMutationsIgnored += 1;
            return;
        }

        // React/Solid 写回英文：raw 变成 source
        const source = (state && state.applied && raw === state.applied)
            ? state.source
            : trimmed;

        if (isMostlyChinese(trimmed) && !(state && state.source && translateText(state.source, context) === trimmed)) {
            // 已是中文且不是我们已知应用结果时跳过
            if (!state || state.applied !== raw) {
                return;
            }
        }

        const lookupSource = state && state.source && (raw === state.applied || raw === state.source)
            ? state.source
            : trimmed;

        // 若当前是英文（或与 source 不同的新值），按当前文本查
        const currentLookup = translateText(trimmed, context);
        const stableLookup = currentLookup !== null ? currentLookup : translateText(lookupSource, context);
        if (stableLookup === null) return;

        const startIndex = raw.indexOf(trimmed);
        const next = startIndex === -1
            ? stableLookup
            : raw.substring(0, startIndex) + stableLookup + raw.substring(startIndex + trimmed.length);

        if (next === raw) {
            textState.set(node, { source: lookupSource, applied: raw, context });
            return;
        }

        applyingWrite = true;
        try {
            node.textContent = next;
            metrics.translations += 1;
            textState.set(node, {
                source: currentLookup !== null ? trimmed : lookupSource,
                applied: next,
                context
            });
        } finally {
            applyingWrite = false;
        }
    }

    function applyAttributes(element, context) {
        if (!element || element.nodeType !== Node.ELEMENT_NODE) return;
        if (!shouldTranslateContext(context)) {
            // 输入框仍可翻译 placeholder
            if (!(context === 'protected-input' && (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA'))) {
                return;
            }
        }

        let state = attrState.get(element);
        if (!state) {
            state = {};
            attrState.set(element, state);
        }

        for (const name of ATTR_NAMES) {
            if (!element.hasAttribute(name)) continue;
            // 输入框当前 value 永不翻译；placeholder 可以
            if (context === 'protected-input' && name !== 'placeholder' && name !== 'aria-placeholder' && name !== 'aria-label' && name !== 'title') {
                continue;
            }
            const raw = element.getAttribute(name);
            if (!raw) continue;
            const trimmed = raw.trim();
            if (!trimmed) continue;

            const prev = state[name];
            if (prev && prev.applied === raw) {
                metrics.selfMutationsIgnored += 1;
                continue;
            }

            const translated = translateText(trimmed, context === 'protected-input' ? 'cursor-settings' : context);
            if (translated === null || translated === trimmed) {
                state[name] = { source: trimmed, applied: raw, context };
                continue;
            }

            applyingWrite = true;
            try {
                element.setAttribute(name, translated);
                metrics.translations += 1;
                state[name] = { source: trimmed, applied: translated, context };
            } finally {
                applyingWrite = false;
            }
        }
    }

    function translateTree(root) {
        if (!root) return;
        const stack = [root];
        while (stack.length > 0) {
            const node = stack.pop();
            if (!node) continue;

            if (node.nodeType === Node.ELEMENT_NODE) {
                // 不进入 shadow / iframe
                if (node.tagName === 'IFRAME' || node.tagName === 'WEBVIEW') continue;
                if (node.shadowRoot) {
                    // 明确不支持 Shadow DOM 遍历
                    continue;
                }

                const context = classifyNode(node);

                if (skippedTags.has(node.tagName) || isEditable(node)) {
                    // 仍尝试属性（placeholder 等）
                    applyAttributes(node, context === 'unknown' ? 'protected-input' : context);
                    continue;
                }

                if (context === 'protected-editor' || context === 'protected-conversation' || context === 'vscode-settings') {
                    continue;
                }

                if (context === 'model-provider-picker') {
                    // 不翻译选项文本，但外层 framing 可能在父级处理
                    applyAttributes(node, context);
                    continue;
                }

                applyAttributes(node, context);
                for (let i = node.childNodes.length - 1; i >= 0; i -= 1) {
                    stack.push(node.childNodes[i]);
                }
            } else if (node.nodeType === Node.TEXT_NODE) {
                const context = classifyNode(node);
                if (shouldTranslateContext(context)) {
                    applyTextNode(node, context);
                }
            }
        }
    }

    function collectCursorRoots(doc) {
        const roots = [];
        try {
            doc.querySelectorAll('.cursor-settings-layout-main, [data-fixture="cursor-settings"]').forEach((node) => roots.push(node));
            if (roots.length === 0) {
                const labels = doc.querySelectorAll('.cursor-settings-sidebar-cell-label');
                if (labels.length >= 3) {
                    const candidate = findCursorSettingsRoot(labels[0]);
                    if (candidate) roots.push(candidate);
                }
            }
        } catch (_error) {}
        return roots;
    }

    function enqueueNode(node) {
        if (!node || applyingWrite) return;
        if (pendingNodes.size >= maxPendingNodes) {
            pendingNodes.clear();
            // 溢出时只重扫识别到的 Cursor 根，避免整页抖动
            const roots = collectCursorRoots(document);
            if (roots.length > 0) {
                for (const root of roots) pendingNodes.add(root);
                metrics.rootRescans += 1;
            } else if (document.body) {
                pendingNodes.add(document.body);
                metrics.rootRescans += 1;
            }
        } else {
            pendingNodes.add(node);
        }
        metrics.queueHighWater = Math.max(metrics.queueHighWater, pendingNodes.size);
        if (!isTranslationScheduled) {
            isTranslationScheduled = true;
            requestAnimationFrame(processPendingNodes);
        }
    }

    function processPendingNodes() {
        const batch = [];
        for (const node of pendingNodes) {
            batch.push(node);
            pendingNodes.delete(node);
            if (batch.length >= maxNodesPerFrame) break;
        }
        isTranslationScheduled = false;
        for (const node of batch) {
            try {
                translateTree(node);
                metrics.processedNodes += 1;
            } catch (_error) {}
        }
        if (pendingNodes.size > 0) {
            isTranslationScheduled = true;
            requestAnimationFrame(processPendingNodes);
        }
    }

    function shouldSkipMutationTarget(node) {
        const element = closestElement(node);
        if (!element) return true;
        try {
            if (element.closest(editorAreaSelector)) return true;
            if (element.closest('iframe, webview, .webview')) return true;
        } catch (_error) {}
        return false;
    }

    function handleMutations(mutations) {
        if (applyingWrite) return;
        for (const mutation of mutations) {
            if (mutation.type === 'childList') {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.TEXT_NODE) {
                        if (shouldSkipMutationTarget(node)) continue;
                        enqueueNode(node);
                    }
                }
            } else if (mutation.type === 'characterData' && mutation.target && mutation.target.nodeType === Node.TEXT_NODE) {
                if (shouldSkipMutationTarget(mutation.target)) continue;
                const state = textState.get(mutation.target);
                if (state && state.applied === mutation.target.textContent) {
                    metrics.selfMutationsIgnored += 1;
                    continue;
                }
                enqueueNode(mutation.target);
            } else if (mutation.type === 'attributes' && mutation.target && mutation.target.nodeType === Node.ELEMENT_NODE) {
                if (shouldSkipMutationTarget(mutation.target)) continue;
                enqueueNode(mutation.target);
            }
        }
    }

    function disconnectExisting() {
        const existing = globalThis[RUNTIME_SYMBOL];
        if (existing && existing.disconnect) {
            try { existing.disconnect(); } catch (_error) {}
        }
    }

    function start() {
        disconnectExisting();
        if (!document.body) {
            document.addEventListener('DOMContentLoaded', start, { once: true });
            return;
        }

        translateTree(document.body);
        // Solid/React 首屏异步挂载：有限次根重扫
        const delays = [200, 800, 1600, 3200];
        for (const delay of delays) {
            setTimeout(() => {
                const roots = collectCursorRoots(document);
                if (roots.length > 0) {
                    for (const root of roots) translateTree(root);
                    metrics.rootRescans += 1;
                } else {
                    translateTree(document.body);
                }
            }, delay);
        }

        observer = new MutationObserver(handleMutations);
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
            attributes: true,
            attributeFilter: ATTR_NAMES
        });
        metrics.observerCount = 1;

        const api = {
            toolName: TOOL_NAME,
            toolVersion: TOOL_VERSION,
            manifestId: MANIFEST_ID,
            disconnect() {
                if (observer) {
                    observer.disconnect();
                    observer = null;
                    metrics.observerCount = 0;
                }
                pendingNodes.clear();
                isTranslationScheduled = false;
            },
            translateTree,
            classifyNode,
            lookupTranslation,
            metrics,
            enqueueNode,
            rescan() {
                const roots = collectCursorRoots(document);
                if (roots.length) roots.forEach(translateTree);
                else translateTree(document.body);
            }
        };
        globalThis[RUNTIME_SYMBOL] = api;
        if (TEST_MODE) {
            globalThis.__CURSOR_V3_TRANSLATE_API__ = api;
        }
    }

    start();
})();
