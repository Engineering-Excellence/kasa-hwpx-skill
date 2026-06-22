---
name: kasa-hwpx
description: 우주항공청(KASA) 표준보고서를 한글 HWPX(.hwpx)로 생성·편집·검증하는 스킬. '우주항공청', 'KASA', '우주청 보고서', '표준보고서', '한글 보고서', 'hwpx', '한글파일', '기관 보고서', '대외비 보고서', '누리호 보고서' 등 우주항공청 양식의 한글 문서가 필요할 때 반드시 사용한다. 첨부된 표준양식을 기준(SSOT)으로 표지·MI 로고·편집용지를 그대로 보존하고 본문만 채워 규정에 맞는 보고서를 만든다. 외부 패키지 없이 파이썬 표준 라이브러리만으로 동작한다.
allowed-tools: Bash(python3 *), Read, Write, Glob, Grep
---

# 우주항공청(KASA) 표준보고서 HWPX 스킬

우주항공청 표준양식에 100% 부합하는 한글 보고서(.hwpx)를 만든다.
**기준 양식 `assets/kasa-standard-report.hwpx`를 단일 기준으로 삼아 표지·MI 로고·머리말·
편집용지(여백/줄간격)를 원본 그대로 보존**하고, 표지 필드와 본문만 채운다.

## 환경
- **외부 패키지 불필요.** 파이썬 표준 라이브러리(zipfile/re/json)만 사용 → 네트워크 없는 환경에서 동작.
- `python-hwpx`·`lxml` 등 설치하지 않는다(버그·의존성 회피).

## 디렉토리
```
kasa-hwpx/
├── SKILL.md
├── scripts/
│   ├── kasa_lib.py        # ★ 핵심 엔진(표지 치환 + 본문/표/참고 생성)
│   ├── build_report.py    # CLI: JSON 사양 / 마커 텍스트 → .hwpx
│   ├── validate.py        # 구조 + KASA 규정 준수 검증
│   ├── extract_text.py    # 텍스트 추출
│   ├── redraft.py         # 재기안: 기존 HWPX 서식 보존 본문 치환
│   └── office/{unpack,pack}.py
├── assets/kasa-standard-report.hwpx   # 기준 양식(SSOT)
└── references/
    ├── kasa-report-style.md   # 양식 규격 전문
    ├── template-styles.md     # charPr/paraPr/borderFill ID 맵
    └── xml-structure.md       # secPr/네임스페이스/표·표지 패턴
```

## 워크플로우 선택
```
요청
 ├─ "보고서 만들어줘 / 작성해줘"        → 워크플로우 A (사양→보고서 생성)
 ├─ "이 양식에 내용만 채워줘"           → 워크플로우 B (텍스트 치환/재기안, 서식 100% 보존)
 ├─ "이 hwpx 수정/편집"                 → 워크플로우 C (unpack→편집→pack)
 └─ "이 hwpx 읽어줘/내용 추출"          → 워크플로우 E (텍스트 추출)
```

> **워크플로우 B(재기안) 빠른 실행.** 임의의 기존 HWPX(KASA 여부 무관)의 서식·표·여백을
> 보존한 채 본문 문구만 바꾼다. 한컴 없이 동작하며, 치환된 흐름 문단의 `linesegarray`를
> 제거해 한글이 열 때 재계산한다.
> ```bash
> # repl.json 예: {"2025년": "2026년", "(부서명)": "우주수송정책과"}
> python3 scripts/redraft.py --input 원본.hwpx --map repl.json --output 결과.hwpx
> #   --mode exact  : <hp:t> 전체가 키와 정확히 일치할 때만 치환(오치환 방지)
> ```

## 워크플로우 A: 사양 → 보고서 생성 (기본)

> **자연어 입력 처리 (가장 중요).** 최종 사용자는 JSON을 작성하지 않으며 명령어도 입력하지 않는다.
> "우주항공청 양식으로 ○○ 보고서 만들어줘"처럼 평범한 한국어 요청과 본문 내용을 받으면,
> **Claude가 그 내용을 아래 JSON 사양으로 직접 변환**해 스크립트를 실행하고 `.hwpx`를 돌려준다.
> 다음을 지킨다:
> - 사용자의 자유로운 서술에서 제목·발행시기·작성정보·본문 항목을 스스로 추출한다.
> - □/ㅇ/-/※ 위계는 내용의 논리에 맞춰 Claude가 부여한다(사용자가 마커를 몰라도 된다).
> - 제목·작성부서·날짜 등 핵심 정보가 빠졌으면 한 번에 하나씩 짧게 묻는다(질문 남발 금지).
> - 수치 비교 등 표로 보여야 할 데이터는 자동으로 표로 구성한다.
> - 생성 후 `validate.py --kasa`로 점검하고, 한글에서 열어 확인하도록 안내한다.

사용자 내용을 JSON 사양으로 정리한 뒤 생성한다.

```bash
python3 scripts/build_report.py --spec spec.json --output 결과.hwpx
# 또는 간이 마커 텍스트:
python3 scripts/build_report.py --markdown 본문.md --title "보고서 제목" --output 결과.hwpx
```

### JSON 사양 형식
```json
{
  "title": "보고서 제목",
  "pub_date": "2026. 6.",
  "author": "(’26.06.18., ○○담당관)",
  "slogan_lead": "우주항공 5대 강국 입국을 주도하는",
  "body": [
    {"level": "title",   "text": "추진 배경"},
    {"level": "content", "text": "..."},
    {"level": "sub",     "text": "..."},
    {"level": "note",    "text": "..."},
    {"type": "table", "title": "표 제목",
     "headers": ["구분", "내용1", "내용2"],
     "rows": [["A", "100", "300"], ["B", "200", "400"]]},
    {"level": "footnote", "text": "..."}
  ],
  "appendix": [
    {"label": "참고 1", "heading": "참고 제목",
     "body": [{"level": "content", "text": "..."}]}
  ]
}
```
- `level`: `title`(□) / `content`(ㅇ) / `sub`(-) / `note`(※) / `footnote`(*)
- 표는 `{"type":"table", ...}`. 모든 행의 칸 수는 `headers` 수와 같아야 한다.
- 미지정 필드(슬로건/날짜 등)는 기준 양식 기본값을 유지한다.

### 간이 마커 텍스트 형식
첫 줄은 제목. 본문은 `□ ㅇ - ※ *` 마커. `@날짜:` `@작성:` `@슬로건:` 메타 지원.
```
누리호 4차 발사 준비현황 보고
@날짜: 2026. 6.
@작성: (’26.06.18., 발사체개발부문)
□ 추진 배경
ㅇ 신뢰성 확보 및 우주수송 역량 강화
- 2027년 상반기 발사 목표
※ 3차 대비 탑재 중량 12% 증가
```

## 워크플로우 B: 텍스트 치환 (서식 100% 보존)
기존 KASA 양식의 특정 문구만 바꿀 때. `kasa_lib.fill_template(template, {old: new}, out)` 사용.
표지 표 레이아웃까지 원본 그대로 유지된다.

## 워크플로우 C: 편집
```bash
python3 scripts/office/unpack.py 문서.hwpx ./unpacked/
# Contents/section0.xml 등 편집
python3 scripts/office/pack.py ./unpacked/ 수정.hwpx
python3 scripts/validate.py 수정.hwpx --kasa
```

## 워크플로우 E: 읽기/추출
```bash
python3 scripts/extract_text.py 문서.hwpx
```

## 검증 (항상 수행)
```bash
python3 scripts/validate.py 결과.hwpx --kasa
```
구조 무결성(ZIP/mimetype/XML/secPr/미정의 참조)과 KASA 규정(MI·여백·마커 글꼴·표지 요소)을 점검한다.

## Critical Rules
1. **HWPX만** 지원(`.hwp` 바이너리 미지원).
2. 기준 양식의 **첫 문단(secPr+colPr+머리말 MI)과 표지·편집용지는 보존**한다. 본문만 교체.
3. **스타일 ID는 기준 양식에서 추출한 값만** 사용(`references/template-styles.md`). 임의 생성·타 양식 ID 혼용 금지.
4. `mimetype`은 첫 ZIP 엔트리·무압축(STORED). 엔진이 자동 처리한다.
5. 네임스페이스 접두사(hp/hs/hh/hc) 보존. 빌드 후 `validate.py`로 점검.
6. 본문 문단 id는 고유 정수, XML 특수문자 `<>&"` 이스케이프(엔진이 처리).
7. **대외비/내부 자료**는 MI 생략(워터마크 대체)이 허용된다 — v1은 안내만 하며, 필요 시 사용자에게 확인.
8. 생성 후 반드시 `validate.py --kasa` 통과를 확인하고, 한글에서 열어 최종 점검을 권장한다.
9. **본문 흐름 문단에 `linesegarray`(줄 위치 캐시)를 넣지 않는다.** 원본 양식의 본문 lineseg는 `vertpos`가 텍스트영역 기준 *누적 절대값*이라, 모든 문단에 `vertpos="0"`을 박으면 한글이 캐시를 신뢰해 줄을 같은 높이에 겹쳐 그린다. 캐시를 비우면 한글이 열 때 줄 위치를 재계산(relayout)하여 자동 줄바꿈까지 정확히 배치한다(`_LINESEG = ""`).
10. **참고/붙임 머리는 3칸 표 디자인**을 사용한다 — 좌측 남색 박스(`borderFill 16`+`charPr 2` 흰색 16pt) + 간격칸(`borderFill 1` 무테) + 굵은 밑줄 제목칸(`borderFill 17`+`charPr 63` 검정 16pt). 엔진의 `make_appendix_header(label, heading)`가 생성한다.
11. **본문 위계 = 선행 공백(항목 시작) + 내어쓰기(2줄 이상).** HWP 내어쓰기 모델은 '첫 줄 시작 = 왼쪽여백(left), 나머지 줄 시작 = left + |intent|'이다. **첫 줄 시작은 반드시 0(left=0)**, 마커 위치는 선행 공백으로만 조정(□=0, ㅇ=1, -=3, ※=5칸). 2줄 이상일 때만 **나머지 줄 시작(|intent|)**을 첫 글자에 맞춘다(한글=전각1em·ASCII=반각0.5em 기준 em 배수: content 3000, sub 3750, note 4800, footnote 4200). 빌드 시 무번호 paraPr 22~25를 주입.
12. **항목 앞 간격(빈 줄)은 첨부 참고 양식과 동일.** 항목 앞에 빈 문단(스페이서)을 넣어 간격을 준다: □ 15pt, ㅇ 10pt, - 5pt, ※/* 3pt, 표 5pt(빈 문단의 글자높이로 간격 크기 결정). 문서 첫 항목 앞에는 넣지 않는다(`SPACER_CP`, `_spacer`). 기준은 `assets/reference-form-spacing.hwpx`.
13. **표 내부는 내어쓰기 금지.** 표 셀 원본 paraPr(13/14/17)은 intent=-2440(내어쓰기)이므로, intent=0으로 복제한 paraPr 26/27/28을 주입해 표에 사용한다(`INDENT_PARAPR`, `TBL_*`).
14. **긴 제목은 2줄 허용.** 표지 제목 문단의 줄위치 캐시(linesegarray)를 제거해 한글이 재계산하도록 한다(긴 제목 자동 2줄). `_set_field_by_anchor(..., strip_lineseg=True)`.
15. **참고 서식은 본문과 동일.** 참고 본문도 본문과 같은 간격(스페이서)·내어쓰기를 적용한다(`_build_body_xml`의 참고 루프).
16. **재기안(re-draft)은 `<hp:t>` 단위 치환 + 전체 `linesegarray` 제거.** 기존 HWPX의 서식을 보존한 채 본문만 바꿀 때는 `redraft.py`를 쓴다. charPr/paraPr·표·셀병합·여백은 그대로 두고 텍스트만 교체하며, 치환 후 줄 위치 캐시를 비워 한글이 재계산하도록 한다(규칙 9와 동일 원리). 오치환이 우려되면 `--mode exact`로 `<hp:t>` 전체 일치만 치환한다.

## 상세 참조
- 양식 규격 전문: `references/kasa-report-style.md`
- 스타일 ID 맵: `references/template-styles.md`
- XML 구조·패턴: `references/xml-structure.md`
- 보고서 기호 위계: □(15pt) → ㅇ(15pt) → -(15pt) → ※(12pt) → *(12pt)
