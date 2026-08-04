# -*- coding: utf-8 -*-
"""재기안 회귀 — 서식·zip 메타데이터 보존, mixed content 가드, PrvText 갱신."""
import os
import tempfile
import unittest
import zipfile

from tests.common import K, build_sample, zip_entries
from redraft import _compile_rules, _redraft_section, redraft
from validate import validate_structure


def _section(sec, replacements, mode, counts, changed=None):
    """_redraft_section 호출 헬퍼 — 치환 맵을 규칙으로 컴파일해 넘긴다."""
    return _redraft_section(sec, _compile_rules(replacements), mode, counts,
                            changed if changed is not None else [0])


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
        new = _section(sec, {"2025년": "2026년"}, "contains", counts)
        self.assertIn("<hp:fwSpace/>", new)
        self.assertIn("2026년", new)
        self.assertEqual(counts["2025년"], 1)
        # exact 모드는 mixed 노드를 건너뛴다
        counts = {"앞 2025년 뒤": 0}
        new = _section(sec, {"앞 2025년 뒤": "X"}, "exact", counts)
        self.assertIn("2025년", new)
        self.assertEqual(counts["앞 2025년 뒤"], 0)

    def test_exact_mode(self):
        sec = "<hp:t>2025년</hp:t><hp:t>계획 2025년</hp:t>"
        counts = {"2025년": 0}
        new = _section(sec, {"2025년": "2026년"}, "exact", counts)
        self.assertEqual(counts["2025년"], 1)          # 전체 일치만 치환
        self.assertIn("<hp:t>계획 2025년</hp:t>", new)  # 부분 일치는 보존


# 연쇄 오치환(도미노) 회귀 — 새 값이 다른 항목의 기존 값과 겹치는 시각 순연 매핑.
# 순차 치환이면 첫 행이 09:30~10:00을 거쳐 10:00~10:30까지 이중 이동한다.
TIMETABLE_SPEC = {
    "title": "행사 시간표 운영 계획",
    "pub_date": "2026. 7.",
    "author": "(’26.07.08., 우주수송정책과)",
    "body": [
        {"level": "title", "text": "행사 일정"},
        {"type": "table", "title": "행사 시간표",
         "headers": ["구분", "시간", "내용"],
         "rows": [["등록", "09:00~09:30", "참가자 접수"],
                  ["개회", "09:30~10:00", "개회사"],
                  ["발표1", "10:00~11:00", "주제발표"],
                  ["발표2", "11:00~12:00", "사례발표"],
                  ["오찬", "12:00~13:00", "오찬"],
                  ["토론", "13:00~14:00", "종합토론"]]},
    ],
}
SHIFT_MAP = {"09:00~09:30": "09:30~10:00", "09:30~10:00": "10:00~10:30",
             "10:00~11:00": "10:30~11:30", "11:00~12:00": "11:30~12:30",
             "12:00~13:00": "12:30~13:30", "13:00~14:00": "13:30~14:30"}
SHIFTED = ["09:30~10:00", "10:00~10:30", "10:30~11:30",
           "11:30~12:30", "12:30~13:30", "13:30~14:30"]


def _times(path):
    """산출물에서 시간표 셀(HH:MM~HH:MM)만 문서 순서대로 뽑는다."""
    return [ln.strip() for ln in K.extract_text(path).splitlines()
            if "~" in ln and ":" in ln]


class TestSimultaneousReplace(unittest.TestCase):
    """치환은 원본 기준 1회 스캔(동시 적용) — 규칙 간 연쇄가 없어야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src = os.path.join(cls.tmp.name, "timetable.hwpx")
        build_sample(cls.src, TIMETABLE_SPEC)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _shift(self, mode):
        out = os.path.join(self.tmp.name, f"shift_{mode}.hwpx")
        n, counts = redraft(self.src, dict(SHIFT_MAP), out, mode=mode)
        return out, n, counts

    def test_no_domino_contains(self):
        out, _, _ = self._shift("contains")
        self.assertEqual(_times(out), SHIFTED)

    def test_no_domino_exact(self):
        out, _, _ = self._shift("exact")
        self.assertEqual(_times(out), SHIFTED)

    def test_counts_exactly_one_per_key(self):
        for mode in ("contains", "exact"):
            with self.subTest(mode=mode):
                _, n, counts = self._shift(mode)
                self.assertEqual(counts, {k: 1 for k in SHIFT_MAP})
                self.assertEqual(n, len(SHIFT_MAP))  # <hp:t> 6개만 변경

    def test_longest_key_wins(self):
        out = os.path.join(self.tmp.name, "longest.hwpx")
        redraft(self.src, {"10:00": "AA", "10:00~11:00": "BB"}, out)
        text = K.extract_text(out)
        self.assertIn("BB", text)              # 긴 키가 통째로 매칭
        self.assertNotIn("AA~11:00", text)     # 짧은 키가 먼저 먹지 않음

    def test_structure_and_format_preserved(self):
        out, _, _ = self._shift("contains")
        self.assertEqual(validate_structure(out), [])
        sec = zip_entries(out)["Contents/section0.xml"].decode("utf-8")
        self.assertNotIn("<hp:linesegarray", sec)
        with zipfile.ZipFile(out) as z:
            first = z.infolist()[0]
        self.assertEqual(first.filename, "mimetype")
        self.assertEqual(first.compress_type, zipfile.ZIP_STORED)

    def test_mixed_content_simultaneous(self):
        # mixed content에서도 세그먼트별 동시 치환 — 태그 보존 + 연쇄 없음
        sec = ('<hp:t>09:00~09:30 <hp:fwSpace/>09:30~10:00</hp:t>')
        counts = {k: 0 for k in SHIFT_MAP}
        new = _section(sec, dict(SHIFT_MAP), "contains", counts)
        self.assertIn("<hp:fwSpace/>", new)
        self.assertIn("09:30~10:00", new)   # 첫 조각의 결과가 재치환되지 않음
        self.assertIn("10:00~10:30", new)
        self.assertEqual(counts["09:00~09:30"], 1)
        self.assertEqual(counts["09:30~10:00"], 1)

    def test_simple_replacement_unchanged(self):
        # 기존 단일 치환 동작 회귀
        out = os.path.join(self.tmp.name, "simple.hwpx")
        n, counts = redraft(self.src, {"주제발표": "기조발표"}, out)
        self.assertEqual((n, counts["주제발표"]), (1, 1))
        self.assertIn("기조발표", K.extract_text(out))


class TestReplaceGuards(unittest.TestCase):
    """안전 가드 — 빈 키 거부, 무의미 규칙 제외, 값의 정규식 특수문자 보호."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src = os.path.join(cls.tmp.name, "src.hwpx")
        build_sample(cls.src)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_empty_key_rejected(self):
        with self.assertRaises(SystemExit):
            redraft(self.src, {"": "X"}, os.path.join(self.tmp.name, "e.hwpx"))

    def test_identity_rule_skipped(self):
        # 키와 값이 같으면 치환·집계 모두 하지 않는다(본문 텍스트 불변).
        # ※ linesegarray 제거는 재기안의 정상 동작이므로 zip 엔트리는 달라질 수 있다.
        out = os.path.join(self.tmp.name, "id.hwpx")
        n, counts = redraft(self.src, {"누리호 4차": "누리호 4차"}, out)
        self.assertEqual((n, counts["누리호 4차"]), (0, 0))
        self.assertEqual(K.extract_text(self.src), K.extract_text(out))

    def test_regex_metachars_in_value_inserted_literally(self):
        out = os.path.join(self.tmp.name, "meta.hwpx")
        value = r"\1 \g<0> $& 100% (주)"
        redraft(self.src, {"누리호 4차": value}, out)
        self.assertIn(value, K.extract_text(out))

    def test_regex_metachars_in_key_matched_literally(self):
        out = os.path.join(self.tmp.name, "key.hwpx")
        n, counts = redraft(self.src, {"(’26.07.07., 발사체개발부문)": "(’26.07.08., 우주수송정책과)"}, out)
        self.assertEqual(n, 1)
        self.assertIn("우주수송정책과", K.extract_text(out))


if __name__ == "__main__":
    unittest.main()
