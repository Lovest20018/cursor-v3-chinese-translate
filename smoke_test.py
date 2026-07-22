# -*- coding: utf-8 -*-
"""
Smoke test for CursorTranslate.py
Creates a fake Cursor installation and tests apply/restore workflow
"""

import os
import sys
import tempfile
import shutil
import json
import subprocess
import hashlib
import base64

ROOT = os.path.dirname(os.path.abspath(__file__))


def create_fake_cursor_installation(base_dir):
    """创建假的 Cursor 安装目录结构"""
    resources_app = os.path.join(base_dir, "resources", "app")
    workbench_dir = os.path.join(
        resources_app, "out", "vs", "code", "electron-sandbox", "workbench"
    )
    out_dir = os.path.join(resources_app, "out")
    vs_workbench = os.path.join(resources_app, "out", "vs", "workbench")
    os.makedirs(workbench_dir, exist_ok=True)
    os.makedirs(vs_workbench, exist_ok=True)

    workbench_html_path = os.path.join(workbench_dir, "workbench.html")
    workbench_html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Cursor</title>
</head>
<body>
    <div id="workbench"></div>
</body>
</html>"""
    with open(workbench_html_path, "w", encoding="utf-8") as f:
        f.write(workbench_html_content)

    checksum = base64.b64encode(
        hashlib.sha256(workbench_html_content.encode("utf-8")).digest()
    ).decode("utf-8").rstrip("=")

    product_json_path = os.path.join(resources_app, "product.json")
    product_data = {
        "name": "Cursor",
        "nameShort": "Cursor",
        "applicationName": "cursor",
        "version": "3.11.13",
        "commit": "3f21b08f0b436a07be29fbfe00b304fa15553350",
        "checksums": {
            "vs/code/electron-sandbox/workbench/workbench.html": checksum
        },
    }
    with open(product_json_path, "w", encoding="utf-8") as f:
        json.dump(product_data, f, indent=2)

    with open(os.path.join(out_dir, "main.js"), "w", encoding="utf-8") as f:
        f.write('["Undo","Paste"]\n')
    with open(os.path.join(out_dir, "nls.messages.json"), "w", encoding="utf-8") as f:
        json.dump(["Undo", "Paste"], f)
    with open(
        os.path.join(vs_workbench, "workbench.desktop.main.js"), "w", encoding="utf-8"
    ) as f:
        f.write('label:"General"\n')

    return base_dir, product_json_path, workbench_html_path


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def run_smoke_test():
    print("=" * 60)
    print("  Smoke Test for CursorTranslate.py")
    print("=" * 60)

    # 避免本机真实 Cursor 进程干扰临时夹具安装测试
    os.environ["CURSOR_V3_TRANSLATE_SKIP_PROCESS_CHECK"] = "1"

    test_dir = tempfile.mkdtemp(prefix="cursor_test_")
    print(f"\n[测试] 创建临时目录: {test_dir}")

    try:
        cursor_dir, product_json_path, workbench_html_path = create_fake_cursor_installation(
            test_dir
        )
        print(f"[测试] 创建假 Cursor 安装: {cursor_dir}")

        with open(workbench_html_path, "r", encoding="utf-8") as f:
            original_html = f.read()
        with open(product_json_path, "r", encoding="utf-8") as f:
            original_product = f.read()
        original_html_sha = file_sha(workbench_html_path)
        original_product_sha = file_sha(product_json_path)

        # --check 只读
        print("\n[测试] 运行 --check...")
        result = subprocess.run(
            [sys.executable, "CursorTranslate.py", "--check", f"--cursorDir={cursor_dir}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
        )
        print(result.stdout)
        if file_sha(workbench_html_path) != original_html_sha:
            print("[错误] --check 修改了 workbench.html")
            return False
        print("[验证] --check 只读")

        print("\n[测试] 运行 --apply...")
        result = subprocess.run(
            [sys.executable, "CursorTranslate.py", "--apply", f"--cursorDir={cursor_dir}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
        )
        if result.returncode != 0:
            print("[错误] --apply 失败:")
            print(result.stdout)
            print(result.stderr)
            return False
        print("[成功] --apply 执行成功")

        with open(workbench_html_path, "r", encoding="utf-8") as f:
            injected_html = f.read()
        if "CURSOR_V3_CHINESE_TRANSLATE_INJECTION" not in injected_html and "CURSOR_HANHUA_INJECTION" not in injected_html:
            print("[错误] 未找到注入标记")
            return False
        if "cursor_hanhua.js" not in injected_html:
            print("[错误] 未找到脚本引用")
            return False
        print("[验证] HTML 注入成功")

        js_path = os.path.join(os.path.dirname(workbench_html_path), "cursor_hanhua.js")
        if not os.path.exists(js_path):
            print(f"[错误] JS 文件未生成: {js_path}")
            return False
        print(f"[验证] JS 文件已生成: {js_path}")

        result = subprocess.run(
            ["node", "--check", js_path], capture_output=True, text=True
        )
        if result.returncode != 0:
            print("[错误] JS 语法检查失败:")
            print(result.stderr)
            return False
        print("[验证] JS 语法正确")

        with open(product_json_path, "r", encoding="utf-8") as f:
            updated_product = f.read()
        if updated_product == original_product:
            print("[错误] product.json 未更新")
            return False
        print("[验证] product.json 已更新")

        print("\n[测试] 运行 --restore...")
        result = subprocess.run(
            [sys.executable, "CursorTranslate.py", "--restore", f"--cursorDir={cursor_dir}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
        )
        if result.returncode != 0:
            print("[错误] --restore 失败:")
            print(result.stdout)
            print(result.stderr)
            return False
        print("[成功] --restore 执行成功")

        with open(workbench_html_path, "r", encoding="utf-8") as f:
            restored_html = f.read()
        if restored_html != original_html:
            print("[错误] HTML 未正确恢复")
            print(f"原始长度: {len(original_html)}, 恢复后长度: {len(restored_html)}")
            return False
        print("[验证] HTML 已正确恢复")

        if os.path.exists(js_path):
            print("[错误] JS 文件未删除")
            return False
        print("[验证] JS 文件已删除")

        if file_sha(product_json_path) != original_product_sha:
            print("[错误] product.json 未恢复到原始 SHA-256")
            return False
        print("[验证] product.json SHA-256 已恢复")

        print("\n" + "=" * 60)
        print("  [成功] 所有 smoke test 通过！")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[错误] Smoke test 失败: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        try:
            shutil.rmtree(test_dir)
            print(f"\n[清理] 已删除临时目录: {test_dir}")
        except Exception as e:
            print(f"\n[警告] 清理临时目录失败: {e}")


if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
