# kasa-hwpx

우주항공청(KASA) 표준보고서를 한글 **HWPX(.hwpx)**로 생성·편집·검증하는 Claude/Cowork **Skill**입니다.
표준양식(표지·MI 로고·편집용지)을 그대로 보존하고 본문만 채워, 규정에 맞는 보고서를 외부 패키지 없이
파이썬 표준 라이브러리만으로 만듭니다.

## 저장소 구조

```
.
├── README.md
├── .gitignore
├── build_skill.py            # kasa-hwpx/ → kasa-hwpx.skill 패키징
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
        ├── kasa_lib.py       # 핵심 엔진
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

## 스킬 패키징

```bash
python3 build_skill.py        # → dist/kasa-hwpx.skill 생성
```

생성된 `kasa-hwpx.skill`을 스킬 디렉터리에 풀어 넣거나 앱의 스킬 가져오기로 등록합니다.

## 핵심 설계 메모

- 본문 흐름 문단에는 줄 위치 캐시(`linesegarray`)를 넣지 않아 한글이 열 때 재계산 → 줄 겹침 방지.
- 본문 위계는 **선행 공백(항목 시작) + 내어쓰기(2줄 이상, 첫 글자 정렬)**. 첫 줄 시작은 항상 0.
- 좌여백 paraPr이 모두 OUTLINE(자동번호)이라, 무번호·무내어쓰기 paraPr을 빌드 시 헤더에 주입.
- 항목 앞 간격은 빈 문단(스페이서)으로 부여(□ 15pt, ㅇ 10pt, - 5pt, ※/* 3pt).
- 표 내부는 내어쓰기를 적용하지 않음. 긴 제목은 2줄 자동 줄바꿈.
- 자세한 규칙은 `kasa-hwpx/SKILL.md` 참고.

## 버전 히스토리

커밋은 [Conventional Commits](https://www.conventionalcommits.org), 태그는 [SemVer](https://semver.org)를 따릅니다.

- `v0.1.0` feat: 초기 버전 — 생성 엔진·검증기·기준 양식
- `v0.1.1` fix: 줄겹침(linesegarray) 해결 + 참고 머리 3칸 표 디자인
- `v0.2.0` feat: 선행 공백 + 내어쓰기 기반 본문 위계
- `v0.3.0` feat: 항목 간격·긴 제목 2줄·표 내어쓰기 제외·참고 서식 통일

### 커밋 규약

```
<type>(<scope>): <subject>

<body>
```

- type: `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `chore` 등
- scope(예): `skill`, `layout`, `table`, `appendix`, `validate`, `build`
- 예: `fix(layout): linesegarray 캐시 제거로 본문 줄 겹침 해결`

## 라이선스

저장소 소유자가 적절한 라이선스를 추가하세요(예: `LICENSE` 파일). 기준 양식·로고 등 자산의
사용 권한은 우주항공청 관련 규정을 따릅니다.
