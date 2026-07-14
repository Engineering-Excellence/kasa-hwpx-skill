# kasa-hwpx

우주항공청(KASA) 표준보고서를 한글 **HWPX(.hwpx)**로 생성·편집·검증하는 **AI 에이전트 Skill**입니다.
표준양식(표지·MI 로고·편집용지)을 그대로 보존하고 본문만 채워, 규정에 맞는 보고서를 외부 패키지 없이
파이썬 표준 라이브러리만으로 만듭니다.

**특정 AI 플랫폼 전용이 아닙니다** — Claude/Cowork 앱과 Claude Code는 물론, Agent Skills
개방 표준(SKILL.md)과 AGENTS.md를 읽는 도구(**Codex CLI, Gemini CLI** 등)에서 그대로
사용할 수 있습니다. 코어는 파이썬 표준 라이브러리 CLI라 어떤 에이전트든 실행만 하면 됩니다.
(가드 훅만 Claude Code 전용 — 다른 플랫폼용 수동 게이트는 [AGENTS.md](AGENTS.md) 7장 참고)

> 🔰 컴퓨터가 익숙하지 않으세요? 명령어 없이 **말로 시켜서** 보고서를 만드는 방법은
> **[쉬운 사용설명서](사용설명서.md)**에 단계별로 정리해 두었습니다.
>
> 🤖 AI 에이전트(Claude Code 등)로 **다른 컴퓨터에서 작업을 이어서** 하려면
> **[AGENTS.md](AGENTS.md)**부터 읽으세요. 잔여 작업은 **[BACKLOG.md](BACKLOG.md)**에 있습니다.

## 저장소 구조

```
.
├── README.md
├── 사용설명서.md             # 컴퓨터가 낯선 분을 위한 쉬운 안내서
├── AGENTS.md                 # AI 에이전트/개발자용 작업 가이드(연속성 SSOT)
├── CLAUDE.md                 # Claude Code 진입점(AGENTS.md를 가져옴)
├── BACKLOG.md                # 잔여 작업·업스트림 관찰 시점·시작 절차
├── .gitignore / .gitattributes / .editorconfig
├── build_skill.py            # kasa-hwpx/ → dist/kasa-hwpx_v{버전}.skill 패키징
├── tests/                    # 회귀 테스트(unittest, .skill 미포함)
└── kasa-hwpx/                # 스킬 본체(.skill 내부 구조와 동일)
    ├── SKILL.md              # 스킬 설명·규칙(트리거/Critical Rules) ★버전의 단일 출처
    ├── assets/               # 기준 양식(SSOT) 및 참고 양식
    │   ├── kasa-standard-report.hwpx
    │   ├── reference-form-spacing.hwpx
    │   └── sample-report.hwpx
    ├── hooks/                # Claude Code PreToolUse 가드 훅 3종(선택 설치)
    │   ├── finalize_guard.py # 산출물 전달 전 validate --kasa 통과 강제
    │   ├── sample_guard.py   # 견본/placeholder 문서 오인 전달 차단
    │   ├── spec_guard.py     # 필수 정보(제목·작성정보·발행시기) 질문 강제
    │   └── README.md         # 등록 방법(.claude/settings.json)
    ├── references/           # 스타일/구조 레퍼런스 문서
    └── scripts/              # 빌드·검증 엔진(파이썬 표준 라이브러리)
        ├── build_report.py   # JSON 사양 → 보고서 HWPX
        ├── validate.py       # 구조·KASA 규정·회귀 점검(표기법 lint 통합)
        ├── kasa_lint.py      # KASA 표기법 lint(날짜·시간·숫자·기호·위계)
        ├── extract_text.py   # 본문 텍스트 추출(검수용)
        ├── redraft.py        # 재기안: 기존 HWPX 서식 보존 본문 치환
        ├── hwpx_diff.py      # 신구대조: 두 HWPX 문단·표 셀 diff(읽기 전용)
        ├── label_fill.py     # 라벨 기반 양식 채우기("성명:" 옆 빈 셀)
        ├── hwpx_edit.py      # in-place 편집: 머리말·꼬리말·쪽번호·표 구조 op
        ├── hwpx_image.py     # 직인/서명 이미지 삽입·교체·삭제(BinData+manifest+pic)
        ├── secure_fill.py    # PII 비경유 양식 채우기(detect/fill/verify/shred)
        ├── fix_vertical.py   # 세로쓰기 오변환 자동보정(다수결 flip)
        ├── kasa_lib.py       # 핵심 엔진(PrvText 재생성 포함)
        └── office/           # HWPX(zip) 패킹/언패킹 보조
```

## 사용법

보고서 생성(JSON 사양 → HWPX):

```bash
python3 kasa-hwpx/scripts/build_report.py \
  --spec spec.json \
  --output 보고서.hwpx
```

생성물 검증(구조·KASA 규정·줄겹침/자동번호 회귀·표기법 점검):

```bash
python3 kasa-hwpx/scripts/validate.py 보고서.hwpx --kasa
python3 kasa-hwpx/scripts/kasa_lint.py 보고서.hwpx --strict   # 표기법만 따로(경고 시 exit 1)
```

표기법 lint는 공문서 표기 원칙(행정업무운영 편람)을 KASA 보고서에 맞게 점검합니다 —
날짜 `2026. 7. 7.`(온점+공백, 앞 0 제거, `’YY.MM.DD.` 축약 허용), 요일 괄호 붙임(`7. 7.(화)`),
시간 24시각제 쌍점·두 자리(`08:09`), 4자리 이상 숫자의 천 단위 쉼표(연도 제외),
항목 기호 □/ㅇ/-/※/* 위계(유사 기호·위계 역전 탐지), 물결표(`~`·`∼`) 붙여쓰기,
쌍점 뒤 한 칸 띄움.

신구대조(재기안 전후 검수 — 문단·표 셀 단위 비교, 읽기 전용):

```bash
python3 kasa-hwpx/scripts/hwpx_diff.py 구버전.hwpx 신버전.hwpx
# 통계: 추가 1 · 삭제 0 · 수정 2 · 동일 40  +  [수정] 표 셀(2,1): '88,000' → '92,000' …
```

라벨 기반 양식 채우기(`{{자리표시자}}` 없는 표 양식 — "성명:" 옆 빈 셀 자동 입력):

```bash
python3 kasa-hwpx/scripts/label_fill.py detect 양식.hwpx        # 라벨·채울 위치 미리보기
python3 kasa-hwpx/scripts/label_fill.py fill   양식.hwpx --data d.json --output 결과.hwpx
```

재기안(기존 HWPX의 서식을 보존한 채 본문만 치환):

```bash
# repl.json 예: {"2025년": "2026년", "(부서명)": "우주수송정책과"}
python3 kasa-hwpx/scripts/redraft.py --input 원본.hwpx --map repl.json --output 결과.hwpx
```

재기안은 모든 섹션을 처리하고, 키별 치환 건수를 출력하며 미적중 키를 경고합니다.
미변경 zip 엔트리는 원본 메타데이터 그대로 유지됩니다(서식 보존).

in-place 편집(머리말·꼬리말·쪽번호·표 구조, 서식 보존):

```bash
python3 kasa-hwpx/scripts/hwpx_edit.py set-footer  문서.hwpx --text "꼬리말" --output 결과.hwpx
python3 kasa-hwpx/scripts/hwpx_edit.py set-pagenum 문서.hwpx --pos BOTTOM_CENTER --output 결과.hwpx
python3 kasa-hwpx/scripts/hwpx_edit.py list-tables 문서.hwpx        # 표 순번 확인
python3 kasa-hwpx/scripts/hwpx_edit.py set-cell    문서.hwpx --table 3 --row 0 --col 0 --bg D9D9D9 --output 결과.hwpx
python3 kasa-hwpx/scripts/hwpx_edit.py merge-cells 문서.hwpx --table 3 --from 0,0 --to 1,0 --output 결과.hwpx
```

직인/서명 등 이미지 삽입·교체·삭제(BinData·manifest·`<hp:pic>` 일괄 처리, 서식 보존):

```bash
python3 kasa-hwpx/scripts/hwpx_image.py list    문서.hwpx           # id·참조 수 확인(선행 권장)
python3 kasa-hwpx/scripts/hwpx_image.py add     문서.hwpx --image 직인.png --anchor "(직인)" \
                                                --replace-anchor --width-mm 20 --output 결과.hwpx
python3 kasa-hwpx/scripts/hwpx_image.py replace 문서.hwpx --id image2 --image 새직인.png --output 결과.hwpx
python3 kasa-hwpx/scripts/hwpx_image.py remove  문서.hwpx --id image2 --output 결과.hwpx
```

`add`는 앵커 텍스트가 있는 문단에 글자취급(treatAsChar) 그림을 넣고, `--replace-anchor`는
양식의 "(직인)" 자리 문구를 지우고 그 자리에 넣습니다(png/jpg/gif/bmp, 한 변만 지정 시 비율 유지).
머리말 안 그림(KASA MI 로고)의 제거는 `--force` 없이 거부됩니다.

개인정보 비노출 양식 채우기(secure-fill)와 세로쓰기 오변환 보정:

```bash
python3 kasa-hwpx/scripts/secure_fill.py fill 양식.hwpx --profile p.json --output 결과.hwpx
python3 kasa-hwpx/scripts/secure_fill.py shred p.json               # 프로필 안전 삭제
python3 kasa-hwpx/scripts/fix_vertical.py --input 변환본.hwpx --output 보정본.hwpx
```

## Claude Code 가드 훅 (선택 설치)

`kasa-hwpx/hooks/`의 PreToolUse 훅 3종을 등록하면 (a) 규정 미통과 산출물 전달,
(b) 견본·placeholder 문서 오인 전달, (c) 필수 정보 미확보 상태의 생성 실행이
**도구 실행 전에** 차단됩니다(exit 2 → Claude가 stderr 사유를 읽고 질문·교정 후 재시도,
훅 내부 오류는 fail-open). 등록 방법은 [kasa-hwpx/hooks/README.md](kasa-hwpx/hooks/README.md) 참고.
훅이 없어도 스킬은 동작합니다.

## 테스트

```bash
python3 -m unittest discover -s tests    # 회귀 테스트(표준 라이브러리 unittest)
```

빌드 결정성(엔트리 바이트 동일)·KASA 규정 통과·재기안 서식/zip 메타데이터 보존·
PrvText 본문 반영·검증기 탐지(세로쓰기 오변환/PrvText 미반영)·표기법 lint(규칙 단위 +
기준양식/산출물 무경고)·in-place 편집(머리말/꼬리말/쪽번호/표 구조 op와 가드)·
표 스타일(정렬 분리·행 높이 동일화)·이미지 삽입/교체/삭제(BinData·manifest·pic 일관성,
MI 보호)·신구대조(문단/셀 diff)·라벨 양식 채우기·secure-fill(값 비노출)·
PreToolUse 가드 훅(차단/통과 조건)·office unpack→repack 왕복 바이트 보존을 잠근다(121케이스).
`tests/`는 저장소 전용이며 `.skill` 패키지에는 포함되지 않는다.

## 스킬 패키징

```bash
python3 build_skill.py        # → dist/kasa-hwpx_v{버전}.skill 생성 (버전은 SKILL.md에서 읽음)
```

생성된 `kasa-hwpx_v{버전}.skill`을 스킬 디렉터리에 풀어 넣거나 앱의 스킬 가져오기로 등록합니다.
`dist/`는 git 추적에서 제외되며(빌드 산출물), 파일명의 버전으로 배포본을 식별합니다 —
버전 식별이 불가능했던 고정 파일명 배포가 v0.5.0 롤백 사건의 원인이었습니다.

## 핵심 설계 메모

- 본문 흐름 문단에는 줄 위치 캐시(`linesegarray`)를 넣지 않아 한글이 열 때 재계산 → 줄 겹침 방지.
- 본문을 바꾸는 모든 경로(빌드·재기안·치환)는 미리보기(`Preview/PrvText.txt`)를 본문 기반으로 재생성.
- in-place 편집(hwpx_edit)은 중첩 표 포함 표 전체·병합(span) 표의 구조 op을 가드로 거부.
- secure-fill은 개인정보 값을 화면·로그·예외에 노출하지 않음(detect/fill/verify는 마스킹, shred로 폐기).
- 세로쓰기 오변환 보정은 다수결(VERTICAL>HORIZONTAL)일 때만 자동 flip — 부분 세로쓰기는 보호.
- 본문 위계는 **선행 공백(항목 시작) + 내어쓰기(2줄 이상, 첫 글자 정렬)**. 첫 줄 시작은 항상 0.
- 좌여백 paraPr이 모두 OUTLINE(자동번호)이라, 무번호·무내어쓰기 paraPr을 빌드 시 헤더에 주입.
- 항목 앞 간격은 빈 문단(스페이서)으로 부여(□ 15pt, ㅇ 10pt, - 5pt, ※/* 3pt).
- 표 내부는 내어쓰기를 적용하지 않음. 긴 제목은 2줄 자동 줄바꿈.
- 서식 보존 편집(재기안·치환)은 미변경 zip 엔트리의 원본 메타데이터(ZipInfo)를 그대로 유지.
- 재기안은 `<hp:t>` 내 컨트롤 태그(mixed content)를 보존한 채 텍스트 구간만 치환.
- 검증기는 세로쓰기 오변환·표 셀 과밀·header `itemCnt` 정합·표기법(kasa_lint)까지 점검.
- 이미지 삽입은 기준 양식 MI 로고의 `<hp:pic>`에서 추출한 **검증된 패턴**만 사용 —
  실물 패턴이 없는 구조(예: 네이티브 각주)는 창작하지 않는다(안전성 최우선, BACKLOG 4번 제외 사유).
- `write_package_preserving`은 미변경 엔트리의 ZipInfo를 보존하며 additions/removals로
  엔트리 추가·삭제(이미지 등록/제거)까지 서식 보존 경로 안에서 처리.
- 가드 훅은 stdin 이벤트 JSON → exit 0/2(stderr 사유) 규약, 훅 내부 오류는 fail-open.
- 자세한 규칙은 `kasa-hwpx/SKILL.md` 참고.

## 버전 히스토리

커밋은 [Conventional Commits](https://www.conventionalcommits.org), 태그는 [SemVer](https://semver.org)를 따릅니다.
**현재 버전: `v0.8.1`** (버전의 단일 출처는 `kasa-hwpx/SKILL.md` 프런트매터의 `version` 필드이며,
빌드 산출물 이름(`dist/kasa-hwpx_v{버전}.skill`)에 자동 반영됩니다.)

- `v0.1.0` feat: 초기 버전 — 생성 엔진·검증기·기준 양식
- `v0.1.1` fix: 줄겹침(linesegarray) 해결 + 참고 머리 3칸 표 디자인
- `v0.2.0` feat: 선행 공백 + 내어쓰기 기반 본문 위계
- `v0.3.0` feat: 항목 간격·긴 제목 2줄·표 내어쓰기 제외·참고 서식 통일
- `v0.4.0` feat: 재기안(`redraft.py`) — 기존 HWPX 서식 보존 본문 치환 / docs: 쉬운 사용설명서 추가
- ~~`v0.5.0`~~ **롤백됨** — 업스트림 반영 직후 항목 간 공백·참고 서식 소실 결함이 보고되어 main에서
  일시 제외. 이후 검증에서 코드 무죄 확인(산출물이 v0.4.1과 바이트 동일), 원인은 버전 식별이
  불가능했던 구 배포 체계(고정 파일명 `.skill`)의 stale 배포본으로 판명
- `v0.4.1` docs/build: MIT LICENSE 명시, 버전 표기 체계·빌드 산출물 버전 네이밍 도입
- `v0.5.1` feat: `v0.5.0` 업스트림 반영분 재릴리스 — 재기안 가드레일(전 섹션·mixed content 보호·미적중 키 경고), zip 메타데이터 보존 기록, 검증 강화(세로쓰기 오변환·표 셀 과밀·itemCnt 정합)
- `v0.6.0` feat: 업스트림(jkf87/hwpx-skill 6월 스프린트) 반영 2차 — PrvText 본문 재생성+미반영 탐지,
  회귀 테스트 스위트(47케이스), 세로쓰기 오변환 자동보정(`fix_vertical.py`),
  머리말·꼬리말·쪽번호·표 구조 in-place 편집(`hwpx_edit.py`), PII 비경유 secure-fill(`secure_fill.py`)
- `v0.7.0` feat: 업스트림 반영 3차 — KASA 표기법 lint(`kasa_lint.py`, validate 통합),
  Claude Code PreToolUse 가드 훅 3종(`hooks/`), 직인/서명 이미지 삽입·교체·삭제(`hwpx_image.py`),
  unpack→repack 왕복 바이트 보존 회귀 잠금(총 94케이스), 작업 연속성 문서(AGENTS.md/CLAUDE.md).
  rc1 빌드를 한글 실물 열람으로 검증 후 승격(직인 삽입 렌더 정상 확인).
  네이티브 각주·하이퍼링크는 검증된 실물 패턴 부재로 **제외 확정**(공문서 안전성 최우선, BACKLOG 참고)
- `v0.7.1` fix: 표 데이터 행 높이 동일화(접히는 셀 기준 전 행 통일) + 숫자 셀만 우측 정렬
  (일반 텍스트는 기본 정렬, paraPr 29 주입) — 실물 보고서(국내여비 증액) 확인 후 반영,
  회귀 테스트 101케이스
- `v0.8.0` feat: kordoc(chrisryugj) 아이디어 반영 1차 — 신구대조(`hwpx_diff.py`,
  문단·표 셀 diff), 라벨 기반 양식 채우기(`label_fill.py`), 표기법 lint 보강(시각 두 자리·
  쌍점 띄움·`∼` 인식·요일 괄호). 실물 예시 보고서 확인 후 릴리스, 회귀 테스트 121케이스
- `v0.8.1` docs: 범용 GenAI 플랫폼 중립화 — AGENTS.md 7장(플랫폼 호환 원칙)·GEMINI.md 신설,
  SKILL.md 주어 일반화·타 플랫폼 수동 게이트 명시. 코드 무변경(렌더 경로 영향 없음 —
  rc 열람 생략), 회귀 테스트 121케이스 **(현재)**

### 커밋 규약

```
<type>(<scope>): <subject>

<body>
```

- type: `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `chore` 등
- scope(예): `skill`, `layout`, `table`, `appendix`, `validate`, `build`
- 예: `fix(layout): linesegarray 캐시 제거로 본문 줄 겹침 해결`

## 라이선스

이 저장소의 코드(빌드·검증 엔진, 스크립트, 문서)는 **[MIT License](LICENSE)**를 따릅니다.
[hwpx-rekian](https://github.com/ai-public-peasant/hwpx-rekian) 등 원작 스킬이 MIT License를 적용하고 있으므로,
**각 하위 디렉터리에 별도 LICENSE 파일이 있는 경우 해당 파일의 라이선스를 우선 확인하세요.**

다만 `kasa-hwpx/assets/`에 포함된 우주항공청(KASA) 표준양식·로고 등 자산의 권리는 아래 우주항공청 저작권 정책을 따릅니다.

이 저작물은 대한민국의 국가기관 또는 지방자치단체가 업무상 작성하여 공표하였거나 계약에 따라 저작재산권의 전부를 보유하고 있습니다. [대한민국 저작권법](https://law.go.kr/%EB%B2%95%EB%A0%B9/%EC%A0%80%EC%9E%91%EA%B6%8C%EB%B2%95) 제24조의2에 따라, 이러한 저작물은 저작권자에게 별도의 허락을 받을 필요 없이 복제·변경·재배포·2차적저작물의 작성 및 이용 등의 자유로운 이용이 영리적 목적을 포함하여 허용됩니다.

출처: [우주항공청 저작권 정책](https://www.kasa.go.kr/prog/bbsArticle/BBSMSTR_000000000190/view.do?bbsId=BBSMSTR_000000000190&nttId=B000000001923Bi6xJ7) · [공공누리 유형 안내](https://www.kogl.or.kr/info/licenseType2.do)

## 기여자 (Contributors)

| 기여자 | 역할 |
| --- | --- |
| [Engineering-Excellence](https://github.com/Engineering-Excellence) (Kyle) | 메인테이너 · KASA 표준보고서 엔진 |
| [Canine89 / 박현규](https://github.com/Canine89/hwpxskill) | 원본 `hwpx` 스킬 제작자 — XML 직접 제어 방식의 기반 · zip 바이트 보존·finalize 가드 참고 |
| [ai-public-peasant](https://github.com/ai-public-peasant) | [hwpx-rekian](https://github.com/ai-public-peasant/hwpx-rekian) 제작자 — 재기안(re-draft) 기능 설계·XML 가드레일 참고 |
| [jkf87](https://github.com/jkf87) | hwpx-skill 접근법 참고 — 네임스페이스 후처리·secPr 보존·mimetype STORED·워크플로우 트리·세로쓰기 오변환 가드 |
| [chrisryugj](https://github.com/chrisryugj) | [kordoc](https://github.com/chrisryugj/kordoc) 제작자 — 신구대조(compare)·라벨 인식 양식 채우기 아이디어, 공문서 표기법 레퍼런스(행정업무운영 편람 정리) 참고 |
| [Claude](https://github.com/claude) (Anthropic) | AI 페어 — 엔진·문서 작성 보조 |
