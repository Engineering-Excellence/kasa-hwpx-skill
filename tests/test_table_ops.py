# -*- coding: utf-8 -*-
"""표 구조 op 회귀 — set-cell/add-col/del-row/merge-cells, 가드, 구조 정합."""
import os
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET

from tests.common import K, SAMPLE_SPEC, build_sample, zip_entries
from hwpx_edit import (_edit_table, list_tables, op_add_col, op_del_row,
                       op_merge_cells, op_set_cell)
from validate import validate_structure

# 제목행(colSpan=3 병합)이 없는 표 → 구조 op 허용 대상
PLAIN_TABLE_SPEC = {
    "title": "표 편집 테스트",
    "body": [
        {"level": "title", "text": "개요"},
        {"type": "table", "headers": ["구분", "내용", "비고"],
         "rows": [["A", "1", "-"], ["B", "2", "-"]]},
    ],
}
T = 3  # 표지 레이아웃 표 2개 다음의 본문 표 순번(머리말 MI 표는 제외됨)


def _table_xml(path, t_idx=T):
    parts, _ = K.read_package(path)
    from hwpx_edit import _doc_tables
    name, s, e = _doc_tables(parts)[t_idx - 1]
    return parts[name].decode("utf-8")[s:e]


class TestTableOps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.plain = os.path.join(cls.tmp.name, "plain.hwpx")
        build_sample(cls.plain, PLAIN_TABLE_SPEC)   # 표: 머리행+데이터 2행, span 없음
        cls.titled = os.path.join(cls.tmp.name, "titled.hwpx")
        build_sample(cls.titled)                     # SAMPLE_SPEC: 제목행 colSpan=3

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _out(self, name):
        return os.path.join(self.tmp.name, name)

    def test_list_tables_excludes_header(self):
        parts, _ = K.read_package(self.plain)
        rows = list_tables(parts)
        self.assertEqual(len(rows), 3)  # 표지 2 + 본문 1 (MI 머리말 표 제외)
        self.assertEqual((rows[T - 1][1], rows[T - 1][2]), ("3", "3"))

    def test_set_cell_bg_and_itemcnt(self):
        out = self._out("bg.hwpx")
        _edit_table(self.plain, out,
                    lambda p: op_set_cell(p, T, 1, 0, bg="FFE699"))
        tbl = _table_xml(out)
        cell = re.search(r'<hp:tc\b(?:(?!</hp:tc>).)*'
                         r'<hp:cellAddr colAddr="0" rowAddr="1"/>'
                         r'(?:(?!</hp:tc>).)*</hp:tc>', tbl, re.S).group(0)
        bf_id = re.search(r'borderFillIDRef="(\d+)"', cell).group(1)
        hdr = zip_entries(out)["Contents/header.xml"].decode("utf-8")
        bf = re.search(rf'<hh:borderFill id="{bf_id}".*?</hh:borderFill>',
                       hdr, re.S).group(0)
        self.assertIn('faceColor="#FFE699"', bf)
        self.assertEqual(validate_structure(out), [])  # itemCnt 정합 포함

    def test_set_cell_reuses_identical_borderfill(self):
        mid, out = self._out("bf1.hwpx"), self._out("bf2.hwpx")
        _edit_table(self.plain, mid, lambda p: op_set_cell(p, T, 1, 0, bg="ABCDEF"))
        n_bf = len(re.findall(r"<hh:borderFill\b",
                              zip_entries(mid)["Contents/header.xml"].decode()))
        _edit_table(mid, out, lambda p: op_set_cell(p, T, 1, 1, bg="ABCDEF"))
        n_bf2 = len(re.findall(r"<hh:borderFill\b",
                               zip_entries(out)["Contents/header.xml"].decode()))
        self.assertEqual(n_bf, n_bf2)  # 동일 정의 재사용, 중복 생성 없음

    def test_set_cell_allowed_on_span_table(self):
        # titled의 표 #3 = 제목행 colSpan=3이 있는 본문 데이터 표
        out = self._out("span-ok.hwpx")
        msg = _edit_table(self.titled, out,
                          lambda p: op_set_cell(p, 3, 0, 0, bg="EEEEEE"))
        self.assertIn("셀(0,0)", msg)
        self.assertEqual(validate_structure(out), [])

    def test_add_col(self):
        out = self._out("addcol.hwpx")
        _edit_table(self.plain, out, lambda p: op_add_col(p, T))
        tbl = _table_xml(out)
        self.assertIn('colCnt="4"', tbl)
        hp_uri = "http://www.hancom.co.kr/hwpml/2011/paragraph"
        root = ET.fromstring(
            f'<w xmlns:hp="{hp_uri}" xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
            + tbl + "</w>")
        hp = "{" + hp_uri + "}"
        for tr in root.iter(hp + "tr"):
            addrs = [tc.find(hp + "cellAddr").get("colAddr")
                     for tc in tr.iter(hp + "tc")]
            self.assertEqual(sorted(map(int, addrs)), [0, 1, 2, 3])  # colAddr 정합
        self.assertEqual(validate_structure(out), [])

    def test_add_col_at_middle(self):
        out = self._out("addmid.hwpx")
        _edit_table(self.plain, out, lambda p: op_add_col(p, T, at=1))
        tbl = _table_xml(out)
        # 머리행: 새 1열은 빈 텍스트, 기존 '내용'은 2열로 밀림
        head_tr = re.search(r"<hp:tr\b[^>]*>.*?</hp:tr>", tbl, re.S).group(0)
        cell1 = re.search(r'<hp:tc\b(?:(?!</hp:tc>).)*colAddr="2"(?:(?!</hp:tc>).)*</hp:tc>',
                          head_tr, re.S).group(0)
        self.assertIn("내용", cell1)
        self.assertEqual(validate_structure(out), [])

    def test_del_row(self):
        out = self._out("delrow.hwpx")
        _edit_table(self.plain, out, lambda p: op_del_row(p, T, 1))  # 데이터행 A 삭제
        tbl = _table_xml(out)
        self.assertIn('rowCnt="2"', tbl)
        text = K.extract_text(out)
        self.assertNotIn("\nA\n", "\n" + text + "\n")
        rows = set(re.findall(r'rowAddr="(\d+)"', tbl))
        self.assertEqual(rows, {"0", "1"})  # rowAddr 감소 정합
        self.assertEqual(validate_structure(out), [])

    def test_merge_cells(self):
        out = self._out("merge.hwpx")
        _edit_table(self.plain, out, lambda p: op_merge_cells(p, T, 1, 0, 2, 0))
        tbl = _table_xml(out)
        anchor = re.search(r'<hp:tc\b(?:(?!</hp:tc>).)*rowAddr="1"(?:(?!</hp:tc>).)*</hp:tc>',
                           tbl, re.S).group(0)
        self.assertIn('rowSpan="2"', anchor)
        # 덮인 셀(2,0) 제거 확인
        self.assertEqual(len([1 for m in re.finditer(
            r'<hp:cellAddr colAddr="0" rowAddr="2"/>', tbl)]), 0)
        self.assertEqual(validate_structure(out), [])

    def test_structural_ops_refused_on_span_table(self):
        # SAMPLE_SPEC 표(#3)는 제목행 colSpan=3 → 구조 op 거부
        for fn in (lambda p: op_add_col(p, 3),
                   lambda p: op_del_row(p, 3, 1),
                   lambda p: op_merge_cells(p, 3, 1, 0, 1, 1)):
            with self.assertRaises(SystemExit):
                _edit_table(self.titled, self._out("refused.hwpx"), fn)

    def test_bad_coords_refused(self):
        with self.assertRaises(SystemExit):
            _edit_table(self.plain, self._out("bad1.hwpx"),
                        lambda p: op_set_cell(p, T, 9, 0, bg="000000"))
        with self.assertRaises(SystemExit):
            _edit_table(self.plain, self._out("bad2.hwpx"),
                        lambda p: op_del_row(p, T, 9))
        with self.assertRaises(SystemExit):
            _edit_table(self.plain, self._out("bad3.hwpx"),
                        lambda p: op_merge_cells(p, T, 0, 0, 0, 9))


if __name__ == "__main__":
    unittest.main()
