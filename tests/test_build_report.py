# -*- coding: utf-8 -*-
"""빌드 회귀 — 구조·KASA 규정 통과, PrvText 본문 반영, 결정성(엔트리 바이트 동일)."""
import os
import tempfile
import unittest

from tests.common import K, SAMPLE_SPEC, build_sample, zip_entries
from validate import kasa_check, validate_structure


class TestBuildReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = os.path.join(cls.tmp.name, "report.hwpx")
        build_sample(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_structure_passes(self):
        self.assertEqual(validate_structure(self.out), [])

    def test_kasa_check_no_warnings(self):
        bad = [n for n in kasa_check(self.out) if not n.startswith("[OK]")]
        self.assertEqual(bad, [])

    def test_body_text_present(self):
        text = K.extract_text(self.out)
        for expected in ["누리호 4차 발사 준비현황 보고", "□ 추진 배경",
                         "ㅇ 신뢰성 확보 및 우주수송 역량 강화", "발사 일정",
                         "2027. 3.", "참고 1", "발사체 제원"]:
            self.assertIn(expected, text)

    def test_annotations_removed(self):
        # 표지 주석런((HY헤드라인M, 30Pt) 등)은 제거되어야 한다
        text = K.extract_text(self.out)
        self.assertNotIn("HY헤드라인M", text)
        self.assertNotIn("함초롬바탕, 24Pt", text)

    def test_prvtext_reflects_body(self):
        prv = zip_entries(self.out)["Preview/PrvText.txt"].decode("utf-8")
        self.assertIn("누리호 4차 발사 준비현황 보고", prv)
        self.assertIn("□ 추진 배경", prv)
        self.assertNotIn("30Pt", prv)  # 표준양식 원문이 남으면 안 됨

    def test_no_linesegarray_in_body(self):
        sec = zip_entries(self.out)["Contents/section0.xml"].decode("utf-8")
        anchor = sec.find("□ ")
        self.assertNotEqual(anchor, -1)
        self.assertEqual(sec.count('vertpos="0"', anchor), 0)

    def test_deterministic_entries(self):
        # 같은 사양·같은 시드 → 모든 엔트리 바이트 동일 (v0.5.0 롤백 사건 회귀잠금:
        # zip 시각은 달라질 수 있으므로 컨테이너가 아닌 엔트리 내용을 비교한다)
        out2 = os.path.join(self.tmp.name, "report2.hwpx")
        build_sample(out2)
        self.assertEqual(zip_entries(self.out), zip_entries(out2))

    def test_table_row_mismatch_rejected(self):
        spec = dict(SAMPLE_SPEC)
        spec["body"] = [{"type": "table", "headers": ["a", "b"], "rows": [["1"]]}]
        out = os.path.join(self.tmp.name, "bad.hwpx")
        with self.assertRaises(ValueError):
            build_sample(out, spec)


if __name__ == "__main__":
    unittest.main()
