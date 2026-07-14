---
name: kasa-hwpx
version: 0.8.1
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
│   ├── kasa_lib.py        # ★ 핵심 엔진(표지 치환 + 본문/표/참고 생성 + PrvText 재생성)
│   ├── build_report.py    # CLI: JSON 사양 / 마커 텍스트 → .hwpx
│   ├── validate.py        # 구조 + KASA 규정 준수 검증(표기법 lint 통합)
│   ├── kasa_lint.py       # 표기법 lint(날짜·시간·숫자·항목 기호·위계)
│   ├── extract_text.py    # 텍스트 추출
│   ├── redraft.py         # 재기안: 기존 HWPX 서식 보존 본문 치환
│   ├── hwpx_diff.py       # 신구대조: 두 HWPX 문단·표 셀 diff(읽기 전용)
│   ├── label_fill.py      # 라벨 기반 양식 채우기("성명:" 옆 빈 셀 자동 입력)
│   ├── hwpx_edit.py       # in-place 편집: 머리말·꼬리말·쪽번호·표 구조 op
│   ├── hwpx_image.py      # 직인/서명 등 이미지 삽입·교체·삭제(BinData+manifest+pic)
│   ├── secure_fill.py     # PII 비경유 양식 채우기(detect/fill/verify/shred)
│   ├── fix_vertical.py    # 세로쓰기 오변환 자동보정(다수결 flip)
│   └── office/{unpack,pack}.py
├── hooks/                 # PreToolUse 가드 훅 3종(선택 설치, hooks/README.md)
│   ├── finalize_guard.py  # 전달 전 validate --kasa 통과 강제
│   ├── sample_guard.py    # 견본/placeholder 문서 오인 전달 차단
│   └── spec_guard.py      # 제목·작성정보·발행시기 미확보 시 질문 강제
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
 │    ├─ 개인정보(이름·연락처 등)면      → 워크플로우 B-2 (secure-fill, 값 비노출)
 │    └─ {{자리표시자}} 없는 표 양식이면 → 워크플로우 B-3 (label_fill, 라벨 옆 빈 셀)
 ├─ "구버전과 뭐가 달라졌어?"           → 신구대조 (hwpx_diff.py, 읽기 전용)
 ├─ "이 hwpx 수정/편집"                 → 워크플로우 C (unpack→편집→pack)
 │    ├─ 꼬리말·쪽번호·표 셀/행/열이면    → 워크플로우 D (hwpx_edit in-place, 서식 보존)
 │    └─ 직인·서명·이미지면              → 워크플로우 D-2 (hwpx_image in-place, 서식 보존)
 ├─ "이 hwpx 읽어줘/내용 추출"          → 워크플로우 E (텍스트 추출)
 └─ "글이 세로로 깨져요/변환 이상"      → fix_vertical.py (오변환 자동보정)
```

> **워크플로우 B(재기안) 빠른 실행.** 임의의 기존 HWPX(KASA 여부 무관)의 서식·표·여백을
> 보존한 채 본문 문구만 바꾼다. 한컴 없이 동작하며, 치환된 흐름 문단의 `linesegarray`를
> 제거해 한글이 열 때 재계산한다. 모든 섹션(section0..N)을 처리하고, 미변경 zip 엔트리는
> 원본 메타데이터 그대로 유지하며, 키별 치환 건수를 출력해 **미적중 키를 경고**한다.
> ```bash
> # repl.json 예: {"2025년": "2026년", "(부서명)": "우주수송정책과"}
> python3 scripts/redraft.py --input 원본.hwpx --map repl.json --output 결과.hwpx
> #   --mode exact  : <hp:t> 전체가 키와 정확히 일치할 때만 치환(오치환 방지)
> # 미적중 키가 있으면 extract_text.py로 원문 표기를 확인 후 맵을 수정한다.
> ```

## 워크플로우 A: 사양 → 보고서 생성 (기본)

> **자연어 입력 처리 (가장 중요).** 최종 사용자는 JSON을 작성하지 않으며 명령어도 입력하지 않는다.
> "우주항공청 양식으로 ○○ 보고서 만들어줘"처럼 평범한 한국어 요청과 본문 내용을 받으면,
> **에이전트가 그 내용을 아래 JSON 사양으로 직접 변환**해 스크립트를 실행하고 `.hwpx`를 돌려준다.
> 다음을 지킨다:
> - 사용자의 자유로운 서술에서 제목·발행시기·작성정보·본문 항목을 스스로 추출한다.
> - □/ㅇ/-/※ 위계는 내용의 논리에 맞춰 에이전트가 부여한다(사용자가 마커를 몰라도 된다).
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

## 워크플로우 B-2: secure-fill (개인정보 비노출 채우기)
이름·연락처·주민번호 등이 들어가는 양식은 **값을 화면·로그에 노출하지 않는**
secure-fill을 쓴다. 프로필 JSON: `{"{{이름}}": "홍길동", "{{전화}}": {"value": "01012345678", "format": "phone"}}`
(format: phone/rrn/date/upper/lower/nospace/digits/mask)
```bash
python3 scripts/secure_fill.py detect 양식.hwpx --profile p.json   # 키 적중만 확인
python3 scripts/secure_fill.py fill   양식.hwpx --profile p.json --output 결과.hwpx
python3 scripts/secure_fill.py verify 결과.hwpx --profile p.json   # 마스킹 표시로 확인
python3 scripts/secure_fill.py shred  p.json                       # 프로필 안전 삭제
```

## 워크플로우 B-3: 라벨 기반 양식 채우기
`{{자리표시자}}`가 없는 관공서 표 양식에서 "성명:" 같은 라벨 셀을 찾아
오른쪽(없으면 아래) **빈 셀**에 값을 넣는다. 빈 셀에 텍스트만 기록하며(구조 창작 없음),
이미 값이 있는 셀은 덮어쓰지 않고 미적중으로 보고한다.
```bash
python3 scripts/label_fill.py detect 양식.hwpx                        # 라벨·채울 위치 미리보기(선행)
python3 scripts/label_fill.py fill   양식.hwpx --data d.json --output 결과.hwpx
# d.json 예: {"성명": "홍길동", "소속": "우주수송정책과"}  (콜론·공백 차이 무시 대조)
```
개인정보 값은 B-2(secure-fill)를 사용한다 — label_fill은 값을 출력에 표시한다.

## 신구대조 (문서 비교, 읽기 전용)
재기안 전후 검수: 두 HWPX의 문단·표 셀 단위 차이를 보고한다(원본 무수정).
```bash
python3 scripts/hwpx_diff.py 구버전.hwpx 신버전.hwpx           # 추가/삭제/수정 + 셀 diff
python3 scripts/hwpx_diff.py 구버전.hwpx 신버전.hwpx --stats   # 통계 한 줄
```

## 워크플로우 C: 편집
```bash
python3 scripts/office/unpack.py 문서.hwpx ./unpacked/
# Contents/section0.xml 등 편집
python3 scripts/office/pack.py ./unpacked/ 수정.hwpx
python3 scripts/validate.py 수정.hwpx --kasa
```

## 워크플로우 D: in-place 편집 (머리말·꼬리말·쪽번호·표, 서식 보존)
unpack 없이 원본 서식·zip 메타데이터를 보존한 채 편집한다.
```bash
python3 scripts/hwpx_edit.py set-footer  문서.hwpx --text "꼬리말" --output 결과.hwpx
python3 scripts/hwpx_edit.py set-pagenum 문서.hwpx --pos BOTTOM_CENTER --side-char "-" --output 결과.hwpx
python3 scripts/hwpx_edit.py list-tables 문서.hwpx                  # 표 순번 확인(필수 선행)
python3 scripts/hwpx_edit.py set-cell    문서.hwpx --table 3 --row 0 --col 0 --bg D9D9D9 --output 결과.hwpx
python3 scripts/hwpx_edit.py add-col     문서.hwpx --table 3 --at 1 --output 결과.hwpx
python3 scripts/hwpx_edit.py del-row     문서.hwpx --table 3 --row 2 --output 결과.hwpx
python3 scripts/hwpx_edit.py merge-cells 문서.hwpx --table 3 --from 0,0 --to 1,0 --output 결과.hwpx
```
- `--table`은 문서 순번(1-based, 머리말/꼬리말 내부 표 제외·표지 표 포함) — **반드시 list-tables로 먼저 확인**.
- 중첩 표를 품은 표는 편집 거부, 병합(span) 표는 구조 op(add-col/del-row/merge-cells) 거부(set-cell은 가능).
- KASA 문서의 머리말(MI 로고)은 건드리지 않는다 — 꼬리말·쪽번호만 편집.
- 세로쓰기 오변환(외부 hwp→hwpx 변환 사고)은 `fix_vertical.py --input 원본 --output 보정본`으로
  다수결(VERTICAL>HORIZONTAL) 자동보정. 부분 세로쓰기는 보호되며 `--force`로만 강제.

## 워크플로우 D-2: 이미지(직인/서명) in-place 편집
BinData 등록·content.hpf manifest·`<hp:pic>` 앵커 삽입을 한 번에 처리한다(png/jpg/gif/bmp).
```bash
python3 scripts/hwpx_image.py list    문서.hwpx                      # id·참조 수 확인(선행 권장)
python3 scripts/hwpx_image.py add     문서.hwpx --image 직인.png --anchor "(직인)" \
                                      --replace-anchor --width-mm 20 --output 결과.hwpx
python3 scripts/hwpx_image.py replace 문서.hwpx --id image2 --image 새직인.png --output 결과.hwpx
python3 scripts/hwpx_image.py remove  문서.hwpx --id image2 --output 결과.hwpx
```
- `add`는 `--anchor` 텍스트가 있는 문단에 글자취급(treatAsChar) 그림을 넣는다.
  `--replace-anchor`는 앵커 문구를 지우고 그 자리에 삽입(양식의 "(직인)" 자리 채움).
  크기 미지정 시 원본 픽셀(96dpi) 크기, 한 변만 지정하면 비율 유지.
- `replace`는 표시 크기를 유지한 채 BinData 바이트와 원본 크기 메타를 갱신한다(직인 갱신).
- `remove`는 머리말/꼬리말 안 그림(KASA MI 로고)을 `--force` 없이 거부한다.

## 워크플로우 E: 읽기/추출
```bash
python3 scripts/extract_text.py 문서.hwpx
```

## 검증 (항상 수행)
```bash
python3 scripts/validate.py 결과.hwpx --kasa
```
구조 무결성(ZIP/mimetype/XML/secPr/미정의 참조/`itemCnt` 정합)과 KASA 규정(MI·여백·마커 글꼴·표지 요소)을 점검한다.
`--kasa`는 추가로 **줄겹침 캐시·자동번호 회귀·세로쓰기 오변환(`textDirection="VERTICAL"`)·
미리보기(PrvText) 본문 미반영·표 셀 과밀(긴 텍스트 한 문단 집중)·표기법 lint**를 탐지한다.
셀 과밀 경고가 나오면 해당 셀 내용을 여러 문단이나 목록으로 나누고,
세로쓰기 경고는 `fix_vertical.py`로 보정한다.

**표기법 lint** (`kasa_lint.py`, 단독 실행 시 `--strict`로 경고를 실패 처리):
날짜 `2026. 7. 7.`(온점+공백, 앞 0 제거, 일 뒤 온점 — `’YY.MM.DD.` 축약형은 허용),
요일 괄호는 날짜에 붙임(`7. 7.(화)`), 시간 24시각제 쌍점·두 자리(`08:09`, 날짜와 반대),
4자리 이상 숫자의 천 단위 쉼표(연도 제외), 항목 기호 □/ㅇ/-/※/* 위계(유사 기호·역전 탐지),
물결표(`~`·`∼`) 앞뒤 붙여쓰기, 쌍점 뒤 한 칸 띄움(`원장: 김갑동`).
**경고가 나오면 본문 사양의 표기를 고쳐 재생성한다.**

## 가드 훅 (Claude Code 전용 — 선택 설치 권장)
`hooks/`의 PreToolUse 훅 3종을 `.claude/settings.json`에 등록하면(방법: `hooks/README.md`)
(a) 규정 미통과 산출물 전달, (b) 견본·placeholder 문서 오인 전달, (c) 필수 정보
(제목·작성정보·발행시기) 미확보 생성 실행이 도구 실행 전에 차단된다(exit 2 → 에이전트가
사유를 읽고 질문·교정 후 재시도). 훅이 없어도 스킬은 동작한다.
**훅을 지원하지 않는 플랫폼(Codex·Gemini 등)에서는 위 (a)(b)(c)를 에이전트가 수동
게이트로 지킨다** — 이 규칙 자체는 플랫폼 기능 없이도 성립해야 한다(AGENTS.md 7장).

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
13. **표 내부는 내어쓰기 금지.** 표 셀 원본 paraPr(13/14/17)은 intent=-2440(내어쓰기)이므로, intent=0으로 복제한 paraPr 26/27/28/29를 주입해 표에 사용한다(`INDENT_PARAPR`, `TBL_*`). 29는 17(RIGHT)의 정렬을 JUSTIFY로 오버라이드한 텍스트 데이터 셀용.
14. **긴 제목은 2줄 허용.** 표지 제목 문단의 줄위치 캐시(linesegarray)를 제거해 한글이 재계산하도록 한다(긴 제목 자동 2줄). `_set_field_by_anchor(..., strip_lineseg=True)`.
15. **참고 서식은 본문과 동일.** 참고 본문도 본문과 같은 간격(스페이서)·내어쓰기를 적용한다(`_build_body_xml`의 참고 루프).
16. **재기안(re-draft)은 `<hp:t>` 단위 치환 + 전체 `linesegarray` 제거.** 기존 HWPX의 서식을 보존한 채 본문만 바꿀 때는 `redraft.py`를 쓴다. charPr/paraPr·표·셀병합·여백은 그대로 두고 텍스트만 교체하며, 치환 후 줄 위치 캐시를 비워 한글이 재계산하도록 한다(규칙 9와 동일 원리). 오치환이 우려되면 `--mode exact`로 `<hp:t>` 전체 일치만 치환한다.
17. **재기안 XML 가드레일.** `<hp:t>` 안에 컨트롤 태그가 섞인 경우(mixed content) 태그는 건드리지 않고 텍스트 구간에만 치환한다(exact 모드는 해당 노드를 건너뜀). `linesegarray`는 속성·self-closing 형태까지 `LINESEG_RE`로 제거한다. 치환 후 키별 적중 수를 확인해 미적중 키는 사용자에게 알린다. (참고: ai-public-peasant/hwpx-rekian XML guardrails, Canine89/hwpxskill finalize 가드)
18. **서식 보존 편집은 zip 메타데이터도 보존한다.** 재기안·`fill_template`·`hwpx_edit`·`fix_vertical` 등 서식 보존 경로는 `write_package_preserving`으로 기록해, 미변경 엔트리의 원본 ZipInfo(순서·시각·압축방식)를 그대로 유지한다. 한글이 zip 메타데이터에 민감할 수 있기 때문이다. (참고: Canine89/hwpxskill 'Preserve HWPX XML bytes')
19. **본문을 바꾸면 미리보기(PrvText)도 함께 갱신한다.** 템플릿의 `Preview/PrvText.txt`를 그대로 두면 탐색기 미리보기·문서 검색에 옛 내용(표준양식 원문)이 노출된다. 빌드·재기안·`fill_template`은 섹션 텍스트로 PrvText를 재생성하며(`refresh_prvtext`, 기존 엔트리가 있을 때만), `validate --kasa`가 미반영을 탐지한다. (참고: jkf87/hwpx-skill `_write_preview`)
20. **개인정보는 secure-fill로만 채운다.** 이름·연락처·주민번호 등은 값이 화면·로그·예외에 남지 않도록 `secure_fill.py`(detect→fill→verify→shred)를 쓴다. 에이전트는 대화에 값을 되풀이하지 않고, 작업 후 프로필 파일 shred를 안내한다.
21. **표 데이터 셀은 숫자만 우측 정렬, 행 높이는 표 안에서 동일하게.** 숫자(쉼표·%·부호 포함)로만 된 셀은 paraPr 28(우측), 일반 텍스트 셀은 paraPr 29(기본 정렬)를 쓴다(`_is_numeric_cell`). 데이터 행 선언 높이는 셀 폭 대비 예상 줄 수(전각 1200·반각 600, 줄간격 160%)의 표 내 최댓값으로 전 행 통일한다 — 접히는 셀이 있어도 행 높이가 들쭉날쭉해지지 않는다(`_cell_lines`, 줄바꿈 없으면 기존 282 유지).
22. **표 편집 전 list-tables로 순번을 확인한다.** 표 순번은 머리말/꼬리말 내부 표를 제외한 문서 순서(표지 레이아웃 표 포함)다. 중첩 표 포함 표는 편집 금지, span 표는 구조 op 금지 — 가드가 거부하면 사용자에게 이유를 설명한다.

## 상세 참조
- 양식 규격 전문: `references/kasa-report-style.md`
- 스타일 ID 맵: `references/template-styles.md`
- XML 구조·패턴: `references/xml-structure.md`
- 보고서 기호 위계: □(15pt) → ㅇ(15pt) → -(15pt) → ※(12pt) → *(12pt)
