# -*- coding: utf-8 -*-
"""secure-fill 회귀 — 포맷 변환, detect/fill/verify 값 비노출, shred."""
import contextlib
import io
import json
import os
import tempfile
import unittest

from tests.common import K, build_sample
from secure_fill import (FORMATTERS, detect, fill, load_profile, mask,
                         shred, verify)

FORM_SPEC = {
    "title": "개인정보 포함 양식",
    "body": [
        {"level": "title", "text": "담당자 정보"},
        {"level": "content", "text": "성명: {{이름}}"},
        {"level": "content", "text": "연락처: {{전화}}"},
        {"level": "content", "text": "지정일: {{지정일}} / 미등록: {{부서}}"},
    ],
}

RAW_PHONE = "01012345678"
FMT_PHONE = "010-1234-5678"


class TestSecureFill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.form = os.path.join(cls.tmp.name, "form.hwpx")
        build_sample(cls.form, FORM_SPEC)
        cls.profile_path = os.path.join(cls.tmp.name, "profile.json")
        with open(cls.profile_path, "w", encoding="utf-8") as f:
            json.dump({
                "{{이름}}": "홍길동",
                "{{전화}}": {"value": RAW_PHONE, "format": "phone"},
                "{{지정일}}": {"value": "20260707", "format": "date"},
            }, f, ensure_ascii=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_formatters(self):
        self.assertEqual(FORMATTERS["phone"](RAW_PHONE), FMT_PHONE)
        self.assertEqual(FORMATTERS["phone"]("021234567"), "02-123-4567")
        self.assertEqual(FORMATTERS["rrn"]("9003151234567"), "900315-1234567")
        self.assertEqual(FORMATTERS["date"]("20260707"), "2026. 7. 7.")
        self.assertEqual(FORMATTERS["nospace"](" a b "), "ab")
        self.assertEqual(FORMATTERS["digits"]("T-01-2"), "012")
        self.assertEqual(FORMATTERS["mask"]("홍길동"), "홍**")

    def test_detect_counts_and_unknown(self):
        profile = load_profile(self.profile_path)
        hits, unknown = detect(self.form, profile)
        self.assertEqual(hits["{{이름}}"], 1)
        self.assertEqual(hits["{{전화}}"], 1)
        self.assertEqual(unknown, ["{{부서}}"])  # 프로필에 없는 플레이스홀더

    def test_fill_applies_formatted_values(self):
        profile = load_profile(self.profile_path)
        out = os.path.join(self.tmp.name, "filled.hwpx")
        counts = fill(self.form, profile, out)
        self.assertEqual(counts["{{이름}}"], 1)
        text = K.extract_text(out)
        self.assertIn("홍길동", text)
        self.assertIn(FMT_PHONE, text)       # 포맷 변환 적용
        self.assertNotIn(RAW_PHONE, text)    # 원시값은 남지 않음
        self.assertIn("2026. 7. 7.", text)
        self.assertNotIn("{{이름}}", text)
        # verify: 전 키 반영 + 마스킹
        res = verify(out, profile)
        self.assertTrue(all(found for found, _ in res.values()))
        self.assertEqual(res["{{이름}}"][1], "홍**")

    def test_cli_output_never_contains_values(self):
        # detect/fill/verify의 화면 출력에 원시값·변환값이 실리면 안 된다
        import secure_fill as SF
        import sys
        out = os.path.join(self.tmp.name, "filled2.hwpx")
        captured = io.StringIO()
        argv = sys.argv
        try:
            with contextlib.redirect_stdout(captured):
                for args in (["secure_fill", "detect", self.form,
                              "--profile", self.profile_path],
                             ["secure_fill", "fill", self.form,
                              "--profile", self.profile_path, "--output", out],
                             ["secure_fill", "verify", out,
                              "--profile", self.profile_path]):
                    sys.argv = args
                    try:
                        SF.main()
                    except SystemExit as e:
                        self.assertIn(e.code, (0, None))
        finally:
            sys.argv = argv
        printed = captured.getvalue()
        for secret in ("홍길동", RAW_PHONE, FMT_PHONE, "20260707", "2026. 7. 7."):
            self.assertNotIn(secret, printed)
        self.assertIn("홍**", printed)  # 마스킹 표시는 허용

    def test_mask(self):
        self.assertEqual(mask("abcd"), "a***")
        self.assertEqual(mask(""), "(빈 값)")

    def test_shred_removes_file(self):
        p = os.path.join(self.tmp.name, "shred-me.json")
        with open(p, "w") as f:
            f.write('{"{{k}}": "v"}')
        shred(p)
        self.assertFalse(os.path.exists(p))

    def test_unknown_format_rejected(self):
        p = os.path.join(self.tmp.name, "badfmt.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"{{k}}": {"value": "v", "format": "nope"}}, f)
        with self.assertRaises(SystemExit):
            load_profile(p)


if __name__ == "__main__":
    unittest.main()
