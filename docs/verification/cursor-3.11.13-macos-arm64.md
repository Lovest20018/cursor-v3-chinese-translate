# Cursor 3.11.13 macOS ARM64 验证记录

## 环境

- 日期：2026-07-13
- macOS：26.x / Apple Silicon arm64
- Cursor：3.11.13
- commit：`3f21b08f0b436a07be29fbfe00b304fa15553350`
- 验收载体：`/tmp/cursor-v3-verify-311/Cursor.app`（自 `/Applications/Cursor.app` 复制，隔离 user-data）

## 自动化结果

| 命令 | 结果 |
|------|------|
| `python3 -m py_compile CursorTranslate.py` | 通过 |
| `python3 -m unittest -v` | 24 passed |
| `python3 -m unittest discover -s tests -v` | 13 passed |
| `python3 smoke_test.py` | 通过 |
| `npm test`（jsdom DOM 套件） | 8 passed |
| `node --check cursor_hanhua.js` | 通过 |

## 副本安装验收

1. 记录关键文件 SHA-256（workbench.html / product.json / main.js / nls.messages.json / workbench.desktop.main.js）
2. `--check`：识别 3.11.13、checksum key、注入锚点；检测到 BYOK `backup-byok-*` 并声明保留
3. `--apply`：注入 marker + `cursor_hanhua.js`，product.json checksum 与 HTML 匹配
4. 启动副本（`--user-data-dir` 隔离）：进程可拉起
5. `--restore`：上述 5 个文件 SHA-256 全部回到安装前值；`cursor_hanhua.js` 删除；外部 `backup-byok-*` 仍在

## DOM 证据（Settings fixture，基于 3.11 实测结构）

见 `cursor-3.11.13-settings-dom-evidence.json`。

侧栏译文包括：

- 通用 / 智能体 / 云端智能体 / 模型
- Git 与 PR / 插件 / 规则、技能、子智能体
- 工具与 MCP / 钩子 / 浏览器与网络 / 索引与文档
- 管理您的账户和账单
- 认识全新的智能体窗口

并验证：

- React/Solid 写回英文后重新翻译
- title/placeholder 属性翻译
- 模型选项 `claude-4-sonnet` / `gpt-5` / `Auto` / `High` 不译
- 用户输入、代码、路径不译
- 普通 VS Code Settings fixture 不译

## 代码签名

- 修改后 `codesign --verify --deep --strict` 失败（sealed resource invalid）
- 源副本在 BYOK 等既有补丁下基线也可能已非官方密封状态
- product.json checksum **仅**服务 Cursor 资源校验，不能恢复 Developer ID 签名
- 官方 DMG 仍是灾难回退路径

## 共存

- 未删除任何 `backup-byok-*`
- 本工具 marker 与外部备份并行存在
- restore 只撤销本工具写入

## 说明

完整 GUI 逐页截图依赖本机窗口环境；本记录以：

1. 真实 bundle 副本 apply/restore 哈希闭环  
2. 基于 3.11 实测 DOM 结构的 jsdom 可见文本证据  
3. 隔离 user-data 的进程拉起  

作为验收支撑。若需像素级截图，可在关闭主 Cursor 后对副本手动打开 Cursor Settings 各页补充。
