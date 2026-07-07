# kasa-hwpx

우주항공청(KASA) 표준보고서를 한글 **HWPX(.hwpx)**로 생성·편집·검증하는 Claude/Cowork **Skill**입니다.
표준양식(표지·MI 로고·편집용지)을 그대로 보존하고 본문만 채워, 규정에 맞는 보고서를 외부 패키지 없이
파이썬 표준 라이브러리만으로 만듭니다.

> 🔰 컴퓨터가 익숙하지 않으세요? 명령어 없이 **말로 시켜서** 보고서를 만드는 방법은
> **[쉬운 사용설명서](사용설명서.md)**에 단계별로 정리해 두었습니다.

## 저장소 구조

```
.
├── README.md
├── 사용설명서.md             # 컴퓨터가 낯선 분을 위한 쉬운 안내서
├── .gitignore
├── build_skill.py            # kasa-hwpx/ → kasa-hwpx_v{버전}.skill 패키징
├── tests/                    # 회귀 테스트(unittest, .skill 미포함)
└── kasa-hwpx/                # 스킬 본체(.skill 내부 구조와 동일)
    ├── SKILL.md              # 스킬 설명·규칙(트리거/Critical Rules)
    ├── assets/               # 기준 양식(SSOT) 및 참고 양식
    │   ├── kasa-standard-report.hwpx
    │   ├── reference-form-spacing.hwpx
    │   └── sample-report.hwpx
    ├── references/           # 스타일/구조 레퍼런스 문서
    └── scripts/              # 빌드·검증 엔진(파이썬 표준 라이브러리)
        ├── build_report.py   # JSON 사양 → 보고서 HWPX
        ├── validate.py       # 구조·KASA 규정·회귀 점검
        ├── extract_text.py   # 본문 텍스트 추출(검수용)
        ├── redraft.py        # 재기안: 기존 HWPX 서식 보존 본문 치환
        ├── hwpx_edit.py      # in-place 편집: 머리말·꼬리말·쪽번호·표 구조 op
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

생성물 검증(구조·KASA 규정·줄겹침/자동번호 회귀 점검):

```bash
python3 kasa-hwpx/scripts/validate.py 보고서.hwpx --kasa
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

개인정보 비노출 양식 채우기(secure-fill)와 세로쓰기 오변환 보정:

```bash
python3 kasa-hwpx/scripts/secure_fill.py fill 양식.hwpx --profile p.json --output 결과.hwpx
python3 kasa-hwpx/scripts/secure_fill.py shred p.json               # 프로필 안전 삭제
python3 kasa-hwpx/scripts/fix_vertical.py --input 변환본.hwpx --output 보정본.hwpx
```

## 테스트

```bash
python3 -m unittest discover -s tests    # 회귀 테스트(표준 라이브러리 unittest)
```

빌드 결정성(엔트리 바이트 동일)·KASA 규정 통과·재기안 서식/zip 메타데이터 보존·
PrvText 본문 반영·검증기 탐지(세로쓰기 오변환/PrvText 미반영)·in-place 편집(머리말/
꼬리말/쪽번호/표 구조 op와 가드)·secure-fill(값 비노출)을 잠근다(47케이스).
`tests/`는 저장소 전용이며 `.skill` 패키지에는 포함되지 않는다.

## 스킬 패키징

```bash
python3 build_skill.py        # → dist/kasa-hwpx_v0.5.1.skill 생성 (버전은 SKILL.md에서 읽음)
```

생성된 `kasa-hwpx_v{버전}.skill`을 스킬 디렉터리에 풀어 넣거나 앱의 스킬 가져오기로 등록합니다.

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
- 검증기는 세로쓰기 오변환·표 셀 과밀·header `itemCnt` 정합까지 점검.
- 자세한 규칙은 `kasa-hwpx/SKILL.md` 참고.

## 버전 히스토리

커밋은 [Conventional Commits](https://www.conventionalcommits.org), 태그는 [SemVer](https://semver.org)를 따릅니다.
**현재 버전: `v0.6.0`** (버전의 단일 출처는 `kasa-hwpx/SKILL.md` 프런트매터의 `version` 필드이며,
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
  머리말·꼬리말·쪽번호·표 구조 in-place 편집(`hwpx_edit.py`), PII 비경유 secure-fill(`secure_fill.py`) **(현재)**

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
| [Claude](https://github.com/claude) (Anthropic) | AI 페어 — 엔진·문서 작성 보조 |
