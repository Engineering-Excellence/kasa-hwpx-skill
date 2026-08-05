# -*- coding: utf-8 -*-
"""시각 순연 회귀 — 자릿수·구분자 보존, 자정 넘김, 범위 한정·분리 노드 제외,
비대상 보존, 자기 검산, 구조 보존."""
import os
import re
import tempfile
import unittest

from tests.common import K, build_sample
import shift_time as S
import validate as V

# 실제 문서(참관계획)의 사고 패턴을 축약한 픽스처:
#  - 순연 대상 구간과 보존 구간(교통편)에 같은 시각 '12:30'이 동시에 존재
#  - 값('5:08-8:02')과 라벨('▪열차 이동')이 서로 다른 <hp:t>에 분리
SHIFT_SPEC = {
    "title": "누리호 발사 참관 계획",
    "pub_date": "2026. 7.",
    "author": "(’26.07.07., 발사체개발부문)",
    "body": [
        {"level": "title", "text": "행사 일정"},
        {"level": "content", "text": "집결 9:20~10:00 점검 09:20-10:00 준비 18:00∼18:05"},
        {"level": "content", "text": "심야 23:50 마감 22:00 조정 00:30 회의 10:00"},
        {"level": "content", "text": "브리핑 12:30 시작"},
        {"level": "content", "text": "소요 (30‘) 상대 L+2h36m 기준 L+20 비율 24:00"},
        {"type": "table", "title": "행사 시간표",
         "headers": ["구분", "시각", "비고"],
         "rows": [["집결", "12:30", "-"], ["발사", "16:55", "예정"]]},
        {"level": "title", "text": "교통편 안내"},
        {"level": "content", "text": "셔틀 12:30 출발"},
        {"level": "content", "text": "5:08-8:02"},
        {"level": "content", "text": "▪열차 이동(용산 → 여천)"},
    ],
}

SCHEDULE_SCOPE = 'between:"행사 일정".."브리핑 12:30 시작"'


class TestShiftTime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src = os.path.join(cls.tmp.name, "plan.hwpx")
        build_sample(cls.src, SHIFT_SPEC)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _run(self, shift, name, **kw):
        """순연 실행 → (결과 경로, 본문 텍스트, changes, kept)."""
        out = os.path.join(self.tmp.name, name)
        kw.setdefault("keywords", ())  # 키워드 제외는 해당 테스트에서만 켠다
        minutes = S.parse_shift(shift, allow_zero=kw.get("pad_hour", False))
        changes, kept = S.shift_file(self.src, out, minutes, **kw)
        return out, K.extract_text(out), changes, kept

    # 1. 자릿수·구분자 보존
    def test_digit_width_and_separator_preserved(self):
        _, text, _, _ = self._run("+2:45", "w1.hwpx")
        self.assertIn("집결 12:05~12:45", text)      # 한자리 시 + 물결표
        self.assertIn("점검 12:05-12:45", text)      # 두자리 시 + 하이픈
        self.assertIn("준비 20:45∼20:50", text)      # U+223C 물결표
        # 결과 시가 한자리가 되는 경우에만 자릿수 규칙이 드러난다
        _, text2, _, _ = self._run("-2:00", "w2.hwpx")
        # 토큰마다 원본 자릿수를 따른다: 9:20 → 7:20(한자리), 10:00 → 08:00(두자리)
        self.assertIn("집결 7:20~08:00", text2)
        self.assertIn("점검 07:20-08:00", text2)

    # 2. 자정 넘김(mod 1440)
    def test_midnight_wrap(self):
        _, text, _, _ = self._run("+2:45", "mid.hwpx")
        self.assertIn("심야 02:35", text)   # 23:50 +2:45
        self.assertIn("마감 00:45", text)   # 22:00 +2:45

    # 3. 음수 순연
    def test_negative_shift(self):
        _, text, _, _ = self._run("-1:00", "neg.hwpx")
        self.assertIn("회의 09:00", text)   # 10:00 -1:00
        self.assertIn("조정 23:30", text)   # 00:30 -1:00 (자정 역방향)

    # 4. 범위 한정 — 같은 '12:30'이 세 곳에 있어도 지정 구간만 바뀐다 (회귀)
    def test_scope_limits_change(self):
        _, text, changes, kept = self._run("+2:45", "scope.hwpx",
                                           scopes=[SCHEDULE_SCOPE])
        self.assertIn("브리핑 15:15 시작", text)   # 구간 안 — 순연됨
        self.assertIn("셔틀 12:30 출발", text)     # 구간 밖 — 보존
        self.assertIn("12:30", text)               # 표 셀도 보존
        self.assertEqual(text.count("12:30"), 2)   # 표 + 셔틀
        self.assertTrue(kept > 0)
        self.assertTrue(all(c.section.endswith("section0.xml") for c in changes))

    # 5. 분리 노드 제외 — 값과 라벨이 다른 노드여도 range 제외로 보존 (회귀)
    def test_exclude_range_protects_split_node(self):
        # 드라이런이 알려 준 바이트 오프셋을 그대로 --exclude range:에 쓰는 실사용 절차
        dry, _ = S.shift_file(self.src, None, S.parse_shift("+2:45"),
                              keywords=(), dry_run=True)
        target = next(c for c in dry if "5:08-8:02" in c.old)
        rng = (f"range:section{S._sec_num(target.section)}:"
               f"{target.byte_off}-{target.byte_off + 40}")
        _, text, _, kept = self._run("+2:45", "excl.hwpx", excludes=[rng])
        self.assertIn("5:08-8:02", text)          # 값 노드 보존
        self.assertIn("▪열차 이동", text)          # 라벨 노드 그대로
        self.assertEqual(kept, 2)                 # 보존된 시각 2건
        self.assertIn("브리핑 15:15", text)        # 나머지는 정상 순연

    def test_exclude_keyword_is_secondary_guard(self):
        # 키워드 제외는 '열차' 라벨 노드만 지킬 뿐, 값 노드는 못 지킨다(설계 근거 2)
        _, text, _, _ = self._run("+2:45", "kw.hwpx", keywords=S.DEFAULT_KEYWORDS)
        self.assertIn("7:53-10:47", text)   # 값 노드는 키워드로 못 막는다
        self.assertIn("▪열차 이동", text)

    # 6. 비대상 보존
    def test_non_time_tokens_untouched(self):
        _, text, _, _ = self._run("+2:45", "keep.hwpx")
        self.assertIn("소요 (30‘) 상대 L+2h36m 기준 L+20 비율 24:00", text)
        for token in ("(30‘)", "L+2h36m", "L+20", "24:00"):
            self.assertIn(token, text)

    # 7. 자기 검산 — 결과를 훼손하면 잡아낸다
    def test_verification_catches_corruption(self):
        good = [S.Change("Contents/section0.xml", 100, "집결", "9:20~10:00",
                         "12:05~12:45")]
        self.assertEqual(S.verify_changes(good, 165), [])
        bad_time = [good[0]._replace(new="12:05~13:45")]     # 산술 오류
        self.assertTrue(S.verify_changes(bad_time, 165))
        bad_sep = [good[0]._replace(new="12:05-12:45")]      # 구분자 변조
        self.assertTrue(S.verify_changes(bad_sep, 165))
        bad_text = [good[0]._replace(old="집결 9:20", new="집합 12:05")]  # 본문 변조
        self.assertTrue(S.verify_changes(bad_text, 165))
        bad_width = [good[0]._replace(old="9:20", new="09:20")]
        self.assertTrue(S.verify_changes(bad_width, 0 + 240))

    def test_verification_blocks_write(self):
        # 검산 실패 시 파일을 쓰지 않는다(전건 검증 → 중단)
        out = os.path.join(self.tmp.name, "never.hwpx")
        real = S.verify_changes
        S.verify_changes = lambda *a, **kw: ["강제 실패"]
        try:
            with self.assertRaises(SystemExit):
                S.shift_file(self.src, out, 165, keywords=())
        finally:
            S.verify_changes = real
        self.assertFalse(os.path.exists(out))

    # 8. 구조 보존
    def test_structure_preserved(self):
        out, _, changes, _ = self._run("+2:45", "struct.hwpx")
        self.assertEqual(V.validate_structure(out), [])
        src_parts, _ = K.read_package(self.src)
        out_parts, _ = K.read_package(out)
        for name in S._sections(out_parts):
            sec = out_parts[name].decode("utf-8")
            self.assertEqual(len(K.LINESEG_RE.findall(sec)), 0)
            self.assertEqual(len(S._T_RE.findall(sec)),
                             len(S._T_RE.findall(src_parts[name].decode("utf-8"))))
        self.assertNotEqual(out_parts[K.PRVTEXT_NAME], src_parts[K.PRVTEXT_NAME])
        self.assertTrue(changes)

    def test_dry_run_writes_nothing_and_matches_report(self):
        out = os.path.join(self.tmp.name, "dry.hwpx")
        changes, kept = S.shift_file(self.src, out, S.parse_shift("+2:45"),
                                     scopes=[SCHEDULE_SCOPE], keywords=(),
                                     dry_run=True)
        self.assertFalse(os.path.exists(out))
        rows = S.render_rows(changes)
        report = S.render_report(changes, kept, 165, self.src,
                                 [SCHEDULE_SCOPE], [], [])
        for c in changes:  # 드라이런과 대조표가 같은 목록을 제시한다
            self.assertIn(S._cell(c.new), rows)
            self.assertIn(f"| {S._where(c)} |", report)
        self.assertEqual(len(re.findall(r"^\| section", report, re.M)), len(changes))

    # --pad-hour: KASA 표기법(시 두 자리) 교정을 적용 범위 안에서만 함께 수행
    def test_pad_hour_normalizes_within_scope_only(self):
        _, text, _, _ = self._run("-2:00", "pad1.hwpx", pad_hour=True,
                                  scopes=[SCHEDULE_SCOPE])
        self.assertIn("집결 07:20~08:00", text)   # 9:20 → 07:20 (한 자리 시 교정)
        self.assertIn("5:08-8:02", text)          # 범위 밖 교통편 표기는 그대로

    def test_pad_hour_only_without_shift(self):
        # 순연 없이 표기만 교정(+0m) — 자릿수 외 문자는 그대로여야 한다
        _, text, changes, _ = self._run("+0m", "pad2.hwpx", pad_hour=True,
                                        scopes=[SCHEDULE_SCOPE])
        self.assertIn("집결 09:20~10:00", text)
        self.assertIn("브리핑 12:30 시작", text)  # 이미 두 자리면 무변경
        self.assertIn("5:08-8:02", text)          # 범위 밖 무변경
        self.assertTrue(changes)

    def test_pad_hour_leaves_non_time_pairs(self):
        _, text, _, _ = self._run("+0m", "pad3.hwpx", pad_hour=True)
        self.assertIn("비율 24:00", text)         # 시각이 아닌 숫자쌍은 교정 대상 아님
        self.assertIn("L+2h36m", text)

    def test_pad_hour_clears_lint_warning(self):
        """교정 후 kasa_lint의 '두 자리' 경고가 사라진다(규칙과 실제로 맞물리는지)."""
        import kasa_lint as L
        out, _, _, _ = self._run("+0m", "pad4.hwpx", pad_hour=True)
        parts, _ = K.read_package(out)
        warns = L.lint_paragraphs(L.paragraphs_from_parts(parts))
        self.assertFalse([w for w in warns if "두 자리로" in w])

    def test_verification_accounts_for_pad_hour(self):
        ch = [S.Change("Contents/section0.xml", 100, "집결", "9:20", "09:20")]
        self.assertEqual(S.verify_changes(ch, 0, pad_hour=True), [])
        self.assertTrue(S.verify_changes(ch, 0))          # 교정 없이는 자릿수 불일치
        bad = [S.Change("Contents/section0.xml", 100, "집결", "9:20", "9:20")]
        self.assertTrue(S.verify_changes(bad, 0, pad_hour=True))

    def test_negative_shift_survives_argparse(self):
        """'--shift -1:00'은 argparse가 옵션으로 오인하므로 =형태로 흡수한다."""
        self.assertEqual(S.fix_negative_shift(["--shift", "-1:00", "--dry-run"]),
                         ["--shift=-1:00", "--dry-run"])
        self.assertEqual(S.fix_negative_shift(["--shift", "-90m"]),
                         ["--shift=-90m"])
        # 양수·=형태·다른 옵션은 건드리지 않는다
        self.assertEqual(S.fix_negative_shift(["--shift", "+2:45", "--yes"]),
                         ["--shift", "+2:45", "--yes"])
        self.assertEqual(S.fix_negative_shift(["--scope", "section:0"]),
                         ["--scope", "section:0"])

    def test_zero_shift_requires_pad_hour(self):
        self.assertEqual(S.parse_shift("+0m", allow_zero=True), 0)
        with self.assertRaises(SystemExit):   # 옮길 것도 고칠 것도 없는 실행은 거부
            S.parse_shift("+0m")

    def test_parse_shift_forms(self):
        self.assertEqual(S.parse_shift("+2:45"), 165)
        self.assertEqual(S.parse_shift("-1:00"), -60)
        self.assertEqual(S.parse_shift("+165m"), 165)
        self.assertEqual(S.parse_shift("-90m"), -90)
        for bad in ("2:45", "+2:60", "abc", "+0m"):
            with self.assertRaises(SystemExit):
                S.parse_shift(bad)

    def test_scope_forms_resolve(self):
        parts, _ = K.read_package(self.src)
        self.assertTrue(S.parse_scope("section:0", parts))
        self.assertTrue(S.parse_scope('after:"교통편 안내"', parts))
        self.assertTrue(S.parse_scope("range:section0:100-2000", parts))
        for bad in ("section:99", 'after:"없는앵커"', "nope:1", "table:999"):
            with self.assertRaises(SystemExit):
                S.parse_scope(bad, parts)

    def test_table_scope_is_one_based(self):
        """표 순번은 hwpx_edit.py list-tables와 같은 1-base다(규칙 22와 동일 기준)."""
        import hwpx_edit as HE
        parts, _ = K.read_package(self.src)
        tables = HE._doc_tables(parts)
        self.assertEqual(S.parse_scope("table:1", parts), [tables[0]])
        self.assertEqual(S.parse_scope(f"table:{len(tables)}", parts), [tables[-1]])
        with self.assertRaises(SystemExit):      # 0은 없는 순번
            S.parse_scope("table:0", parts)
        with self.assertRaises(SystemExit):
            S.parse_scope(f"table:{len(tables) + 1}", parts)


if __name__ == "__main__":
    unittest.main()
