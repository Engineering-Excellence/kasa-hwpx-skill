# BACKLOG — 미반영 잔여 후보

v0.6.0(2026-07-07) 릴리스 기준, 업스트림 조사에서 반영하기로 합의했으나 아직 착수하지 않은
항목들이다. 어느 머신에서든 이 파일과 README의 버전 이력만 보면 이어서 작업할 수 있다.

## 잔여 후보 (중간 우선순위, 위에서부터 권장 순서)

1. ~~**KASA 표기법 lint**~~ — **완료(2026-07-07)**: `kasa_lint.py` 신설(날짜·시간·숫자·
   항목 기호·위계·물결표 규칙) + `validate.py --kasa` 통합 + 회귀 테스트 18케이스.
2. ~~**PreToolUse 가드 훅 3종**~~ — **완료(2026-07-07)**: `kasa-hwpx/hooks/`에
   finalize_guard(전달 전 validate --kasa 강제)·sample_guard(견본/placeholder 오인 전달
   차단)·spec_guard(필수 정보 질문 강제) + 등록 안내 README + 회귀 테스트 14케이스.
3. **직인/서명·이미지 삽입·편집 (P12/P13)** — BinData 등록 + `<hp:pic>` 앵커 삽입.
   기존 이미지 교체·삭제 포함. write_package_preserving 경로 유지 필수.
4. **네이티브 각주·하이퍼링크 (P4)** — 현재 텍스트 병기 방식을 `<hp:footNote>`,
   `<hp:fieldBegin type="HYPERLINK">` 네이티브 구조로 대체.
5. ~~**Canine89 unpack 바이트 보존 점검**~~ — **완료(2026-07-07)**: unpack→repack 왕복
   바이트 동일성·mimetype 규칙·단일 엔트리 수정 시 나머지 보존을 회귀 테스트 4케이스로 잠금
   (`tests/test_office_roundtrip.py`).

## 제외 판단 (재론 시 사용자 결정 필요)

- 수식·차트·도형·테마 지원: KASA 표준양식이 고정이라 수요 없음.
- 문서 유형 확장(기안문·보도자료·계획서): 스킬 스코프 확대라 별도 결정 필요.
- py3.9 호환 작업: 해당 없음(스크립트에 3.10+ 문법 미사용 확인, 2026-07-07).

## 업스트림 관찰 시점 (다음 동기화 때 이 커밋 이후분만 확인)

| 저장소 | 마지막 확인 커밋 | 시점 |
| --- | --- | --- |
| jkf87/hwpx-skill | `48cf9ab` | 2026-06-30 |
| Canine89/hwpxskill | `cb5f25b` | 2026-06-27 |
| ai-public-peasant/hwpx-rekian | `e151c96` | 2026-04-09 |

## 작업 시작 절차

```bash
git clone https://github.com/Engineering-Excellence/kasa-hwpx-skill.git
cd kasa-hwpx-skill
python3 -m unittest discover -s tests   # 83개 통과 확인 (Python 3.10+, 외부 의존성 없음)
```

기능 1개 = 커밋 1개(Conventional Commits, 한국어 제목), 회귀 테스트 동반 추가,
`tests/`는 `.skill` 패키지에 미포함 — 기존 관례를 따른다.
