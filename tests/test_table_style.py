# -*- coding: utf-8 -*-
"""표 스타일 회귀 — 숫자/텍스트 셀 정렬 분리, 데이터 행 높이 동일화."""
import copy
import os
import re
import tempfile
import unittest

from tests.common import SAMPLE_SPEC, K, build_sample, zip_entries
from validate import validate_structure


def _spec_with_table(rows, headers=("구분", "금액(천원)", "비고"), title="산출 내역"):
    spec = copy.deepcopy(SAMPLE_SPEC)
    spec["body"] = [{"level": "title", "text": "산출내역"},
                    {"type": "table", "title": title,
                     "headers": list(headers), "rows": rows}]
    spec["appendix"] = []
    return spec


# 국내여비 증액 보고서 사례(비고 텍스트가 셀 폭을 넘어 2줄로 접힘)
WRAP_ROWS = [["전년도 집행액", "116,818", "국내여비 전액 집행 실적"],
             ["금년 예산액", "88,000", "—"],
             ["증액 요청액(부족분)", "28,818", "전년 집행액 − 금년 예산"]]
SHORT_ROWS = [["조립", "2026. 10.", "-"], ["발사", "2027. 3.", "예정"]]


def _tbl_cells(path, needle):
    """needle 텍스트가 든 표의 [(row, col, height, paraPr, text)]."""
    sec = zip_entries(path)["Contents/section0.xml"].decode("utf-8")
    tbl_s = sec.rfind("<hp:tbl", 0, sec.find(needle))
    tbl = sec[tbl_s:sec.find("</hp:tbl>", tbl_s)]
    out = []
    for m in re.finditer(r"<hp:tc\b.*?</hp:tc>", tbl, re.S):
        tc = m.group(0)
        col, row = re.search(r'colAddr="(\d+)" rowAddr="(\d+)"', tc).groups()
        h = int(re.search(r'<hp:cellSz width="\d+" height="(\d+)"', tc).group(1))
        pp = re.search(r'paraPrIDRef="(\d+)"', tc).group(1)
        txt = "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", tc))
        out.append((int(row), int(col), h, pp, txt))
    return out


class TestTableStyle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.wrap = os.path.join(cls.tmp.name, "wrap.hwpx")
        build_sample(cls.wrap, _spec_with_table(WRAP_ROWS))
        cls.short = os.path.join(cls.tmp.name, "short.hwpx")
        build_sample(cls.short, _spec_with_table(SHORT_ROWS))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_numeric_cells_right_aligned(self):
        cells = {t: pp for _, _, _, pp, t in _tbl_cells(self.wrap, "116,818")}
        for num in ("116,818", "88,000", "28,818"):
            self.assertEqual(cells[num], "28", num)  # paraPr 28 = RIGHT

    def test_text_cells_default_aligned(self):
        cells = {t: pp for _, _, _, pp, t in _tbl_cells(self.wrap, "116,818")}
        for txt in ("국내여비 전액 집행 실적", "—", "전년 집행액 − 금년 예산"):
            self.assertEqual(cells[txt], "29", txt)  # paraPr 29 = JUSTIFY(기본)

    def test_label_column_unchanged(self):
        cells = {t: pp for _, _, _, pp, t in _tbl_cells(self.wrap, "116,818")}
        self.assertEqual(cells["전년도 집행액"], "27")  # 구분 열은 CENTER 유지

    def test_justify_parapr_injected(self):
        hdr = zip_entries(self.wrap)["Contents/header.xml"].decode("utf-8")
        m = re.search(r'<hh:paraPr id="29".*?</hh:paraPr>', hdr, re.S)
        self.assertIsNotNone(m)
        self.assertIn('horizontal="JUSTIFY"', m.group(0))
        self.assertEqual(validate_structure(self.wrap), [])  # itemCnt 정합 포함

    def test_wrap_table_data_rows_uniform_and_taller(self):
        cells = _tbl_cells(self.wrap, "116,818")
        data_h = {h for row, _, h, _, _ in cells if row >= 2}   # r0 제목, r1 머리행
        self.assertEqual(len(data_h), 1, data_h)                # 전 행 동일
        self.assertGreater(data_h.pop(), 282)                   # 2줄 기준으로 상향
        head_h = {h for row, _, h, _, _ in cells if row == 1}
        self.assertEqual(head_h, {282})                         # 머리행은 유지

    def test_short_table_heights_unchanged(self):
        cells = _tbl_cells(self.short, "2026. 10.")
        self.assertEqual({h for row, _, h, _, _ in cells if row >= 2}, {282})

    def test_content_identical_after_style_change(self):
        text = K.extract_text(self.wrap)
        for t in ("국내여비 전액 집행 실적", "전년 집행액 − 금년 예산", "116,818"):
            self.assertIn(t, text)


if __name__ == "__main__":
    unittest.main()
