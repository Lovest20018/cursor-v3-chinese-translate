# Cursor V3 Chinese Translate

> Cursor V3 中文增强翻译脚本：通过注入前端翻译脚本，补全 Cursor 自定义 UI、Cursor 设置页、插件页、MCP、欢迎页等官方 VS Code 中文语言包覆盖不到的英文内容。

## 功能特性

- 翻译 Cursor 自定义界面文本，包括设置页、插件页、MCP、Agent、Composer、欢迎页等。
- 不覆盖、不替换 VS Code 官方中文语言包，避免破坏编辑器内置本地化。
- 使用 `cursor_translate_dic.txt` 维护精确翻译词典，便于继续补充遗漏项。
- 支持翻译文本节点以及 `title`、`aria-label`、`placeholder` 等属性。
- 监听 DOM 动态变化，处理弹窗、菜单、设置项等后加载内容。
- 自动备份并恢复 `workbench.html`、`product.json`。
- 自动更新 `product.json` 校验值，降低“安装损坏”提示概率。

## 环境要求

- Python 3
- 本地已安装 Cursor
- 对 Cursor 安装目录具有读写权限

项目仅使用 Python 标准库，不依赖第三方 Python 包。

## 默认路径

### Cursor 安装目录

- Windows 用户级安装：`%LocalAppData%\Programs\cursor`
- Windows 系统级安装：`C:\Program Files\cursor`
- macOS：`/Applications/Cursor.app` 或 `~/Applications/Cursor.app`
- Linux：`/usr/share/cursor`、`/opt/Cursor`、`/opt/cursor`
- 其他系统：`/usr/share/cursor`

如果 Cursor 安装在系统目录，可能需要管理员权限。脚本会检查实际需要写入的目录，并在权限不足时提示。

### Cursor 用户数据目录

- Windows：`%AppData%\Cursor`
- macOS：`~/Library/Application Support/Cursor`
- Linux：`~/.cursor`
- 其他系统：`~/.cursor`

如果安装路径不同，可以通过 `--cursorDir` 指定。该参数既可以指向 Cursor 安装根目录，也可以直接指向 `resources/app` 目录；macOS 下也可以指向 `Cursor.app`、`Cursor.app/Contents` 或 `Cursor.app/Contents/Resources/app`。

## 使用方法

运行 `--apply` 或 `--restore` 前，请先完全关闭 Cursor，避免文件锁定、运行时覆盖或并发写入导致文件不一致。

查看帮助：

```bash
python CursorTranslate.py
```

应用汉化：

```bash
python CursorTranslate.py --apply
```

恢复原始文件：

```bash
python CursorTranslate.py --restore
```

指定 Cursor 安装目录：

```bash
python CursorTranslate.py --apply --cursorDir="D:\Tools\cursor"
python3 ./CursorTranslate.py --apply --cursorDir="/Applications/Cursor.app"
python3 ./CursorTranslate.py --apply --cursorDir="/Applications/Cursor.app/Contents/Resources/app"
python3 ./CursorTranslate.py --apply --cursorDir="/your/cursor/path"
```

清理早期版本遗留配置：

```bash
python CursorTranslate.py --cleanup-legacy
```

该命令用于清理早期版本可能写入的 `languagepacks.json`、`cursor-local-zh-cn` 和相关缓存。它会检查文件标记，只清理确认由本工具创建的文件。

从 Cursor 源码提取候选词条：

```bash
python CursorTranslate.py --extract-source-strings --limit=200
```

该命令只打印候选结果，不修改词典，也不写入 Cursor 安装目录。候选结果需要人工确认后再补进 `cursor_translate_dic.txt`。

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

当前词典重点补充：

- Cursor 设置页
- Agent / Composer 设置
- 插件 Marketplace 页面
- MCP 服务器和工具页面
- 索引、网络、钩子、自动运行相关设置
- 欢迎页按钮和最近项目区域
- 编辑器菜单中 Cursor 自定义动作
- Agent / Chat 右键菜单和工具调用时间线

如果仍有英文，截图后把原文补进 `cursor_translate_dic.txt`，再执行：

```bash
python CursorTranslate.py --apply
```

也可以先运行候选提取命令，从 Cursor 打包源码中查找相关英文：

```bash
python CursorTranslate.py --extract-source-strings --limit=200
```

不要把提取结果全量加入词典；源码里会包含内部状态、错误码、命令 ID、快捷键、模型名和服务名。只补确认会显示在 Cursor 自定义 UI 中的文案。

## 常见问题

### 仍有部分英文没有翻译

原因通常是：

- Cursor 新版本增加了新文案
- 文本被拆成多个 DOM 节点
- 文本是动态加载的菜单、弹窗或设置项
- 原文与词典不完全一致

处理方式：优先补 Cursor 自定义 UI、Cursor 设置表体、顶部栏和 Cursor 相关菜单中的原文；不要把 VS Code 内置设置项大面积加入词典。补完后重新执行 `--apply` 并重启 Cursor。

### Cursor 更新后汉化失效

Cursor 更新可能覆盖 `workbench.html`，重新执行：

```bash
python CursorTranslate.py --apply
```

### Cursor 提示安装损坏

脚本会更新 `product.json` 校验值。若之前手动修改过文件，可尝试：

```bash
python CursorTranslate.py --restore
python CursorTranslate.py --apply
```

### 找不到 `workbench.html`

说明 Cursor 安装目录不是默认路径，使用 `--cursorDir` 指定实际路径。

## 安全说明

- 脚本不读取 Cursor 登录信息、本地 token 或本地数据库。
- 脚本不访问网络，也不会上传本地文件。
- 修改安装目录前会自动备份关键文件。

该项目会修改 Cursor 安装目录内文件，请自行评估风险，并建议保留备份。
