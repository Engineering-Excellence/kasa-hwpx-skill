# -*- coding: utf-8 -*-
"""office unpack→pack 왕복 회귀 — 미수정 엔트리 바이트 보존, mimetype 규칙.

워크플로우 C(unpack→편집→pack)에서 손대지 않은 엔트리가 바이트 단위로 보존되는지
잠근다(참고: Canine89/hwpxskill 'Preserve HWPX XML bytes' — 기존에는 build/redraft
경로만 테스트했다).
"""
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tests.common import ROOT, TEMPLATE, build_sample, zip_entries
from validate import validate_structure

OFFICE = os.path.join(ROOT, "kasa-hwpx", "scripts", "office")


def _run(script, *args):
    subprocess.run([sys.executable, os.path.join(OFFICE, script), *args],
                   check=True, capture_output=True)


class TestOfficeRoundtrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _roundtrip(self, src, tag):
        udir = os.path.join(self.tmp.name, f"un_{tag}")
        out = os.path.join(self.tmp.name, f"re_{tag}.hwpx")
        _run("unpack.py", src, udir)
        _run("pack.py", udir, out)
        return udir, out

    def test_template_roundtrip_bytes_identical(self):
        _, out = self._roundtrip(TEMPLATE, "tpl")
        self.assertEqual(zip_entries(TEMPLATE), zip_entries(out))
        self.assertEqual(validate_structure(out), [])

    def test_built_sample_roundtrip_bytes_identical(self):
        src = os.path.join(self.tmp.name, "sample.hwpx")
        build_sample(src)
        _, out = self._roundtrip(src, "sample")
        self.assertEqual(zip_entries(src), zip_entries(out))

    def test_mimetype_first_and_stored(self):
        _, out = self._roundtrip(TEMPLATE, "mime")
        with zipfile.ZipFile(out) as z:
            first = z.infolist()[0]
        self.assertEqual(first.filename, "mimetype")
        self.assertEqual(first.compress_type, zipfile.ZIP_STORED)

    def test_edit_one_entry_preserves_the_rest(self):
        # 워크플로우 C 시나리오: 한 엔트리만 고쳐도 나머지는 바이트 동일해야 한다
        udir, _ = self._roundtrip(TEMPLATE, "edit")
        target = os.path.join(udir, "Contents", "section0.xml")
        with open(target, encoding="utf-8") as f:
            xml = f.read()
        with open(target, "w", encoding="utf-8") as f:
            f.write(xml.replace("보고서 제목", "수정된 제목", 1))
        out = os.path.join(self.tmp.name, "edited.hwpx")
        _run("pack.py", udir, out)
        orig, edited = zip_entries(TEMPLATE), zip_entries(out)
        diff = [n for n in orig if orig[n] != edited[n]]
        self.assertEqual(diff, ["Contents/section0.xml"])


if __name__ == "__main__":
    unittest.main()
