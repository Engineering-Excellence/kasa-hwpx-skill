# -*- coding: utf-8 -*-
"""재기안 회귀 — 서식·zip 메타데이터 보존, mixed content 가드, PrvText 갱신."""
import os
import tempfile
import unittest
import zipfile

from tests.common import K, build_sample, zip_entries
from redraft import _redraft_section, redraft


class TestRedraft(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src = os.path.join(cls.tmp.name, "src.hwpx")
        build_sample(cls.src)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_replace_and_counts(self):
        out = os.path.join(self.tmp.name, "out.hwpx")
        n, counts = redraft(self.src, {"누리호 4차": "누리호 5차", "없는문구": "X"}, out)
        self.assertGreaterEqual(n, 1)
        self.assertGreaterEqual(counts["누리호 4차"], 1)
        self.assertEqual(counts["없는문구"], 0)  # 미적중 키 집계
        text = K.extract_text(out)
        self.assertIn("누리호 5차", text)
        self.assertNotIn("누리호 4차", text)

    def test_prvtext_refreshed(self):
        out = os.path.join(self.tmp.name, "prv.hwpx")
        redraft(self.src, {"누리호 4차": "누리호 6차"}, out)
        prv = zip_entries(out)["Preview/PrvText.txt"].decode("utf-8")
        self.assertIn("누리호 6차", prv)
        self.assertNotIn("누리호 4차", prv)

    def test_unchanged_entries_and_zipinfo_preserved(self):
        out = os.path.join(self.tmp.name, "meta.hwpx")
        redraft(self.src, {"누리호 4차": "누리호 7차"}, out)
        changed = {"Contents/section0.xml", "Preview/PrvText.txt"}
        src_e, out_e = zip_entries(self.src), zip_entries(out)
        self.assertEqual(set(src_e), set(out_e))
        for name in src_e:
            if name not in changed:
                self.assertEqual(src_e[name], out_e[name], name)
        with zipfile.ZipFile(self.src) as zs, zipfile.ZipFile(out) as zo:
            for a, b in zip(zs.infolist(), zo.infolist()):
                self.assertEqual(a.filename, b.filename)      # 순서 보존
                self.assertEqual(a.date_time, b.date_time)    # 시각 보존
                self.assertEqual(a.compress_type, b.compress_type)

    def test_linesegarray_removed(self):
        out = os.path.join(self.tmp.name, "seg.hwpx")
        redraft(self.src, {"누리호 4차": "누리호 8차"}, out)
        sec = zip_entries(out)["Contents/section0.xml"].decode("utf-8")
        self.assertNotIn("<hp:linesegarray", sec)

    def test_mixed_content_guard(self):
        # <hp:t> 안 컨트롤 태그는 보존, 텍스트 구간만 치환
        sec = '<hp:t>앞 <hp:fwSpace/>2025년 뒤</hp:t>'
        counts = {"2025년": 0}
        new = _redraft_section(sec, {"2025년": "2026년"}, "contains", counts, [0])
        self.assertIn("<hp:fwSpace/>", new)
        self.assertIn("2026년", new)
        self.assertEqual(counts["2025년"], 1)
        # exact 모드는 mixed 노드를 건너뛴다
        counts = {"앞 2025년 뒤": 0}
        new = _redraft_section(sec, {"앞 2025년 뒤": "X"}, "exact", counts, [0])
        self.assertIn("2025년", new)
        self.assertEqual(counts["앞 2025년 뒤"], 0)

    def test_exact_mode(self):
        sec = "<hp:t>2025년</hp:t><hp:t>계획 2025년</hp:t>"
        counts = {"2025년": 0}
        new = _redraft_section(sec, {"2025년": "2026년"}, "exact", counts, [0])
        self.assertEqual(counts["2025년"], 1)          # 전체 일치만 치환
        self.assertIn("<hp:t>계획 2025년</hp:t>", new)  # 부분 일치는 보존


if __name__ == "__main__":
    unittest.main()
