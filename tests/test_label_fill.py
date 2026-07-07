# -*- coding: utf-8 -*-
"""라벨 기반 양식 채우기 회귀 — 라벨 탐지, 오른쪽/아래 채움, 거름망, 보존."""
import copy
import os
import tempfile
import unittest

from tests.common import SAMPLE_SPEC, K, build_sample, zip_entries
import label_fill as LF
from validate import validate_structure


def _form_spec(rows, headers=("항목", "내용")):
    spec = copy.deepcopy(SAMPLE_SPEC)
    spec["body"] = [{"level": "title", "text": "신청 정보"},
                    {"type": "table", "headers": list(headers), "rows": rows}]
    spec["appendix"] = []
    return spec


class TestLabelFill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        # 오른쪽 채움형: 라벨 | 빈 칸
        cls.right = os.path.join(cls.tmp.name, "right.hwpx")
        build_sample(cls.right, _form_spec(
            [["성명:", ""], ["소속", ""], ["기간", "6개월"]]))
        # 아래 채움형: 라벨 행 아래 빈 행
        cls.below = os.path.join(cls.tmp.name, "below.hwpx")
        build_sample(cls.below, _form_spec(
            [["성명:", "연락처:"], ["", ""]], headers=("가", "나")))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_detect_labels(self):
        parts, _ = K.read_package(self.right)
        found = {text for _, text, *_ in LF.scan(parts)}
        self.assertIn("성명:", found)
        self.assertIn("소속", found)
        self.assertNotIn("기간", found)      # 오른쪽이 채워져 있어 대상 없음
        self.assertNotIn("6개월", found)     # 값 거름망

    def test_fill_right_cell(self):
        parts, _ = K.read_package(self.right)
        filled, unmatched = LF.fill(parts, {"성명": "홍길동", "소속": "우주수송정책과"})
        self.assertEqual(len(filled), 2)
        self.assertEqual(unmatched, [])
        out = os.path.join(self.tmp.name, "filled.hwpx")
        orig = dict(K.read_package(self.right)[0])
        changed = {n: b for n, b in parts.items() if orig.get(n) != b}
        K.write_package_preserving(self.right, out, changed)
        text = K.extract_text(out)
        self.assertIn("홍길동", text)
        self.assertIn("우주수송정책과", text)
        self.assertEqual(validate_structure(out), [])

    def test_fill_below_cell_when_right_occupied(self):
        parts, _ = K.read_package(self.below)
        filled, unmatched = LF.fill(parts, {"성명": "홍길동"})
        self.assertEqual(unmatched, [])
        (_, _, rc, where), = filled
        self.assertEqual(where, "아래")

    def test_colon_and_space_insensitive_key(self):
        parts, _ = K.read_package(self.right)
        filled, unmatched = LF.fill(parts, {"성 명:": "홍길동"})
        self.assertEqual(len(filled), 1, unmatched)

    def test_unknown_label_reported(self):
        parts, _ = K.read_package(self.right)
        filled, unmatched = LF.fill(parts, {"주소": "사천시"})
        self.assertEqual(filled, [])
        self.assertEqual(unmatched[0][0], "주소")

    def test_occupied_target_not_overwritten(self):
        parts, _ = K.read_package(self.right)
        filled, unmatched = LF.fill(parts, {"기간": "12개월"})
        self.assertEqual(filled, [])
        self.assertIn("빈 셀 없음", unmatched[0][1])
        sec = parts["Contents/section0.xml"].decode("utf-8")
        self.assertIn("6개월", sec)          # 기존 값 그대로
        self.assertNotIn("12개월", sec)      # 덮어쓰지 않음

    def test_untouched_entries_preserved(self):
        parts, _ = K.read_package(self.right)
        LF.fill(parts, {"성명": "홍길동"})
        orig = dict(K.read_package(self.right)[0])
        changed = {n for n, b in parts.items() if orig.get(n) != b}
        self.assertLessEqual(changed,
                             {"Contents/section0.xml", "Preview/PrvText.txt"})


if __name__ == "__main__":
    unittest.main()
