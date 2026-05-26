# Cursor V3 Chinese Translate

> Cursor V3 中文增强翻译脚本：通过注入前端翻译脚本补全 Cursor 自定义 UI、设置页、插件页、MCP、欢迎页等官方 VS Code 中文语言包覆盖不到的英文内容，并在设置页展示账号用量。

## 功能特性

- 翻译 Cursor 自定义界面文本，包括设置页、插件页、MCP、Agent、Composer、欢迎页等。
- 不覆盖、不替换 VS Code 官方中文语言包，避免破坏编辑器内置本地化。
- 使用 `cursor_translate_dic.txt` 维护精确翻译词典，便于继续补充遗漏项。
- 支持翻译文本节点以及 `title`、`aria-label`、`placeholder` 等属性。
- 监听 DOM 动态变化，处理弹窗、菜单、设置项等后加载内容。
- 自动读取本地 Cursor 登录信息并获取用量数据。
- 在 Cursor 设置页插入用量卡片。
- 自动备份并恢复 `workbench.html`、`product.json`。
- 自动更新 `product.json` 校验值，降低“安装损坏”提示概率。

## 当前方案

本项目当前采用“前端脚本注入 + 外部词典”的方式：

1. 读取 `cursor_translate_dic.txt` 翻译词典。
2. 生成 `cursor_hanhua.js`。
3. 将脚本引用注入 Cursor 的 `workbench.html`。
4. 运行时在页面 DOM 中匹配英文文本并替换为中文。
5. 监听后续 DOM 变化，继续翻译动态加载内容。
6. 更新 `product.json` 中对应文件的 SHA256 校验值。

这种方式适合补齐 Cursor 自定义 UI，因为很多文本不属于 VS Code 官方语言包范围。

## 项目结构

| 文件 | 说明 |
| --- | --- |
| `CursorTranslate.py` | 主脚本，负责注入、恢复、用量获取、校验值更新 |
| `cursor_translate_dic.txt` | 翻译词典文件 |
| `README.md` | 项目说明文档 |
| `.gitignore` | Git 忽略规则 |

## 环境要求

- Python 3
- 本地已安装并登录 Cursor
- 对 Cursor 安装目录具有读写权限
- 如需显示用量，网络需可访问 Cursor 用量接口

项目仅使用 Python 标准库，不依赖第三方 Python 包。

## 默认路径

### Cursor 安装目录

- Windows: `%LocalAppData%\Programs\cursor`
- Linux: `/usr/share/cursor`
- 其他系统: `/usr/share/cursor`

### Cursor 用户数据目录

- Windows: `%AppData%\Cursor`
- Linux: `~/.cursor`
- 其他系统: `~/.cursor`

如果安装路径不同，可以通过 `--cursorDir` 指定。

## 使用方法

### 查看帮助

```bash
python CursorTranslate.py
```

### 应用汉化

```bash
python CursorTranslate.py --apply
```

### 指定 Cursor 安装目录

```bash
python CursorTranslate.py --apply --cursorDir="D:\Tools\cursor"
```

### 恢复原始文件

```bash
python CursorTranslate.py --restore
```

恢复会执行：

- 还原 `workbench.html`
- 还原 `product.json`
- 删除生成的 `cursor_hanhua.js`

## Windows 示例

```powershell
python .\CursorTranslate.py --apply
```

恢复：

```powershell
python .\CursorTranslate.py --restore
```

自定义安装目录：

```powershell
python .\CursorTranslate.py --apply --cursorDir="D:\Tools\cursor"
```

## Linux 示例

```bash
python3 ./CursorTranslate.py --apply
```

恢复：

```bash
python3 ./CursorTranslate.py --restore
```

自定义安装目录：

```bash
python3 ./CursorTranslate.py --apply --cursorDir="/your/cursor/path"
```

如果 Cursor 安装在系统目录，可能需要用具备写权限的方式运行。

## 翻译词典

默认词典文件：

```text
cursor_translate_dic.txt
```

词典每行使用 `=>` 分隔原文和译文：

```text
Settings => 设置
General => 常规
Account => 账户
```

推荐使用带引号格式，便于处理空格、标点和特殊字符：

```text
"Open project" => "打开项目"
"Prevent \"Connection failed\" errors" => "防止出现“Connection failed”错误"
```

脚本会使用 JSON 规则解析带引号词条，因此 `\"` 会被正确还原为英文原文中的 `"`。

以下内容会被忽略：

- 空行
- 以 `#` 开头的行
- 以 `//` 开头的行

## 已覆盖的主要界面

当前词典重点补充：

- Cursor 设置页
- Agent / Composer 设置
- 插件 Marketplace 页面
- MCP 服务器和工具页面
- 索引、网络、钩子、自动运行相关设置
- 欢迎页按钮和最近项目区域
- 编辑器菜单中 Cursor 自定义动作

如果仍有英文，截图后把原文补进 `cursor_translate_dic.txt`，再执行：

```bash
python CursorTranslate.py --apply
```

## 备份与恢复

脚本会自动生成：

- `workbench.html.bak`
- `product.json.bak`

恢复命令：

```bash
python CursorTranslate.py --restore
```

## 更新 Cursor 后

Cursor 更新可能覆盖 `workbench.html`，需要重新执行：

```bash
python CursorTranslate.py --apply
```

## 常见问题

### 仍有部分英文没有翻译

原因通常是：

- Cursor 新版本增加了新文案
- 文本被拆成多个 DOM 节点
- 文本是动态加载的菜单、弹窗或设置项
- 原文与词典不完全一致

处理方式：把完整英文或截图中的末级标题/说明文本加入 `cursor_translate_dic.txt`，重新执行 `--apply` 并重启 Cursor。

### 带引号的词条匹配不上

当前版本已经支持带引号词条反转义。例如词典里的：

```text
"Prevent \"Connection failed\" errors" => "防止出现“Connection failed”错误"
```

会按原文 `Prevent "Connection failed" errors` 匹配。

### Cursor 提示安装损坏

脚本会更新 `product.json` 校验值。若之前手动修改过文件，可尝试：

```bash
python CursorTranslate.py --restore
python CursorTranslate.py --apply
```

### 找不到 `workbench.html`

说明 Cursor 安装目录不是默认路径，使用 `--cursorDir` 指定实际路径。

### 用量数据为空

可能原因：

- Cursor 未登录
- 本地 token 无效或已过期
- 网络无法访问 Cursor 用量接口

这种情况下汉化仍可继续生效，只是用量卡片数据可能为空。

## 安全说明

- 脚本不会上传本地数据库文件。
- 登录信息只从本地 Cursor 数据目录读取。
- 用量查询使用 Cursor 自身接口。
- 修改安装目录前会自动备份关键文件。

该项目会修改 Cursor 安装目录内文件，请自行评估风险，并建议保留备份。

## 开发检查

```bash
python -m py_compile CursorTranslate.py
```
