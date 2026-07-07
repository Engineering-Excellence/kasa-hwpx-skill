# -*- coding: utf-8 -*-
"""PreToolUse 가드 훅 회귀 — finalize/sample/spec 차단·통과 조건."""
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

from tests.common import ROOT, SAMPLE_SPEC, TEMPLATE, build_sample

HOOKS = os.path.join(ROOT, "kasa-hwpx", "hooks")
if HOOKS not in sys.path:
    sys.path.insert(0, HOOKS)

import finalize_guard  # noqa: E402
import sample_guard  # noqa: E402
import spec_guard  # noqa: E402
from _hook_common import is_delivery  # noqa: E402


def _evt(command, cwd="."):
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}


def _corrupt(src, dst, name, data):
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for zi in zin.infolist():
            zout.writestr(zi, data if zi.filename == name else zin.read(zi.filename))


class TestDeliveryDetection(unittest.TestCase):
    def test_delivery_commands(self):
        for cmd in ['cp a.hwpx ~/Downloads/', 'mv a.hwpx "C:/Users/u/Desktop/"',
                    'start 결과.hwpx', 'open 결과.hwpx',
                    'Copy-Item a.hwpx C:/Users/u/다운로드/']:
            self.assertTrue(is_delivery(cmd), cmd)

    def test_non_delivery_commands(self):
        for cmd in ['python3 scripts/validate.py a.hwpx --kasa',
                    'cp a.hwpx ./backup/', 'ls Downloads']:
            self.assertFalse(is_delivery(cmd), cmd)


class TestGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ok = os.path.join(cls.tmp.name, "ok.hwpx")
        build_sample(cls.ok)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # --- finalize_guard -------------------------------------------------
    def test_finalize_passes_clean_output(self):
        self.assertIsNone(finalize_guard.check(_evt(f'cp "{self.ok}" ~/Downloads/')))

    def test_finalize_blocks_broken_structure(self):
        bad = os.path.join(self.tmp.name, "broken.hwpx")
        _corrupt(self.ok, bad, "Contents/header.xml", b"<broken")
        reason = finalize_guard.check(_evt(f'cp "{bad}" ~/Downloads/'))
        self.assertIn("구조 검증 실패", reason or "")

    def test_finalize_blocks_lint_warning(self):
        import copy
        spec = copy.deepcopy(SAMPLE_SPEC)
        spec["body"].append({"level": "note", "text": "2026-07-07 점검 예정"})
        bad = os.path.join(self.tmp.name, "lint.hwpx")
        build_sample(bad, spec)
        reason = finalize_guard.check(_evt(f'start "{bad}"'))
        self.assertIn("표기법", reason or "")

    def test_finalize_ignores_non_delivery(self):
        self.assertIsNone(finalize_guard.check(
            _evt(f'python3 validate.py "{self.ok}" --kasa')))

    # --- sample_guard ---------------------------------------------------
    def test_sample_blocks_bundled_asset(self):
        reason = sample_guard.check(_evt(f'cp "{TEMPLATE}" ~/Downloads/'))
        self.assertIn("동봉 견본", reason or "")

    def test_sample_blocks_renamed_placeholder_copy(self):
        renamed = os.path.join(self.tmp.name, "최종보고서.hwpx")
        shutil.copyfile(TEMPLATE, renamed)
        reason = sample_guard.check(_evt(f'start "{renamed}"'))
        self.assertIn("placeholder", reason or "")

    def test_sample_passes_real_output(self):
        self.assertIsNone(sample_guard.check(_evt(f'cp "{self.ok}" ~/Downloads/')))

    # --- spec_guard -----------------------------------------------------
    def _spec_file(self, spec, name):
        p = os.path.join(self.tmp.name, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False)
        return p

    def test_spec_passes_complete(self):
        p = self._spec_file(SAMPLE_SPEC, "full.json")
        self.assertIsNone(spec_guard.check(
            _evt(f'python3 build_report.py --spec "{p}" --output o.hwpx')))

    def test_spec_blocks_missing_title_and_placeholder_author(self):
        spec = dict(SAMPLE_SPEC, title="", author="(’26.00.00., ○○담당관)")
        p = self._spec_file(spec, "missing.json")
        reason = spec_guard.check(
            _evt(f'python3 build_report.py --spec "{p}" --output o.hwpx'))
        self.assertIn("제목", reason or "")
        self.assertIn("작성정보", reason or "")

    def test_spec_markdown_meta_checked(self):
        md = os.path.join(self.tmp.name, "본문.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write("점검 보고\n□ 현황\n")  # @날짜/@작성 메타 없음
        reason = spec_guard.check(
            _evt(f'python3 build_report.py --markdown "{md}" --output o.hwpx'))
        self.assertIn("작성정보", reason or "")
        self.assertIn("발행시기", reason or "")

    def test_spec_markdown_complete_passes(self):
        md = os.path.join(self.tmp.name, "완전.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write("점검 보고\n@날짜: 2026. 7.\n@작성: (’26.07.07., 우주수송정책과)\n"
                    "□ 현황\n")
        self.assertIsNone(spec_guard.check(
            _evt(f'python3 build_report.py --markdown "{md}" --output o.hwpx')))

    def test_spec_ignores_other_commands(self):
        self.assertIsNone(spec_guard.check(_evt("python3 extract_text.py a.hwpx")))


if __name__ == "__main__":
    unittest.main()
