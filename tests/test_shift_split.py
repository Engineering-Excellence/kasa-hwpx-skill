# -*- coding: utf-8 -*-
"""분리 노드 시각 탐지 회귀 — 글자 서식 경계로 쪼개진 시각을 '조용한 누락'이 아니라
'보이는 경고'로 만든다.

실제 누락 사례(참관계획, 시각 토큰 960개):
    <hp:run charPrIDRef="508"><hp:t>’26년 10월 7일, 12</hp:t></hp:run>
    <hp:run charPrIDRef="509"><hp:t>:30 예정</hp:t></hp:run>
어느 노드에도 온전한 '12:30'이 없어 순연되지 않았고 드라이런 목록에도 뜨지 않았다.
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

from tests.common import K, build_sample
import shift_time as S
from redraft import redraft

SEC0 = "Contents/section0.xml"
MARK = "@@SPLIT1@@"
MARK2 = "@@SPLIT2@@"
_RUN_RE = re.compile(r"<hp:run\b[^>]*>")
_P_RE = re.compile(r"<hp:p\b[^>]*>")

SPLIT_SPEC = {
    "title": "누리호 발사 참관 계획",
    "pub_date": "2026. 7.",
    "author": "(’26.07.07., 발사체개발부문)",
    "body": [
        {"level": "title", "text": "행사 개요"},
        {"level": "content", "text": f"발사 예정 {MARK} 확정"},   # ← 쪼갤 자리
        {"level": "content", "text": "정상 표기 12:30~13:30 유지"},
        {"level": "content", "text": f"예비 일정 {MARK2} 참고"},  # ← 쪼갤 자리 2
    ],
}

# 표 셀 경계 픽스처 — 인접한 두 셀에 조각이 나뉘어 들어간다(결합하면 안 되는 경계)
CELL_SPEC = {
    "title": "누리호 발사 참관 계획",
    "pub_date": "2026. 7.",
    "author": "(’26.07.07., 발사체개발부문)",
    "body": [
        {"level": "title", "text": "행사 개요"},
        {"type": "table", "title": "행사 시간표", "headers": ["구분", "비고"],
         "rows": [["일시 12", ":30 예정"]]},
    ],
}


def _sec(parts):
    return parts[SEC0].decode("utf-8")


def _split_node(parts, marker, pieces, glue=None):
    """marker가 든 <hp:t> 한 개를 pieces 여러 <hp:t>로 쪼갠다.
    glue 기본값은 런 경계(</hp:run><hp:run …>) — 실제 사고와 같은 모양이다."""
    sec = _sec(parts)
    m = re.search(r"<hp:t(?:\s[^>]*)?>[^<]*%s[^<]*</hp:t>" % re.escape(marker), sec)
    assert m, f"픽스처에서 {marker}를 찾지 못했습니다"
    if glue is None:
        glue = "</hp:run>" + _RUN_RE.findall(sec[:m.start()])[-1]
    body = ("</hp:t>" + glue + "<hp:t>").join(pieces)
    parts[SEC0] = (sec[:m.start()] + "<hp:t>" + body + "</hp:t>"
                   + sec[m.end():]).encode("utf-8")
    return glue


def _para_glue(parts):
    """문단 경계 접착제 — 앞 문단을 닫고 새 문단을 여는, 형태가 온전한 XML."""
    sec = _sec(parts)
    return ("</hp:run></hp:p>" + _P_RE.findall(sec)[-1]
            + _RUN_RE.findall(sec)[-1])


def _build(tmp, name, spec=SPLIT_SPEC, edit=None):
    """샘플을 만들고 XML을 직접 손봐 픽스처 파일을 쓴다. 반환: (경로, parts)."""
    src = os.path.join(tmp, "base_" + name)
    build_sample(src, spec)
    parts, _ = K.read_package(src)
    if edit:
        edit(parts)
    out = os.path.join(tmp, name)
    K.write_package_preserving(src, out, {SEC0: parts[SEC0]})
    return out, parts


def _run_cli(*argv):
    """shift_time.main()을 인자만 바꿔 호출한다. 반환: (표준출력, SystemExit 또는 None)."""
    buf = io.StringIO()
    old, sys.argv = sys.argv, ["shift_time.py"] + list(argv)
    try:
        with contextlib.redirect_stdout(buf):
            S.main()
    except SystemExit as e:
        return buf.getvalue(), e
    finally:
        sys.argv = old
    return buf.getvalue(), None


class TestDetectSplit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = cls.tmpdir.name

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    # 1. 2노드 분리 탐지 — 이번 누락 사례의 회귀 테스트
    def test_two_node_split_detected(self):
        pieces = ["’26년 10월 7일, 12", ":30 예정"]
        _, parts = _build(self.tmp, "two.hwpx",
                          edit=lambda p: _split_node(p, MARK, pieces))
        splits = S.find_split_times(parts, 90)
        self.assertEqual(len(splits), 1)
        sp = splits[0]
        self.assertEqual(sp.pieces, pieces)
        self.assertEqual(sp.times, ["12:30"])
        self.assertEqual(S._where(sp), f"section0@{sp.byte_off}")
        # 오프셋은 드라이런 '구간' 열과 같은 기준(원본 바이트) — 그 자리에 노드가 있다
        self.assertTrue(parts[SEC0][sp.byte_off:].startswith(b"<hp:t"))
        self.assertIn("’26년 10월 7일, 12", parts[SEC0][sp.byte_off:]
                      .decode("utf-8")[:60])
        # 순연 자체는 이 시각을 건드리지 못한다(그래서 경고가 필요하다)
        changes, _, _ = S.shift_document(parts, 90)
        self.assertFalse([c for c in changes if "10월 7일" in c.old])

    # 2. 3노드 분리 탐지
    def test_three_node_split_detected(self):
        pieces = ["일시 12", ":", "30 예정"]
        _, parts = _build(self.tmp, "three.hwpx",
                          edit=lambda p: _split_node(p, MARK, pieces))
        splits = S.find_split_times(parts, 90)
        self.assertEqual(len(splits), 1)
        self.assertEqual(splits[0].pieces, pieces)
        self.assertEqual(splits[0].times, ["12:30"])

    # 3. 오탐 없음 — 온전한 시각 노드만 있는 문서
    def test_no_false_positive(self):
        _, parts = _build(self.tmp, "clean.hwpx")
        self.assertEqual(S.find_split_times(parts, 90), [])

    # 4. 결합 금지 경계 — 문단·표 셀·줄바꿈을 넘어 이어붙이지 않는다
    def test_paragraph_boundary_not_joined(self):
        def edit(p):
            _split_node(p, MARK, ["일시 12", ":30 예정"], glue=_para_glue(p))
        _, parts = _build(self.tmp, "para.hwpx", edit=edit)
        self.assertIn("</hp:p>", _sec(parts))
        self.assertEqual(S.find_split_times(parts, 90), [])

    def test_table_cell_boundary_not_joined(self):
        _, parts = _build(self.tmp, "cell.hwpx", spec=CELL_SPEC)
        sec = _sec(parts)
        i, j = sec.index(">일시 12<"), sec.index(">:30 예정<")
        self.assertIn("</hp:tc>", sec[i:j])   # 두 조각 사이는 표 셀 경계다
        self.assertEqual(S.find_split_times(parts, 90), [])

    def test_line_break_not_joined(self):
        _, parts = _build(self.tmp, "br.hwpx",
                          edit=lambda p: _split_node(p, MARK, ["일시 12", ":30 예정"],
                                                     glue="<hp:lineBreak/>"))
        self.assertEqual(S.find_split_times(parts, 90), [])

    # 5. 런 경계만 있으면 결합한다(실제 사고 패턴)
    def test_run_boundary_is_joined(self):
        holder = {}

        def edit(p):
            holder["glue"] = _split_node(p, MARK, ["일시 12", ":30 예정"])
        _, parts = _build(self.tmp, "run.hwpx", edit=edit)
        self.assertRegex(holder["glue"], r'^</hp:run><hp:run [^>]*charPrIDRef="\d+"')
        self.assertEqual(len(S.find_split_times(parts, 90)), 1)

    # 6. 범위 필터 — 순연 대상이 아닌 구간은 경고하지 않는다
    def test_scope_and_exclude_filter_warnings(self):
        _, parts = _build(self.tmp, "scope.hwpx",
                          edit=lambda p: _split_node(p, MARK, ["일시 12", ":30 예정"]))
        off = S.find_split_times(parts, 90)[0].byte_off
        rng = f"range:section0:{off}-{off + 40}"
        self.assertEqual(S.find_split_times(parts, 90, excludes=[rng]), [])
        self.assertEqual(S.find_split_times(parts, 90,
                                            scopes=[f"range:section0:0-{off}"]), [])
        wide = f"range:section0:{off}-{off + 400}"   # 두 조각을 모두 담는 범위
        self.assertEqual(len(S.find_split_times(parts, 90, scopes=[wide])), 1)
        # 키워드 제외도 순연과 같은 판정을 쓴다
        self.assertEqual(S.find_split_times(parts, 90, keywords=("일시",)), [])

    def test_non_time_pairs_ignored(self):
        # 시각이 아닌 숫자쌍(24:00·비율)은 순연 대상이 아니므로 경고하지 않는다
        _, parts = _build(self.tmp, "ratio.hwpx",
                          edit=lambda p: _split_node(p, MARK, ["득표 24", ":00 기록"]))
        self.assertEqual(S.find_split_times(parts, 90), [])


class TestSplitReporting(unittest.TestCase):
    """경고 블록·신구대조표·CLI 동작."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = cls.tmpdir.name
        cls.pieces = ["’26년 10월 7일, 12", ":30 예정"]
        cls.src, cls.parts = _build(
            cls.tmp, "plan.hwpx",
            edit=lambda p: _split_node(p, MARK, ["’26년 10월 7일, 12", ":30 예정"]))
        cls.splits = S.find_split_times(cls.parts, 90)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_warning_block_shape(self):
        block = S.render_splits(self.splits)
        self.assertIn("분리 노드로 인해 순연되지 않은 시각 1건", block)
        self.assertIn(f"section0@{self.splits[0].byte_off}", block)
        self.assertIn("'’26년 10월 7일, 12' + ':30 예정'", block)
        self.assertIn("→ 12:30", block)
        self.assertIn("redraft.py", block)

    def test_report_has_split_section(self):
        report = S.render_report([], 0, 90, self.src, [], [], [],
                                 splits=self.splits)
        self.assertIn("## 순연되지 않은 분리 노드 시각", report)
        self.assertIn(f"| section0@{self.splits[0].byte_off} |", report)
        self.assertIn("12:30", report.split("## 순연되지 않은")[1])
        clean = S.render_report([], 0, 90, self.src, [], [], [])
        self.assertIn("해당 없음", clean.split("## 순연되지 않은")[1])

    def test_dry_run_and_real_run_both_warn(self):
        out = os.path.join(self.tmp, "dry_warn.hwpx")
        dry, _ = _run_cli("--input", self.src, "--shift", "+1:30",
                          "--scope", "section:0", "--dry-run")
        self.assertIn("순연되지 않은 시각 1건", dry)
        real, err = _run_cli("--input", self.src, "--output", out,
                             "--shift", "+1:30", "--scope", "section:0")
        self.assertIsNone(err)
        self.assertIn("순연되지 않은 시각 1건", real)
        self.assertTrue(os.path.exists(out))       # 기본은 경고 후 정상 진행

    # 7. --fail-on-split — 파일을 쓰지 않고 비정상 종료
    def test_fail_on_split_blocks_write(self):
        out = os.path.join(self.tmp, "never.hwpx")
        text, err = _run_cli("--input", self.src, "--output", out,
                             "--shift", "+1:30", "--scope", "section:0",
                             "--fail-on-split")
        self.assertIsNotNone(err)
        self.assertNotIn(err.code, (0, None))
        self.assertFalse(os.path.exists(out))
        self.assertIn("순연되지 않은 시각 1건", text)

    def test_fail_on_split_passes_when_clean(self):
        clean, _ = _build(self.tmp, "clean2.hwpx")
        out = os.path.join(self.tmp, "clean_out.hwpx")
        text, err = _run_cli("--input", clean, "--output", out, "--shift", "+1:30",
                             "--scope", "section:0", "--fail-on-split")
        self.assertIsNone(err)
        self.assertTrue(os.path.exists(out))
        self.assertNotIn("분리 노드", text)

    # 8. 수정 매핑 생성 → redraft.py --mode exact 적용(엔드투엔드)
    def test_fix_map_applies_via_redraft(self):
        mp = os.path.join(self.tmp, "fix.json")
        out = os.path.join(self.tmp, "shifted.hwpx")
        text, err = _run_cli("--input", self.src, "--output", out,
                             "--shift", "+1:30", "--scope", "section:0",
                             "--split-fix-map", mp)
        self.assertIsNone(err)
        self.assertIn("수정 매핑", text)
        with open(mp, encoding="utf-8") as f:
            mapping = json.load(f)
        self.assertEqual(mapping, {"’26년 10월 7일, 12": "’26년 10월 7일, 14",
                                   ":30 예정": ":00 예정"})
        fixed = os.path.join(self.tmp, "fixed.hwpx")
        n, counts = redraft(out, mapping, fixed, mode="exact")
        self.assertEqual(n, 2)
        self.assertTrue(all(c == 1 for c in counts.values()))
        lines = K.extract_text(fixed).splitlines()
        self.assertIn("’26년 10월 7일, 14", lines)   # 12:30 → 14:00 (조각 두 개로)
        self.assertIn(":00 예정", lines)
        self.assertIn("ㅇ 정상 표기 14:00~15:00 유지", lines)  # 온전한 노드는 이미 순연됨
        # 값은 고쳐졌지만 노드는 여전히 쪼개져 있다 — 경고는 서식을 통일해야 사라진다
        fixed_parts, _ = K.read_package(fixed)
        self.assertEqual(S.find_split_times(fixed_parts, 90)[0].times, ["14:00"])

    # 9. 유일성 검사 — 같은 텍스트 노드가 둘이면 매핑에서 뺀다
    def test_duplicate_node_text_excluded_from_map(self):
        def edit(p):
            _split_node(p, MARK, ["일시 12", ":30 예정"])
            _split_node(p, MARK2, ["일시 12", ":45 예정"])
        _, parts = _build(self.tmp, "dup.hwpx", edit=edit)
        splits = S.find_split_times(parts, 90)
        self.assertEqual(len(splits), 2)
        mapping, problems = S.build_fix_map(splits, parts)
        self.assertEqual(mapping, {})
        self.assertEqual(len(problems), 2)
        self.assertTrue(all("수동 확인 필요" in p and "'일시 12'" in p
                            for p in problems))

    def test_unique_pieces_make_map(self):
        _, parts = _build(self.tmp, "uniq.hwpx",
                          edit=lambda p: _split_node(p, MARK, ["집결 9", ":20 완료"]))
        splits = S.find_split_times(parts, 90)
        mapping, problems = S.build_fix_map(splits, parts)
        self.assertEqual(problems, [])
        self.assertEqual(mapping, {"집결 9": "집결 10", ":20 완료": ":50 완료"})

    def test_pad_hour_split_map(self):
        """--pad-hour면 조각 경계가 밀린다(9:20 → 09:50) — 쌍점 기준으로 되돌린다."""
        _, parts = _build(self.tmp, "pad.hwpx",
                          edit=lambda p: _split_node(p, MARK, ["집결 9", ":20 완료"]))
        splits = S.find_split_times(parts, 30, pad_hour=True)
        mapping, _ = S.build_fix_map(splits, parts)
        self.assertEqual(mapping, {"집결 9": "집결 09", ":20 완료": ":50 완료"})


if __name__ == "__main__":
    unittest.main()
