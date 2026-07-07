# -*- coding: utf-8 -*-
"""신구대조 회귀 — 동일 문서 무차이, 문단 수정/추가, 표 셀 단위 diff."""
import copy
import os
import tempfile
import unittest

from tests.common import SAMPLE_SPEC, build_sample
from hwpx_diff import compare


class TestHwpxDiff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old = os.path.join(cls.tmp.name, "old.hwpx")
        build_sample(cls.old)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _build(self, name, mutate):
        spec = copy.deepcopy(SAMPLE_SPEC)
        mutate(spec)
        out = os.path.join(self.tmp.name, name)
        build_sample(out, spec)
        return out

    def test_identical_documents_no_diff(self):
        same = os.path.join(self.tmp.name, "same.hwpx")
        build_sample(same)
        stats, events = compare(self.old, same)
        self.assertEqual(events, [])
        self.assertEqual(stats["added"] + stats["removed"] + stats["modified"], 0)
        self.assertGreater(stats["unchanged"], 0)

    def test_paragraph_modification_detected(self):
        def mutate(spec):
            spec["body"][1]["text"] = "신뢰성 확보 및 우주수송 역량 강화(개정)"
        new = self._build("mod.hwpx", mutate)
        stats, events = compare(self.old, new)
        self.assertEqual(stats["modified"], 1)
        self.assertEqual(stats["added"], 0)
        self.assertEqual(stats["removed"], 0)
        ev, d = events[0]
        self.assertEqual((ev, d["kind"]), ("modified", "p"))
        self.assertIn("개정", d["new"])

    def test_paragraph_addition_detected(self):
        def mutate(spec):
            spec["body"].append({"level": "note", "text": "신규 참고 항목"})
        new = self._build("add.hwpx", mutate)
        stats, events = compare(self.old, new)
        self.assertEqual(stats["added"], 1)
        self.assertEqual(stats["removed"], 0)
        self.assertTrue(any(ev == "added" and "신규 참고" in d["text"]
                            for ev, d in events), events)

    def test_paragraph_removal_detected(self):
        def mutate(spec):
            del spec["body"][3]  # note 항목 제거
        new = self._build("del.hwpx", mutate)
        stats, _ = compare(self.old, new)
        self.assertEqual(stats["removed"], 1)
        self.assertEqual(stats["added"], 0)

    def test_table_cell_diff(self):
        def mutate(spec):
            spec["body"][4]["rows"][1][1] = "2027. 6."  # 발사 일정 변경
        new = self._build("cell.hwpx", mutate)
        stats, events = compare(self.old, new)
        self.assertEqual(stats["modified"], 1)
        tbl = next(d for ev, d in events if d["kind"] == "table")
        self.assertEqual(len(tbl["cells"]), 1)
        r, c, ov, nv = tbl["cells"][0]
        self.assertEqual((ov, nv), ("2027. 3.", "2027. 6."))

    def test_table_dimension_change(self):
        def mutate(spec):
            spec["body"][4]["rows"].append(["점검", "2027. 1.", "신규"])
        new = self._build("dim.hwpx", mutate)
        _, events = compare(self.old, new)
        tbl = next(d for ev, d in events if d["kind"] == "table")
        self.assertNotEqual(tbl["dims"][0], tbl["dims"][1])
        self.assertTrue(any(nv == "점검" for _, _, _, nv in tbl["cells"]))


if __name__ == "__main__":
    unittest.main()
