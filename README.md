# Cursor V3 Chinese Translate

> Cursor 自定义 UI 中文增强翻译工具。通过注入前端运行时翻译脚本，并按需补丁少量 Electron 原生菜单资源，补全官方 VS Code 简体中文语言包覆盖不到的 Cursor Settings、Agents、Models、Tools & MCPs 等内容。

**已验证**：Cursor **3.11.13**（commit `3f21b08f0b436a07be29fbfe00b304fa15553350`）/ macOS ARM64。

## 支持矩阵

| 平台 | 入口路径示例 | 状态 |
|------|----------------|------|
| macOS ARM64 | `/Applications/Cursor.app`、`~/Applications/Cursor.app`、`Cursor.app/Contents`、`.../Resources/app` | 已在 3.11.13 验证 |
| Windows | `%LocalAppData%\Programs\cursor`、`C:\Program Files\cursor`、`resources\app` | 路径兼容保留 |
| Linux | `/usr/share/cursor`、`/opt/Cursor`、`/opt/cursor` | 路径兼容保留 |

主要职责是翻译 **Cursor 自有 Settings / Agents / Models / Tools & MCPs** 等页面，**不**替换官方 VS Code 语言包，也**不**大面积重写 VS Code Settings。

## 主要特性

- **Cursor 3.11 Settings 运行时汉化**：基于实测稳定类名（如 `cursor-settings-sidebar-cell-label`），覆盖侧栏与内容区。
- **Solid/React 重渲染容忍**：文本节点状态用 WeakMap 跟踪；框架写回英文后会再次翻译，并忽略自身写入，避免死循环。
- **属性翻译**：`title` / `aria-label` / `placeholder` / `aria-placeholder` / `aria-description`。
- **上下文保护**：模型名、Provider、Auto/High/Low 等在模型选择器中不译；代码、路径、用户输入、Chat/Agent 输出、VS Code Settings 跳过。
- **事务式安装**：版本化 manifest + 原子写入；任一步失败整单回滚。
- **只读诊断**：`--check` / `--status` / `--dry-run` 不写任何目标文件。
- **共存友好**：不删除 `@cometix/ccursor`、Cursor++ BYOK、cursor-always-local 等外部 marker / `backup-*` 文件。
- **可恢复**：restore 只撤销本工具改动，并校验 Cursor version/commit，拒绝用旧版本备份错误恢复。

## 环境要求

- Python 3
- 本地已安装 Cursor，并对安装目录可写
- 应用/恢复前请**完全退出 Cursor**
- 项目仅使用 Python 标准库；运行时 DOM 测试可选 Node 22+ 与 `jsdom@26.1.0`

## 快速使用

```bash
# 预检（只读）
python3 CursorTranslate.py --check
python3 CursorTranslate.py --status
python3 CursorTranslate.py --dry-run

# 应用汉化（会写入 Cursor 安装目录）
python3 CursorTranslate.py --apply

# 恢复本工具改动
python3 CursorTranslate.py --restore
```

指定安装路径：

```bash
python3 CursorTranslate.py --apply --cursorDir="/Applications/Cursor.app"
python3 CursorTranslate.py --apply --cursorDir="/Applications/Cursor.app/Contents/Resources/app"
python3 CursorTranslate.py --apply --cursorDir="D:\Tools\cursor"
```

## CLI 说明

| 命令 | 行为 |
|------|------|
| `--check` | 报告 version/commit、解析路径、注入锚点、checksum key、marker、冲突、计划写入；**零写入** |
| `--status` | 报告安装状态：`not-installed` / `installed` / `drifted` / `needs-recovery` / `legacy-installation` / `stale-after-upgrade` |
| `--dry-run` | 等同 check + 打印精确 PatchPlan（前后哈希、写入顺序） |
| `--apply` | 预检通过后事务式写入 |
| `--restore` | 按活动 manifest 恢复；版本不匹配则拒绝 |
| `--extract-source-strings` | 只读提取候选词条，**不**自动写入词典 |
| `--cleanup-legacy` | 清理早期语言包残留（本工具标记） |

退出码：`0` 正常，`2` 布局/冲突不兼容，`3` Cursor 仍在运行，`4` 需恢复/陈旧状态，`1` 其他错误。

## 备份位置

备份在 Cursor.app **之外**的用户数据目录，带 manifest：

- macOS: `~/Library/Application Support/cursor-v3-chinese-translate/backups/`
- Windows: `%APPDATA%\cursor-v3-chinese-translate\backups\`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/cursor-v3-chinese-translate/backups/`

每个 manifest 记录：tool/version、manifest id、Cursor version/commit、相对路径、原始/应用后 SHA-256、可逆片段描述。

**升级 Cursor 后**：旧 manifest 属于上一 version/commit，`--restore` 会拒绝错误恢复。请用官方 DMG 重装或在匹配版本副本上恢复，再对新版本重新 `--apply`。

## 词典

文件：`cursor_translate_dic.txt`

```text
"Settings" => "设置"
"Git & PRs" => "Git 与 PR"

# [Cursor 3.11 Settings Navigation]
"Browser & Network" => "浏览器与网络"
```

- 支持 `#` / `//` 注释与分组
- 空行忽略
- 重复键、冲突翻译、空键值会在加载时失败
- **不要**把 `--extract-source-strings` 的两千多条候选整表导入

## 修改范围

可能修改：

- `out/vs/code/electron-sandbox/workbench/workbench.html`
- `out/vs/code/electron-sandbox/workbench/cursor_hanhua.js`（生成）
- `product.json`（仅 workbench.html checksum）
- `out/main.js` / `out/nls.messages.json`（仅白名单原生菜单字面量，且要求唯一匹配）

**只读参考**：`workbench.desktop.main.js`（提取候选 / 兼容检查，不写入）。

## 与其他补丁工具共存

本机可能同时存在：

- `@cometix/ccursor`
- Cursor++ BYOK
- cursor-always-local
- renderer hooks / product.json checksum patch

本工具：

- 使用独立 marker（含 tool name / version / manifest id）
- **不删除** 外部 `.bak` / `backup-*`
- 发现锚点重叠或不可逆冲突时默认停止并提示
- restore 只移除本工具注入与已记录改动

## Apple 代码签名说明（重要）

修改 `Cursor.app` 内资源会使 Apple sealed-resource 验证失效。

- `codesign --verify --deep --strict` **可能失败**
- 更新 `product.json` checksum **只**解决 Cursor 自身资源校验，**不能**恢复 Apple Developer ID 签名
- Gatekeeper 是否接受需单独验证；机器级安全策略下的结果不能当作“本工具已修复签名”
- 请保留官方 DMG 作为灾难回退
- **不建议**关闭 SIP
- **不建议**删除 `com.apple.macl`
- **不建议** `chmod -R 777`
- 本脚本**不会**、也**不能**重新生成 Cursor 官方签名

## 安全边界

- 默认纯汉化模式：**不读取** Cursor access token、邮箱、`state.vscdb` 或认证信息
- **不访问网络**，不上传本地文件
- 不把 token 编入 `cursor_hanhua.js`
- 本次版本**不包含**用量监控 / 账户 API 功能

## 升级 Cursor 后的处理

1. 完全退出 Cursor  
2. 若需干净状态：官方 DMG 重装，或在**旧版本**上 `--restore`  
3. 对新版本执行 `--check`，确认路径与 checksum key  
4. `--apply`  
5. 启动验证 Cursor Settings / Agents 相关页面  

## 开发与测试

```bash
python3 -m py_compile CursorTranslate.py
python3 -m unittest -v
python3 -m unittest discover -s tests -v
python3 smoke_test.py
npm ci   # 或 npm install
npm test
```

对生成脚本：

```bash
node --check path/to/cursor_hanhua.js
```

## 常见问题

### Cursor Settings 仍是英文

1. 确认已完整重启 Cursor（不是只 reload 窗口）  
2. `--status` 确认 `installed`  
3. 打开 DevTools 查看是否加载 `cursor_hanhua.js`  
4. 将**准确原文**补进词典后重新 `--apply`

### 提示安装损坏

先 `--restore` 再 `--apply`。若仍异常，使用官方 DMG 重装。

### 与 ccursor 冲突

两者都改 `workbench.html` / `product.json` 时，以非重叠局部补丁共存；若 marker/锚点冲突，本工具会停止并提示，不会用整文件旧备份覆盖对方修改。

## 许可证与风险

该项目会修改 Cursor 安装目录文件，请自行评估风险并保留官方安装包备份。
