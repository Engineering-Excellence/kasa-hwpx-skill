# -*- coding: utf-8 -*-
"""표기법 lint 회귀 — 날짜·시간·숫자·기호·위계 규칙, 기준양식·빌드산출물 무경고."""
import copy
import os
import tempfile
import unittest

from tests.common import SAMPLE_SPEC, TEMPLATE, build_sample
from kasa_lint import lint_hwpx, lint_paragraphs
from validate import kasa_check


class TestRules(unittest.TestCase):
    def _warned(self, text, tag):
        warns = lint_paragraphs([text])
        self.assertTrue(any(f"표기법({tag})" in w for w in warns), (text, warns))

    def test_date_hyphen(self):
        self._warned("회의는 2026-07-07 개최", "날짜")

    def test_date_no_space(self):
        self._warned("2026.7.7. 기준 실적", "날짜")

    def test_date_leading_zero(self):
        self._warned("2026. 07. 07. 기준 실적", "날짜")

    def test_date_missing_tail_period(self):
        self._warned("2026. 7. 7 기준 실적", "날짜")

    def test_date_hangul(self):
        self._warned("2026년 7월 7일 개최", "날짜")

    def test_date_ok_forms(self):
        clean = ["2026. 7. 7. 기준", "2026. 10. 예정", "(’26.07.07., 발사체개발부문)",
                 "2027년 상반기 발사 목표"]
        self.assertEqual(lint_paragraphs(clean), [])

    def test_time_ampm(self):
        self._warned("오후 2시 보고 예정", "시간")

    def test_time_si_bun(self):
        self._warned("14시 30분 개최", "시간")

    def test_time_duration_ok(self):
        self.assertEqual(lint_paragraphs(["소요시간 3시간 30분 예상"]), [])

    def test_number_needs_comma(self):
        self._warned("예산 12500백만원 편성", "숫자")

    def test_number_ok(self):
        self.assertEqual(
            lint_paragraphs(["예산 12,500백만원", "2026년 예산", "총중량 200톤급"]), [])

    def test_marker_lookalike(self):
        self._warned("○ 추진 배경입니다", "기호")

    def test_hierarchy_reversed(self):
        warns = lint_paragraphs(["ㅇ 내용이 먼저 나옴", "□ 제목이 나중"])
        self.assertTrue(any("표기법(위계)" in w for w in warns), warns)

    def test_hierarchy_ok(self):
        self.assertEqual(
            lint_paragraphs(["□ 제목", "ㅇ 내용", "- 보충", "※ 참고", "-"]), [])

    def test_tilde_spaced(self):
        self._warned("기간: 2026. 7. 1. ~ 15. 운영", "기간")

    def test_tilde_unicode_variant(self):
        self._warned("기간: 5. 1. ∼ 6. 30.", "기간")  # U+223C도 인식

    def test_time_zero_padding(self):
        self._warned("행사는 8:9 시작", "시간")
        self._warned("점검은 9:30 시작", "시간")

    def test_time_padded_ok(self):
        self.assertEqual(lint_paragraphs(["회의 08:09~14:30 진행"]), [])

    def test_colon_tight(self):
        self._warned("담당: 원장:김갑동", "쌍점")

    def test_colon_ok(self):
        self.assertEqual(lint_paragraphs(["원장: 김갑동 (단위: 천원)"]), [])

    def test_weekday_gap(self):
        self._warned("개최일 2026. 7. 7. (화) 예정", "날짜")

    def test_weekday_attached_ok(self):
        self.assertEqual(lint_paragraphs(["개최일 2026. 7. 7.(화) 예정"]), [])


class TestHwpx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_template_clean(self):
        self.assertEqual(lint_hwpx(TEMPLATE), [])

    def test_built_sample_clean_and_integrated(self):
        out = os.path.join(self.tmp.name, "ok.hwpx")
        build_sample(out)
        self.assertEqual(lint_hwpx(out), [])
        self.assertTrue(any(n.startswith("[OK] 표기법") for n in kasa_check(out)))

    def test_violation_surfaces_in_validate(self):
        spec = copy.deepcopy(SAMPLE_SPEC)
        spec["body"].append({"level": "note", "text": "2026-07-07 오후 2시 점검"})
        out = os.path.join(self.tmp.name, "bad.hwpx")
        build_sample(out, spec)
        notes = kasa_check(out)
        self.assertTrue(any("표기법(날짜)" in n for n in notes), notes)
        self.assertTrue(any("표기법(시간)" in n for n in notes), notes)


if __name__ == "__main__":
    unittest.main()
