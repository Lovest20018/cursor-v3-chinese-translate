# -*- coding: utf-8 -*-
"""
CursorTranslate.py 单元测试
"""

import unittest
import tempfile
import os
import json
import shutil
from CursorTranslate import (
    APP_RELATIVE_DIR,
    MACOS_APP_RELATIVE_DIR,
    MACOS_CONTENTS_APP_RELATIVE_DIR,
    parse_translation_entry,
    resolve_cursor_app_path,
    remove_injected_script,
    update_checksum,
    cleanup_legacy_language_pack,
    INJECTION_MARKER,
    TRANSLATION_JS_NAME,
    BACKUP_SUFFIX,
)


class TestParseTranslationEntry(unittest.TestCase):
    """测试翻译词条解析"""

    def test_parse_entry_with_arrow_in_quoted_source(self):
        """测试带引号的原文中包含 => 的情况"""
        line = '"A => B" => "甲=>乙"'
        source, translated = parse_translation_entry(line, 1)
        self.assertEqual(source, "A => B")
        self.assertEqual(translated, "甲=>乙")

    def test_parse_normal_entry(self):
        """测试普通词条解析"""
        line = 'A => B => C'
        source, translated = parse_translation_entry(line, 1)
        self.assertEqual(source, "A")
        self.assertEqual(translated, "B => C")

    def test_parse_simple_entry(self):
        """测试简单词条"""
        line = 'Hello => 你好'
        source, translated = parse_translation_entry(line, 1)
        self.assertEqual(source, "Hello")
        self.assertEqual(translated, "你好")

    def test_parse_quoted_entry(self):
        """测试带引号的词条"""
        line = '"Hello World" => "你好世界"'
        source, translated = parse_translation_entry(line, 1)
        self.assertEqual(source, "Hello World")
        self.assertEqual(translated, "你好世界")

    def test_parse_entry_with_escaped_quotes(self):
        """测试带转义引号的词条"""
        line = r'"Say \"Hello\"" => "说\"你好\""'
        source, translated = parse_translation_entry(line, 1)
        self.assertEqual(source, 'Say "Hello"')
        self.assertEqual(translated, '说"你好"')


class TestRemoveInjectedScript(unittest.TestCase):
    """测试移除注入脚本"""

    def test_remove_complete_injection(self):
        """测试正常移除完整注入块"""
        html_content = f'''<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<div>Content</div>
</body>
\t{INJECTION_MARKER}
\t<script src="./{TRANSLATION_JS_NAME}"></script>
</html>'''
        result = remove_injected_script(html_content)
        self.assertNotIn(INJECTION_MARKER, result)
        self.assertNotIn(TRANSLATION_JS_NAME, result)
        self.assertIn('<div>Content</div>', result)
        self.assertIn('</html>', result)

    def test_remove_injection_preserves_other_html(self):
        """测试移除注入时不影响其他 HTML"""
        html_content = f'''<!DOCTYPE html>
<html>
<body>
<div>Before</div>
\t{INJECTION_MARKER}
\t<script src="./{TRANSLATION_JS_NAME}"></script>
<div>After</div>
</body>
</html>'''
        result = remove_injected_script(html_content)
        self.assertIn('<div>Before</div>', result)
        self.assertIn('<div>After</div>', result)
        self.assertNotIn(INJECTION_MARKER, result)

    def test_remove_injection_incomplete_marker_only(self):
        """测试只有 marker 没有完整 script 时抛出错误"""
        html_content = f'''<!DOCTYPE html>
<html>
<body>
<div>Content</div>
\t{INJECTION_MARKER}
<div>More content</div>
</body>
</html>'''
        with self.assertRaises(ValueError) as context:
            remove_injected_script(html_content)
        error_msg = str(context.exception)
        # Check for Chinese or English error message
        self.assertTrue(
            "不完整" in error_msg or "incomplete" in error_msg.lower(),
            f"Expected error about incomplete injection, got: {error_msg}"
        )

    def test_remove_injection_marker_with_wrong_script(self):
        """测试 marker 后跟错误的 script 标签时抛出错误"""
        html_content = f'''<!DOCTYPE html>
<html>
<body>
\t{INJECTION_MARKER}
\t<script src="./other_script.js"></script>
<div>Content</div>
</body>
</html>'''
        with self.assertRaises(ValueError) as context:
            remove_injected_script(html_content)
        error_msg = str(context.exception)
        # Check for Chinese or English error message
        self.assertTrue(
            "不完整" in error_msg or "incomplete" in error_msg.lower(),
            f"Expected error about incomplete injection, got: {error_msg}"
        )


class TestUpdateChecksum(unittest.TestCase):
    """测试校验和更新"""

    def setUp(self):
        """创建临时测试目录"""
        self.test_dir = tempfile.mkdtemp()
        # 创建完整的目录结构
        resources_app = os.path.join(self.test_dir, "resources", "app")
        os.makedirs(resources_app, exist_ok=True)
        self.product_json_path = os.path.join(resources_app, "product.json")

        workbench_dir = os.path.join(resources_app, "out", "vs", "code", "electron-sandbox", "workbench")
        os.makedirs(workbench_dir, exist_ok=True)
        self.workbench_html_path = os.path.join(workbench_dir, "workbench.html")

    def tearDown(self):
        """清理临时测试目录"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_update_checksum_missing_key_returns_false(self):
        """测试找不到 checksum key 时返回 False"""
        # 创建不包含 checksum key 的 product.json
        product_data = {"name": "Cursor", "version": "1.0.0"}
        with open(self.product_json_path, 'w', encoding='utf-8') as f:
            json.dump(product_data, f)

        # 创建 workbench.html
        with open(self.workbench_html_path, 'w', encoding='utf-8') as f:
            f.write("<html><body>Test</body></html>")

        # 测试 update_checksum 返回 False
        import CursorTranslate
        original_path = CursorTranslate.CURSOR_INSTALL_PATH
        try:
            CursorTranslate.CURSOR_INSTALL_PATH = self.test_dir
            result = update_checksum()
            self.assertFalse(result, "update_checksum should return False when checksum key is missing")
        finally:
            CursorTranslate.CURSOR_INSTALL_PATH = original_path

    def test_check_checksum_key_exists_returns_false_when_missing(self):
        """测试 check_checksum_key_exists 在 key 缺失时返回 False"""
        # 创建不包含 checksum key 的 product.json
        product_data = {"name": "Cursor", "version": "1.0.0"}
        with open(self.product_json_path, 'w', encoding='utf-8') as f:
            json.dump(product_data, f)

        import CursorTranslate
        original_path = CursorTranslate.CURSOR_INSTALL_PATH
        try:
            CursorTranslate.CURSOR_INSTALL_PATH = self.test_dir
            from CursorTranslate import check_checksum_key_exists
            result = check_checksum_key_exists()
            self.assertFalse(result, "check_checksum_key_exists should return False when key is missing")
        finally:
            CursorTranslate.CURSOR_INSTALL_PATH = original_path


class TestCursorPathResolution(unittest.TestCase):
    """测试跨平台 Cursor app 目录解析"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def create_product_json(self, directory_path):
        os.makedirs(directory_path, exist_ok=True)
        product_json_path = os.path.join(directory_path, "product.json")
        with open(product_json_path, 'w', encoding='utf-8') as file:
            json.dump({"name": "Cursor"}, file)
        return product_json_path

    def test_resolve_windows_linux_install_root(self):
        install_root = os.path.join(self.test_dir, "cursor")
        app_path = os.path.join(install_root, APP_RELATIVE_DIR)
        self.create_product_json(app_path)

        self.assertEqual(resolve_cursor_app_path(install_root), app_path)

    def test_resolve_direct_resources_app_path(self):
        app_path = os.path.join(self.test_dir, "resources", "app")
        self.create_product_json(app_path)

        self.assertEqual(resolve_cursor_app_path(app_path), app_path)

    def test_resolve_macos_app_bundle_path(self):
        app_bundle_path = os.path.join(self.test_dir, "Cursor.app")
        app_path = os.path.join(app_bundle_path, MACOS_APP_RELATIVE_DIR)
        self.create_product_json(app_path)

        self.assertEqual(resolve_cursor_app_path(app_bundle_path), app_path)

    def test_resolve_macos_contents_path(self):
        contents_path = os.path.join(self.test_dir, "Cursor.app", "Contents")
        app_path = os.path.join(contents_path, MACOS_CONTENTS_APP_RELATIVE_DIR)
        self.create_product_json(app_path)

        self.assertEqual(resolve_cursor_app_path(contents_path), app_path)

    def test_resolve_missing_macos_bundle_falls_back_to_bundle_app_path(self):
        app_bundle_path = os.path.join(self.test_dir, "Missing.app")
        expected_path = os.path.join(app_bundle_path, MACOS_APP_RELATIVE_DIR)

        self.assertEqual(resolve_cursor_app_path(app_bundle_path), expected_path)


class TestCleanupLegacyLanguagePack(unittest.TestCase):
    """测试旧版语言包清理"""

    def setUp(self):
        """创建临时测试目录"""
        self.test_dir = tempfile.mkdtemp()
        self.original_user_data_path = None

    def tearDown(self):
        """清理临时测试目录"""
        if self.original_user_data_path:
            import CursorTranslate
            CursorTranslate.CURSOR_USER_DATA_PATH = self.original_user_data_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cleanup_not_called_by_default_apply(self):
        """测试默认 --apply 不调用 legacy cleanup"""
        # 使用 mock 来验证 cleanup_legacy_language_pack 没有被调用
        import unittest.mock as mock
        import CursorTranslate

        with mock.patch.object(CursorTranslate, 'cleanup_legacy_language_pack') as mock_cleanup:
            with mock.patch.object(CursorTranslate, 'validate_cursor_installation'):
                with mock.patch.object(CursorTranslate, 'read_translation_dictionary', return_value={}):
                    with mock.patch.object(CursorTranslate, 'is_already_injected', return_value=False):
                        with mock.patch.object(CursorTranslate, 'create_backup'):
                            with mock.patch.object(CursorTranslate, 'write_translation_js'):
                                with mock.patch.object(CursorTranslate, 'inject_into_html'):
                                    # 模拟 --apply 参数
                                    with mock.patch('sys.argv', ['CursorTranslate.py', '--apply']):
                                        try:
                                            CursorTranslate.main()
                                        except SystemExit:
                                            pass

            # 验证 cleanup_legacy_language_pack 没有被调用
            mock_cleanup.assert_not_called()

    def test_cleanup_called_with_explicit_flag(self):
        """测试显式 --cleanup-legacy 会调用清理函数"""
        import unittest.mock as mock
        import CursorTranslate

        with mock.patch.object(CursorTranslate, 'cleanup_legacy_language_pack') as mock_cleanup:
            with mock.patch.object(CursorTranslate, 'validate_cursor_installation'):
                # 模拟 --cleanup-legacy 参数
                with mock.patch('sys.argv', ['CursorTranslate.py', '--cleanup-legacy']):
                    try:
                        CursorTranslate.main()
                    except SystemExit:
                        pass

        # 验证 cleanup_legacy_language_pack 被调用了
        mock_cleanup.assert_called_once()


if __name__ == '__main__':
    unittest.main()
