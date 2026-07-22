# Cursor V3 中文增强翻译

面向 **Cursor 3.x** 的自定义界面汉化工具。在官方 VS Code 简体中文语言包之外，补全 Cursor 自有 **Settings、Agents、Models、Tools & MCPs、插件与动态状态** 等英文界面。

> 本仓库在社区汉化方案基础上，针对 **Cursor 3.11.13（macOS Apple Silicon）** 做了完整适配与工程化加固，可独立使用。

## 已验证版本

| 项目 | 值 |
|------|-----|
| Cursor | **3.11.13** |
| Commit | `3f21b08f0b436a07be29fbfe00b304fa15553350` |
| 平台 | macOS ARM64（Apple Silicon） |
| 路径 | `/Applications/Cursor.app` 及多种入口形式 |

Windows / Linux 路径解析保留兼容，但当前以 macOS 3.11.13 为主要验收目标。

## 功能概览

- **Cursor Settings 汉化**：侧栏与内容区（通用、智能体、模型、工具与 MCP、浏览器与网络等）
- **动态 UI 翻译**：文本节点 + `title` / `aria-label` / `placeholder` 等属性
- **Solid/React 重渲染容忍**：节点状态跟踪，框架写回英文后会再次翻译，并抑制自身写入死循环
- **上下文保护**：模型名、Provider、代码、路径、用户输入、Chat/Agent 输出、VS Code 原生设置等默认不译
- **事务式安装**：版本化备份 manifest、原子写入、失败整单回滚
- **只读诊断**：`--check` / `--status` / `--dry-run` 不修改任何文件
- **可恢复**：`--restore` 仅撤销本工具改动，并校验 Cursor 版本/commit
- **共存友好**：不删除其他补丁工具生成的 `backup-*` / marker

## 环境要求

- Python 3（仅标准库）
- 已安装 Cursor，并对安装目录可写
- **应用或恢复前请完全退出 Cursor**

可选（开发测试）：

- Node.js 22+
- `npm test`（jsdom DOM 测试）

## 快速开始

```bash
git clone https://github.com/zbsdsb/cursor-v3-chinese-translate.git
cd cursor-v3-chinese-translate

# 预检（只读）
python3 CursorTranslate.py --check

# 应用汉化
python3 CursorTranslate.py --apply

# 恢复本工具修改
python3 CursorTranslate.py --restore
```

指定安装路径：

```bash
python3 CursorTranslate.py --apply --cursorDir="/Applications/Cursor.app"
python3 CursorTranslate.py --apply --cursorDir="/Applications/Cursor.app/Contents/Resources/app"
python3 CursorTranslate.py --apply --cursorDir="~/Applications/Cursor.app"
```

Windows / Linux 示例：

```bash
python CursorTranslate.py --apply --cursorDir="%LocalAppData%\Programs\cursor"
python3 CursorTranslate.py --apply --cursorDir="/opt/Cursor"
```

## 命令说明

| 命令 | 作用 |
|------|------|
| `--check` | 报告版本、commit、路径、注入锚点、checksum、冲突与计划写入；**零写入** |
| `--status` | 安装状态：`not-installed` / `installed` / `drifted` / `needs-recovery` 等 |
| `--dry-run` | 预检 + 打印精确写入计划（前后哈希） |
| `--apply` | 事务式写入汉化 |
| `--restore` | 按活动 manifest 恢复；版本不匹配则拒绝 |
| `--extract-source-strings` | 从打包源码提取候选词条（**不会**自动写入词典） |
| `--cleanup-legacy` | 清理早期语言包残留 |

退出码：`0` 正常；`2` 布局/冲突不兼容；`3` Cursor 仍在运行；`4` 需恢复/陈旧状态；`1` 其他错误。

## 默认路径

### Cursor 安装目录

- macOS：`/Applications/Cursor.app` 或 `~/Applications/Cursor.app`
- Windows 用户级：`%LocalAppData%\Programs\cursor`
- Windows 系统级：`C:\Program Files\cursor`
- Linux：`/usr/share/cursor`、`/opt/Cursor`、`/opt/cursor`

`--cursorDir` 可指向：

- 安装根目录
- `Cursor.app`
- `Cursor.app/Contents`
- `Contents/Resources/app` / `resources/app`

### 备份目录（在 App 之外）

- macOS：`~/Library/Application Support/cursor-v3-chinese-translate/backups/`
- Windows：`%APPDATA%\cursor-v3-chinese-translate\backups\`
- Linux：`${XDG_DATA_HOME:-~/.local/share}/cursor-v3-chinese-translate/backups/`

每个 manifest 记录：工具名/版本、manifest id、Cursor version/commit、文件相对路径、原始与应用后 SHA-256。

## 词典

默认文件：`cursor_translate_dic.txt`

```text
"Settings" => "设置"
"Git & PRs" => "Git 与 PR"

# [Cursor 3.11 Settings Navigation]
"Browser & Network" => "浏览器与网络"
```

规则：

- 空行、`#` / `//` 注释忽略
- 支持分组注释
- 重复键、冲突翻译、空键值会在加载时失败
- **不要**把 `--extract-source-strings` 的全量候选直接导入词典

若仍有英文：复制界面上的**完整原文**加入词典，重新 `--apply` 并完整重启 Cursor。

## 修改范围

可能写入：

- `out/vs/code/electron-sandbox/workbench/workbench.html`
- `out/vs/code/electron-sandbox/workbench/cursor_hanhua.js`（生成）
- `product.json`（仅 workbench.html 的 checksum）
- `out/main.js` / `out/nls.messages.json`（仅白名单原生菜单字符串，且要求唯一匹配）

只读参考：`workbench.desktop.main.js`（候选提取 / 兼容检查）。

## 升级 Cursor 之后

1. 完全退出 Cursor  
2. 若旧版本曾安装本工具：在**旧版本**上 `--restore`，或直接用官方安装包重装  
3. 对新版本执行 `--check`  
4. `--apply`  
5. 启动验证 Cursor Settings / 智能体相关页面  

旧 manifest 绑定旧 version/commit，升级后 `--restore` 会拒绝错误恢复，避免用过期备份覆盖新版本文件。

## 与其他补丁工具共存

可能同时存在：

- `@cometix/ccursor`
- Cursor++ BYOK
- cursor-always-local
- 其他 renderer / checksum 补丁

本工具：

- 使用独立 marker（含工具名、版本、manifest id）
- **不删除** 外部 `.bak` / `backup-*`
- 锚点重叠或不可逆冲突时默认停止并提示
- restore 只移除本工具注入与已记录改动

## Apple 代码签名（重要）

修改 `Cursor.app` 内部资源会使 Apple sealed-resource 验证失效。

- `codesign --verify --deep --strict` **可能失败**
- 更新 `product.json` checksum **只**解决 Cursor 自身资源校验，**不能**恢复 Apple Developer ID 签名
- Gatekeeper 结果需自行验证
- 请保留官方安装包 / DMG 作为灾难回退
- **不建议**关闭 SIP
- **不建议**删除 `com.apple.macl`
- **不建议** `chmod -R 777`
- 本工具**不会**、也**不能**重新生成 Cursor 官方签名

## 安全边界

- 默认纯汉化：**不读取** Cursor 登录 token、邮箱、`state.vscdb` 或本地认证库
- **不访问网络**，不上传任何文件
- 不把 token 编入 `cursor_hanhua.js`
- 不包含用量监控 / 账户 API 功能

## 测试

```bash
python3 -m py_compile CursorTranslate.py
python3 -m unittest -v
python3 -m unittest discover -s tests -v
python3 smoke_test.py
npm ci
npm test
```

对生成脚本：

```bash
node --check path/to/cursor_hanhua.js
```

## 项目结构

```text
CursorTranslate.py          # CLI 入口
cursor_translate/           # 核心模块（路径、词典、事务、运行时）
cursor_translate_dic.txt    # 翻译词典
tests/                      # 单元测试与 DOM fixture
docs/verification/          # 验收记录（无账号/隐私数据）
```

## 致谢与渊源

- 早期社区汉化思路与词典积累来自相关开源项目贡献者
- 本仓库当前维护目标：Cursor 3.11 Settings/Agents 真实 UI 可用、可恢复、可与其他补丁共存

如上游仓库暂未合并适配改动，可直接使用本仓库的发布分支。

## 免责声明

本项目会修改 Cursor 安装目录中的文件，可能影响自动更新、完整性校验与系统签名验证。请自行评估风险，使用前备份，并保留官方安装包以便回退。与 Cursor / Anysphere 官方无隶属关系。

## License

请遵循仓库内既有许可声明；贡献代码前建议先开 Issue 讨论大范围改动。
