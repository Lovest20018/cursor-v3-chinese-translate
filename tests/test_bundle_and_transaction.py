# -*- coding: utf-8 -*-
"""Cursor 3.11 macOS 路径、事务、共存与回滚测试。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cursor_translate.bundle import (  # noqa: E402
    preflight,
    resolve_cursor_app_path,
    sha256_file,
)
from cursor_translate.constants import (  # noqa: E402
    CHECKSUM_KEY,
    EXIT_CURSOR_RUNNING,
    EXIT_INCOMPATIBLE,
    EXIT_NEEDS_RECOVERY,
    EXIT_OK,
    INJECTION_MARKER,
    TOOL_NAME,
    TRANSLATION_JS_NAME,
)
from cursor_translate.dictionary import (  # noqa: E402
    DictionaryError,
    parse_dictionary_text,
    parse_translation_entry,
)
from cursor_translate.runtime import generate_js_code  # noqa: E402
from cursor_translate.transaction import (  # noqa: E402
    InstallTransaction,
    TransactionError,
    restore_from_manifest,
    status_report,
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create_fake_cursor(
    base_dir: str,
    *,
    version: str = "3.11.13",
    commit: str = "3f21b08f0b436a07be29fbfe00b304fa15553350",
    with_checksum: bool = True,
    macos_bundle: bool = False,
    foreign_html_marker: str = "",
    foreign_product_keys: bool = False,
) -> str:
    if macos_bundle:
        resources_app = os.path.join(
            base_dir, "Cursor.app", "Contents", "Resources", "app"
        )
        root = os.path.join(base_dir, "Cursor.app")
    else:
        resources_app = os.path.join(base_dir, "resources", "app")
        root = base_dir

    workbench_dir = os.path.join(
        resources_app, "out", "vs", "code", "electron-sandbox", "workbench"
    )
    out_dir = os.path.join(resources_app, "out")
    vs_workbench = os.path.join(resources_app, "out", "vs", "workbench")
    os.makedirs(workbench_dir, exist_ok=True)
    os.makedirs(vs_workbench, exist_ok=True)

    html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Cursor</title></head>
<body>
<div id="workbench"></div>
</body>
</html>"""
    if foreign_html_marker:
        html = html.replace(
            "</html>",
            f"\n\t<!-- {foreign_html_marker} -->\n\t<script src=\"./foreign.js\"></script>\n</html>",
        )

    workbench_html = os.path.join(workbench_dir, "workbench.html")
    with open(workbench_html, "w", encoding="utf-8") as handle:
        handle.write(html)

    checksum = ""
    if with_checksum:
        digest = hashlib.sha256(html.encode("utf-8")).digest()
        import base64

        checksum = base64.b64encode(digest).decode("utf-8").rstrip("=")

    product = {
        "name": "Cursor",
        "nameShort": "Cursor",
        "applicationName": "cursor",
        "version": version,
        "commit": commit,
        "checksums": {},
    }
    if with_checksum:
        product["checksums"][CHECKSUM_KEY] = checksum
    if foreign_product_keys:
        product["cursorppByok"] = {"enabled": True}
        product["checksums"]["custom.foreign"] = "abc"

    with open(os.path.join(resources_app, "product.json"), "w", encoding="utf-8") as handle:
        json.dump(product, handle, indent=2)

    with open(os.path.join(out_dir, "main.js"), "w", encoding="utf-8") as handle:
        handle.write('menuLabels=["Undo","Redo","Cut","Copy","Paste","Select All"];\n')
    with open(os.path.join(out_dir, "nls.messages.json"), "w", encoding="utf-8") as handle:
        json.dump(["Undo", "Paste", "Select All"], handle)
    with open(
        os.path.join(vs_workbench, "workbench.desktop.main.js"),
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write('const labels={general:"General",models:"Models"};\n')

    # foreign backups
    if foreign_html_marker:
        with open(workbench_html + ".backup-byok-katex-test", "w", encoding="utf-8") as handle:
            handle.write("foreign-backup")
        with open(
            os.path.join(resources_app, "product.json.backup-byok-inject-test"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write("{}")

    return root if macos_bundle else base_dir


class TestPathResolution(unittest.TestCase):
    def test_macos_app_contents_and_resources_app_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_fake_cursor(tmp, macos_bundle=True)
            app = os.path.join(tmp, "Cursor.app")
            contents = os.path.join(app, "Contents")
            resources_app = os.path.join(contents, "Resources", "app")

            self.assertEqual(resolve_cursor_app_path(app), resources_app)
            self.assertEqual(resolve_cursor_app_path(contents), resources_app)
            self.assertEqual(resolve_cursor_app_path(resources_app), resources_app)

            report = preflight(app)
            self.assertEqual(report.version, "3.11.13")
            self.assertEqual(
                report.commit, "3f21b08f0b436a07be29fbfe00b304fa15553350"
            )
            self.assertTrue(report.checksum_present)
            self.assertTrue(report.injection_anchor_valid)


class TestDictionary(unittest.TestCase):
    def test_parse_nested_quotes_and_arrow(self):
        source, translated = parse_translation_entry(
            '"Reset "Don\'t Ask Again" Dialogs" => "重置「不再询问」对话框"', 1
        )
        self.assertIn("Don't Ask Again", source)
        self.assertIn("不再询问", translated)

        source, translated = parse_translation_entry('"A => B" => "甲=>乙"', 2)
        self.assertEqual(source, "A => B")
        self.assertEqual(translated, "甲=>乙")

    def test_duplicate_and_conflict_detection(self):
        with self.assertRaises(DictionaryError):
            parse_dictionary_text('"Hello" => "你好"\n"Hello" => "你好"\n')
        with self.assertRaises(DictionaryError):
            parse_dictionary_text('"Hello" => "你好"\n"Hello" => "您好"\n')

    def test_repo_dictionary_loads(self):
        path = ROOT / "cursor_translate_dic.txt"
        payload = parse_dictionary_text(path.read_text(encoding="utf-8"))
        self.assertGreater(len(payload.entries), 1500)
        self.assertIn("General", payload.entries)
        self.assertIn("Git & PRs", payload.entries)
        self.assertIn("Browser & Network", payload.entries)
        self.assertIn("Menu Bar Icon", payload.entries)


class TestTransaction(unittest.TestCase):
    def setUp(self):
        os.environ["CURSOR_V3_TRANSLATE_SKIP_PROCESS_CHECK"] = "1"
        self.tmp = tempfile.mkdtemp(prefix="cursor-v3-test-")
        self.backup_root = os.path.join(self.tmp, "backups")
        self.cursor_root = create_fake_cursor(os.path.join(self.tmp, "cursor"))
        self.dic = parse_dictionary_text(
            "\n".join(
                [
                    '"General" => "通用"',
                    '"Agents" => "智能体"',
                    '"Undo" => "撤销"',
                    '"Paste" => "粘贴"',
                    '"Select All" => "全选"',
                ]
            )
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _report(self, **kwargs):
        return preflight(self.cursor_root, require_not_running=False, for_apply=True)

    def test_missing_checksum_zero_writes(self):
        shutil.rmtree(self.cursor_root)
        self.cursor_root = create_fake_cursor(
            os.path.join(self.tmp, "cursor2"), with_checksum=False
        )
        report = preflight(self.cursor_root, for_apply=True)
        self.assertFalse(report.checksum_present)
        paths = report.paths
        before = sha256_file(paths.workbench_html)
        tx = InstallTransaction(report, self.dic, backup_root=self.backup_root)
        with self.assertRaises(TransactionError) as ctx:
            tx.apply()
        self.assertEqual(ctx.exception.exit_code, EXIT_INCOMPATIBLE)
        self.assertEqual(sha256_file(paths.workbench_html), before)
        self.assertFalse(os.path.exists(paths.translation_js))

    def test_apply_restore_idempotent_hashes(self):
        report = self._report()
        paths = report.paths
        before = {
            "html": sha256_file(paths.workbench_html),
            "product": sha256_file(paths.product_json),
            "main": sha256_file(paths.main_js),
            "nls": sha256_file(paths.nls_messages),
        }
        with mock.patch(
            "cursor_translate.transaction.preflight",
            return_value=report,
        ):
            plan = InstallTransaction(
                report, self.dic, backup_root=self.backup_root
            ).apply()
        self.assertTrue(os.path.isfile(paths.translation_js))
        html = open(paths.workbench_html, encoding="utf-8").read()
        self.assertIn(INJECTION_MARKER, html)
        self.assertIn(TOOL_NAME, html)
        self.assertIn(plan.manifest_id, html)

        # node --check
        completed = subprocess.run(
            ["node", "--check", paths.translation_js],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

        # second apply should work (idempotent re-apply)
        report2 = preflight(self.cursor_root, for_apply=True)
        with mock.patch(
            "cursor_translate.transaction.preflight",
            return_value=report2,
        ):
            InstallTransaction(report2, self.dic, backup_root=self.backup_root).apply()

        report3 = preflight(self.cursor_root, for_apply=False)
        with mock.patch(
            "cursor_translate.bundle.is_cursor_process_running",
            return_value=(False, ()),
        ):
            restore_from_manifest(report3, backup_root=self.backup_root)

        self.assertEqual(sha256_file(paths.workbench_html), before["html"])
        self.assertEqual(sha256_file(paths.product_json), before["product"])
        self.assertEqual(sha256_file(paths.main_js), before["main"])
        self.assertEqual(sha256_file(paths.nls_messages), before["nls"])
        self.assertFalse(os.path.exists(paths.translation_js))

    def test_partial_failure_rolls_back(self):
        report = self._report()
        paths = report.paths
        before_html = sha256_file(paths.workbench_html)
        before_product = sha256_file(paths.product_json)

        tx = InstallTransaction(report, self.dic, backup_root=self.backup_root)
        plan = tx.build_plan()

        real_atomic = __import__(
            "cursor_translate.transaction", fromlist=["atomic_write_text"]
        ).atomic_write_text
        calls = {"n": 0}

        def flaky_write(path, text):
            calls["n"] += 1
            # 让 product.json 写入失败
            if path.endswith("product.json") and calls["n"] >= 3:
                raise IOError("simulated failure")
            return real_atomic(path, text)

        with mock.patch(
            "cursor_translate.transaction.atomic_write_text", side_effect=flaky_write
        ), mock.patch(
            "cursor_translate.transaction.preflight", return_value=report
        ):
            with self.assertRaises(TransactionError):
                tx.apply()

        self.assertEqual(sha256_file(paths.workbench_html), before_html)
        self.assertEqual(sha256_file(paths.product_json), before_product)
        self.assertFalse(os.path.exists(paths.translation_js))

    def test_stale_backup_version_rejected(self):
        report = self._report()
        with mock.patch(
            "cursor_translate.transaction.preflight", return_value=report
        ):
            InstallTransaction(report, self.dic, backup_root=self.backup_root).apply()

        # 模拟升级后 version/commit 变化
        product_path = report.paths.product_json
        product = json.loads(open(product_path, encoding="utf-8").read())
        product["version"] = "3.12.0"
        product["commit"] = "deadbeef"
        open(product_path, "w", encoding="utf-8").write(json.dumps(product))

        report2 = preflight(self.cursor_root, for_apply=False)
        with self.assertRaises(TransactionError) as ctx:
            restore_from_manifest(report2, backup_root=self.backup_root)
        self.assertEqual(ctx.exception.exit_code, EXIT_NEEDS_RECOVERY)

    def test_running_cursor_blocks_apply(self):
        report = self._report()
        report.cursor_running = True
        tx = InstallTransaction(report, self.dic, backup_root=self.backup_root)
        with self.assertRaises(TransactionError) as ctx:
            tx.apply()
        self.assertEqual(ctx.exception.exit_code, EXIT_CURSOR_RUNNING)

    def test_coexistence_preserves_foreign_backups_and_markers(self):
        shutil.rmtree(self.cursor_root)
        self.cursor_root = create_fake_cursor(
            os.path.join(self.tmp, "cursor3"),
            foreign_html_marker="COMETIX_CCURSOR_INJECTION",
            foreign_product_keys=True,
        )
        report = preflight(self.cursor_root, for_apply=True)
        paths = report.paths
        foreign_bak = paths.workbench_html + ".backup-byok-katex-test"
        foreign_product_bak = os.path.join(
            paths.resources_app, "product.json.backup-byok-inject-test"
        )
        foreign_html_before = open(paths.workbench_html, encoding="utf-8").read()
        foreign_bak_sha = sha256_file(foreign_bak)
        foreign_product_bak_sha = sha256_file(foreign_product_bak)
        product_before = open(paths.product_json, encoding="utf-8").read()
        self.assertIn("cursorppByok", product_before)

        with mock.patch(
            "cursor_translate.transaction.preflight", return_value=report
        ):
            InstallTransaction(report, self.dic, backup_root=self.backup_root).apply()

        html = open(paths.workbench_html, encoding="utf-8").read()
        self.assertIn("COMETIX_CCURSOR_INJECTION", html)
        self.assertIn(INJECTION_MARKER, html)
        self.assertEqual(sha256_file(foreign_bak), foreign_bak_sha)
        self.assertEqual(sha256_file(foreign_product_bak), foreign_product_bak_sha)
        product_after = open(paths.product_json, encoding="utf-8").read()
        self.assertIn("cursorppByok", product_after)

        report2 = preflight(self.cursor_root, for_apply=False)
        with mock.patch(
            "cursor_translate.bundle.is_cursor_process_running",
            return_value=(False, ()),
        ):
            restore_from_manifest(report2, backup_root=self.backup_root)

        html2 = open(paths.workbench_html, encoding="utf-8").read()
        self.assertIn("COMETIX_CCURSOR_INJECTION", html2)
        self.assertNotIn(INJECTION_MARKER, html2)
        self.assertEqual(sha256_file(foreign_bak), foreign_bak_sha)
        self.assertEqual(sha256_file(foreign_product_bak), foreign_product_bak_sha)

    def test_check_is_readonly(self):
        report = preflight(self.cursor_root, for_apply=False)
        paths = report.paths
        before = {
            p: sha256_file(p)
            for p in (
                paths.workbench_html,
                paths.product_json,
                paths.main_js,
            )
        }
        # 再次 check
        preflight(self.cursor_root, for_apply=False)
        for path, digest in before.items():
            self.assertEqual(sha256_file(path), digest)
        self.assertFalse(os.path.exists(paths.translation_js))

    def test_generated_js_syntax(self):
        js = generate_js_code({"General": "通用", "Agents": "智能体"}, manifest_id="test")
        completed = subprocess.run(
            ["node", "--check"],
            input=js,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


class TestCliReadonly(unittest.TestCase):
    def test_cli_check_no_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cursor_root = create_fake_cursor(tmp)
            before = []
            for dirpath, _dirnames, filenames in os.walk(cursor_root):
                for name in filenames:
                    path = os.path.join(dirpath, name)
                    before.append((path, sha256_file(path), os.path.getmtime(path)))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "CursorTranslate.py"),
                    "--check",
                    f"--cursorDir={cursor_root}",
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            self.assertIn(completed.returncode, {0, 2, 3, 4}, completed.stdout + completed.stderr)
            after = []
            for dirpath, _dirnames, filenames in os.walk(cursor_root):
                for name in filenames:
                    path = os.path.join(dirpath, name)
                    after.append((path, sha256_file(path)))
            self.assertEqual(
                {(p, h) for p, h, _m in before},
                {(p, h) for p, h in after},
            )


if __name__ == "__main__":
    unittest.main()
