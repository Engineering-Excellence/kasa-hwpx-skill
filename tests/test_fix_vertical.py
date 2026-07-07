# -*- coding: utf-8 -*-
"""세로쓰기 오변환 자동보정 회귀 — 다수결 flip, 부분 세로쓰기 보호, 무변경 시 미기록."""
import os
import tempfile
import unittest
import zipfile

from tests.common import K, build_sample, zip_entries
from fix_vertical import fix_vertical
from validate import kasa_check


def _with_section(src, dst, mutate):
    """section0.xml을 mutate(str)->str로 바꾼 사본을 만든다."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for zi in zin.infolist():
            data = zin.read(zi.filename)
            if zi.filename == "Contents/section0.xml":
                data = mutate(data.decode("utf-8")).encode("utf-8")
            zout.writestr(zi, data)


class TestFixVertical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ok = os.path.join(cls.tmp.name, "ok.hwpx")
        build_sample(cls.ok)  # 표 포함 → 셀 textDirection="HORIZONTAL" 다수

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_misconvert_fixed_by_majority(self):
        bad = os.path.join(self.tmp.name, "bad.hwpx")
        _with_section(self.ok, bad, lambda s: s.replace(
            'textDirection="HORIZONTAL"', 'textDirection="VERTICAL"'))
        out = os.path.join(self.tmp.name, "fixed.hwpx")
        flipped, n_vert, n_horz = fix_vertical(bad, out)
        self.assertGreater(n_vert, 0)
        self.assertEqual(flipped, n_vert)
        sec = zip_entries(out)["Contents/section0.xml"].decode("utf-8")
        self.assertNotIn('textDirection="VERTICAL"', sec)
        # 보정 후 검증기 경고도 사라져야 한다
        self.assertFalse(any("세로쓰기" in n and n.startswith("[경고]")
                             for n in kasa_check(out)))

    def test_partial_vertical_protected(self):
        # 셀 1곳만 VERTICAL(의도된 서식 가능) → 다수결 미충족, 보정 거부
        part = os.path.join(self.tmp.name, "part.hwpx")
        _with_section(self.ok, part, lambda s: s.replace(
            'textDirection="HORIZONTAL"', 'textDirection="VERTICAL"', 1))
        out = os.path.join(self.tmp.name, "part-fixed.hwpx")
        flipped, n_vert, n_horz = fix_vertical(part, out)
        self.assertEqual(flipped, 0)
        self.assertGreater(n_horz, n_vert)
        self.assertFalse(os.path.exists(out))  # 미보정 시 파일을 쓰지 않음
        # --force면 되돌린다
        flipped, _, _ = fix_vertical(part, out, force=True)
        self.assertEqual(flipped, 1)
        self.assertNotIn('textDirection="VERTICAL"',
                         zip_entries(out)["Contents/section0.xml"].decode("utf-8"))

    def test_clean_file_untouched(self):
        out = os.path.join(self.tmp.name, "noop.hwpx")
        flipped, n_vert, _ = fix_vertical(self.ok, out)
        self.assertEqual((flipped, n_vert), (0, 0))
        self.assertFalse(os.path.exists(out))

    def test_metadata_preserved(self):
        bad = os.path.join(self.tmp.name, "bad2.hwpx")
        _with_section(self.ok, bad, lambda s: s.replace(
            'textDirection="HORIZONTAL"', 'textDirection="VERTICAL"'))
        out = os.path.join(self.tmp.name, "fixed2.hwpx")
        fix_vertical(bad, out)
        src_e, out_e = zip_entries(bad), zip_entries(out)
        for name in src_e:
            if name != "Contents/section0.xml":
                self.assertEqual(src_e[name], out_e[name], name)


if __name__ == "__main__":
    unittest.main()
