# -*- coding: utf-8 -*-
"""머리말·꼬리말·쪽번호 편집 회귀 — 생성/갱신/제거, 기존값 보존, 구조 무결성."""
import os
import re
import tempfile
import unittest

from tests.common import K, build_sample, zip_entries
from hwpx_edit import (remove_headerfooter, remove_pagenum, set_headerfooter,
                       set_pagenum, _edit_sections)
from validate import validate_structure


def _sec(path):
    return zip_entries(path)["Contents/section0.xml"].decode("utf-8")


class TestHwpxEdit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src = os.path.join(cls.tmp.name, "src.hwpx")
        build_sample(cls.src)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _out(self, name):
        return os.path.join(self.tmp.name, name)

    def test_set_footer_creates_slot(self):
        out = self._out("footer.hwpx")
        n = _edit_sections(self.src, out,
                           lambda s: set_headerfooter(s, "footer", "우 주 항 공 청"))
        self.assertEqual(n, 1)
        sec = _sec(out)
        m = re.search(r"<hp:footer\b.*?</hp:footer>", sec, re.S)
        self.assertIsNotNone(m)
        self.assertIn("우 주 항 공 청", m.group(0))
        self.assertIn('applyPageType="BOTH"', m.group(0))
        self.assertEqual(validate_structure(out), [])

    def test_set_footer_updates_existing(self):
        mid, out = self._out("f1.hwpx"), self._out("f2.hwpx")
        _edit_sections(self.src, mid, lambda s: set_headerfooter(s, "footer", "이전"))
        n = _edit_sections(mid, out, lambda s: set_headerfooter(s, "footer", "이후"))
        self.assertEqual(n, 1)
        sec = _sec(out)
        self.assertEqual(len(re.findall(r"<hp:footer\b", sec)), 1)  # 중복 생성 금지
        self.assertIn("이후", sec)
        self.assertNotIn("이전", sec)
        self.assertEqual(validate_structure(out), [])

    def test_set_header_preserves_mi_objects(self):
        # KASA 머리말의 MI 로고(표·이미지) 개체는 보존, 텍스트만 교체
        out = self._out("header.hwpx")
        n = _edit_sections(self.src, out,
                           lambda s: set_headerfooter(s, "header", "테스트 머리말"))
        self.assertEqual(n, 1)
        block = re.search(r"<hp:header\b.*?</hp:header>", _sec(out), re.S).group(0)
        self.assertIn("<hp:tbl", block)          # MI 표 보존
        self.assertIn("테스트 머리말", block)
        self.assertEqual(validate_structure(out), [])

    def test_remove_footer(self):
        mid, out = self._out("rf1.hwpx"), self._out("rf2.hwpx")
        _edit_sections(self.src, mid, lambda s: set_headerfooter(s, "footer", "꼬리말"))
        n = _edit_sections(mid, out, lambda s: remove_headerfooter(s, "footer"))
        self.assertEqual(n, 1)
        self.assertNotIn("<hp:footer", _sec(out))
        self.assertEqual(validate_structure(out), [])

    def test_set_pagenum_partial_update_preserves_rest(self):
        # 기준 양식엔 pos=BOTTOM_CENTER formatType=DIGIT sideChar="-" 쪽번호가 있음
        out = self._out("pn.hwpx")
        n = _edit_sections(self.src, out, lambda s: set_pagenum(s, side_char=""))
        self.assertEqual(n, 1)
        m = re.search(r"<hp:pageNum\b[^>]*/>", _sec(out)).group(0)
        self.assertIn('sideChar=""', m)
        self.assertIn('pos="BOTTOM_CENTER"', m)   # 미지정 옵션 기존값 보존
        self.assertIn('formatType="DIGIT"', m)
        self.assertEqual(validate_structure(out), [])

    def test_pagenum_remove_then_recreate(self):
        mid, out = self._out("pn1.hwpx"), self._out("pn2.hwpx")
        n = _edit_sections(self.src, mid, lambda s: remove_pagenum(s))
        self.assertEqual(n, 1)
        self.assertNotIn("<hp:pageNum", _sec(mid))
        n = _edit_sections(mid, out, lambda s: set_pagenum(s, pos="BOTTOM_RIGHT"))
        self.assertEqual(n, 1)
        m = re.search(r"<hp:pageNum\b[^>]*/>", _sec(out)).group(0)
        self.assertIn('pos="BOTTOM_RIGHT"', m)
        self.assertEqual(validate_structure(out), [])

    def test_unchanged_entries_preserved(self):
        out = self._out("meta.hwpx")
        _edit_sections(self.src, out, lambda s: set_headerfooter(s, "footer", "F"))
        src_e, out_e = zip_entries(self.src), zip_entries(out)
        for name in src_e:
            if name != "Contents/section0.xml":
                self.assertEqual(src_e[name], out_e[name], name)


if __name__ == "__main__":
    unittest.main()
