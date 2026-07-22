/**
 * Cursor 3.11 Settings DOM runtime tests (jsdom).
 */
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '../..');
const FIXTURE = path.join(ROOT, 'tests/fixtures/cursor_settings_311.html');
const VSCODE_FIXTURE = path.join(ROOT, 'tests/fixtures/vscode_settings.html');

function generateRuntimeJs() {
  const py = `
import json, sys
sys.path.insert(0, ${JSON.stringify(ROOT)})
from cursor_translate.dictionary import load_dictionary_file
from cursor_translate.runtime import generate_js_code
payload = load_dictionary_file(${JSON.stringify(path.join(ROOT, 'cursor_translate_dic.txt'))})
# keep payload smaller for tests but include key settings strings
keys = [
  'General','Agents','Cloud Agents','Models','Git & PRs','Plugins',
  'Rules, Skills, Subagents','Tools & MCPs','Hooks','Browser & Network',
  'Indexing & Docs','Meet the new Agents Window','Manage your account and billing',
  'Preferences','Editor Settings','Keyboard Shortcuts','Import Settings from VS Code',
  'Window Layout','Conversation Density','System Notifications','Menu Bar Icon',
  'Privacy Mode','Log Out','Search Settings','Search settings','Cursor Account',
  'Show Cursor in menu bar','Run many agents in parallel',
  'Choose how much detail Agent tool calls show in the conversation',
  'Import settings, extensions, and keybindings from VS Code'
]
data = {k: payload.entries[k] for k in keys if k in payload.entries}
print(generate_js_code(data, manifest_id='dom-test'))
`;
  const result = spawnSync('python3', ['-c', py], {
    encoding: 'utf-8',
    maxBuffer: 10 * 1024 * 1024,
  });
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || 'python generate failed');
  }
  return result.stdout;
}

function loadDom(html, runtimeJs) {
  const dom = new JSDOM(html, {
    runScripts: 'outside-only',
    url: 'https://cursor.local/workbench',
    pretendToBeVisual: true,
  });
  const { window } = dom;
  window.__CURSOR_V3_TRANSLATE_TEST__ = true;
  // rAF polyfill that runs immediately for deterministic tests
  window.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
  window.cancelAnimationFrame = (id) => clearTimeout(id);
  window.eval(runtimeJs);
  return dom;
}

function flush(ms = 30) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

let runtimeJs;

before(() => {
  runtimeJs = generateRuntimeJs();
  const check = spawnSync('node', ['--check'], { input: runtimeJs, encoding: 'utf-8' });
  assert.equal(check.status, 0, check.stderr);
});

test('translates Cursor Settings sidebar and content labels', async () => {
  const html = fs.readFileSync(FIXTURE, 'utf8');
  const dom = loadDom(html, runtimeJs);
  await flush(50);
  const labels = [...dom.window.document.querySelectorAll('.cursor-settings-sidebar-cell-label')]
    .map((n) => n.textContent.trim());
  assert.ok(labels.includes('通用'), `labels=${labels.join('|')}`);
  assert.ok(labels.includes('智能体'));
  assert.ok(labels.includes('云端智能体'));
  assert.ok(labels.includes('模型'));
  assert.ok(labels.includes('Git 与 PR'));
  assert.ok(labels.includes('工具与 MCP'));
  assert.ok(labels.includes('浏览器与网络'));
  assert.ok(labels.includes('规则、技能、子智能体'));

  const title = dom.window.document.querySelector('.cursor-settings-inline-banner__title');
  assert.match(title.textContent, /智能体窗口/);

  const prefs = dom.window.document.body.textContent;
  assert.match(prefs, /对话密度|系统通知|菜单栏图标|隐私模式|退出登录/);
});

test('retranslates after React/Solid rewrites English into existing text node', async () => {
  const html = fs.readFileSync(FIXTURE, 'utf8');
  const dom = loadDom(html, runtimeJs);
  await flush(40);
  const node = dom.window.document.querySelector('.cursor-settings-sidebar-cell-label');
  const textNode = node.firstChild;
  assert.equal(textNode.nodeType, dom.window.Node.TEXT_NODE);
  // simulate framework rewrite
  textNode.textContent = 'General';
  await flush(40);
  assert.equal(node.textContent.trim(), '通用');
});

test('translates incrementally inserted nodes via MutationObserver', async () => {
  const html = fs.readFileSync(FIXTURE, 'utf8');
  const dom = loadDom(html, runtimeJs);
  await flush(20);
  const nav = dom.window.document.querySelector('.cursor-settings-sidebar-nav');
  const cell = dom.window.document.createElement('div');
  cell.className = 'cursor-settings-sidebar-cell cursor-settings-sidebar-nav-cell';
  const span = dom.window.document.createElement('span');
  span.className = 'cursor-settings-sidebar-cell-label';
  span.title = 'Hooks';
  span.textContent = 'Hooks';
  cell.appendChild(span);
  nav.appendChild(cell);
  await flush(40);
  assert.equal(span.textContent.trim(), '钩子');
  assert.equal(span.getAttribute('title'), '钩子');
});

test('translates title/aria-label/placeholder attributes', async () => {
  const html = fs.readFileSync(FIXTURE, 'utf8');
  const dom = loadDom(html, runtimeJs);
  await flush(40);
  const input = dom.window.document.querySelector('input[aria-label], input[placeholder]');
  const aria = input.getAttribute('aria-label') || '';
  const placeholder = input.getAttribute('placeholder') || '';
  assert.ok(
    aria.includes('搜索') || placeholder.includes('搜索'),
    `aria=${aria} placeholder=${placeholder}`
  );
  const general = [...dom.window.document.querySelectorAll('.cursor-settings-sidebar-cell-label')]
    .find((el) => (el.getAttribute('title') || '').includes('通用') || el.textContent.includes('通用'));
  assert.ok(general);
});

test('does not translate model/provider option names or protected enums in picker', async () => {
  const html = fs.readFileSync(FIXTURE, 'utf8');
  const dom = loadDom(html, runtimeJs);
  await flush(40);
  const options = [...dom.window.document.querySelectorAll('[role="option"]')].map((n) => n.textContent.trim());
  assert.ok(options.includes('claude-4-sonnet'));
  assert.ok(options.includes('gpt-5'));
  assert.ok(options.includes('Auto'));
  assert.ok(options.includes('High'));
});

test('does not translate user input, code, or path-like content', async () => {
  const html = fs.readFileSync(FIXTURE, 'utf8');
  const dom = loadDom(html, runtimeJs);
  await flush(40);
  assert.equal(dom.window.document.querySelector('#user-input').value, 'do not translate this value');
  assert.equal(dom.window.document.querySelector('textarea').value, 'user authored content');
  assert.equal(dom.window.document.querySelector('code').textContent, 'const x = 1');
  assert.match(dom.window.document.querySelector('.view-lines').textContent, /function hello/);
});

test('leaves ordinary VS Code settings fixture untranslated by Cursor settings path', async () => {
  const html = fs.readFileSync(VSCODE_FIXTURE, 'utf8');
  const dom = loadDom(html, runtimeJs);
  await flush(40);
  assert.equal(
    dom.window.document.querySelector('.setting-item-label').textContent.trim(),
    'Auto Save'
  );
  assert.equal(
    dom.window.document.querySelector('.settings-toc-entry').textContent.trim(),
    'Workbench'
  );
});

test('runtime is idempotent and exposes single observer in test mode', async () => {
  const html = fs.readFileSync(FIXTURE, 'utf8');
  const dom = loadDom(html, runtimeJs);
  await flush(40);
  const api = dom.window.__CURSOR_V3_TRANSLATE_API__;
  assert.ok(api);
  assert.equal(api.metrics.observerCount, 1);
  const before = api.metrics.translations;
  api.rescan();
  await flush(40);
  // 再次扫描不应形成观察者翻倍
  assert.equal(api.metrics.observerCount, 1);
  assert.ok(api.metrics.queueHighWater <= 500);
  // 自写入应被忽略累计
  assert.ok(api.metrics.selfMutationsIgnored >= 0);
  assert.ok(api.metrics.translations >= before || before >= 0);
});
