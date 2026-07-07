# -*- coding: utf-8 -*-
"""검증기 회귀 — 기준 양식 통과, 세로쓰기 오변환·PrvText 미반영 탐지."""
import os
import tempfile
import unittest
import zipfile

from tests.common import TEMPLATE, K, build_sample
from validate import kasa_check, validate_structure


def _rewrite_entry(src, dst, name, data):
    """zip 엔트리 하나를 바꿔 쓴 사본을 만든다(테스트용 오염 주입)."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for zi in zin.infolist():
            zout.writestr(zi, data if zi.filename == name else zin.read(zi.filename))


class TestValidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ok = os.path.join(cls.tmp.name, "ok.hwpx")
        build_sample(cls.ok)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_template_structure_passes(self):
        self.assertEqual(validate_structure(TEMPLATE), [])

    def test_template_kasa_no_warnings(self):
        # 기준 양식은 한글이 저장한 파일이라 정상 lineseg 캐시가 있음 —
        # 줄겹침 휴리스틱(생성물 대상)은 제외하고 나머지 규정 경고가 없어야 한다
        bad = [n for n in kasa_check(TEMPLATE)
               if n.startswith("[경고]") and "lineseg" not in n]
        self.assertEqual(bad, [])

    def test_vertical_misconvert_detected(self):
        parts, _ = K.read_package(self.ok)
        sec = parts["Contents/section0.xml"].decode("utf-8")
        bad = sec.replace('textDirection="HORIZONTAL"',
                          'textDirection="VERTICAL"')
        self.assertNotEqual(sec, bad)
        out = os.path.join(self.tmp.name, "vert.hwpx")
        _rewrite_entry(self.ok, out, "Contents/section0.xml", bad.encode("utf-8"))
        notes = kasa_check(out)
        self.assertTrue(any("세로쓰기" in n and n.startswith("[경고]") for n in notes),
                        notes)

    def test_stale_prvtext_detected(self):
        out = os.path.join(self.tmp.name, "stale.hwpx")
        stale = "예전 보고서 제목\r\n예전 본문 내용입니다".encode("utf-8")
        _rewrite_entry(self.ok, out, "Preview/PrvText.txt", stale)
        notes = kasa_check(out)
        self.assertTrue(any("PrvText" in n and n.startswith("[경고]") for n in notes),
                        notes)

    def test_broken_xml_detected(self):
        out = os.path.join(self.tmp.name, "broken.hwpx")
        _rewrite_entry(self.ok, out, "Contents/header.xml", b"<broken")
        self.assertTrue(any("XML" in i for i in validate_structure(out)))


if __name__ == "__main__":
    unittest.main()
