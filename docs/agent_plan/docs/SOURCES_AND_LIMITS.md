# 근거·복구 출처·현재 확인 한계

## 1. 내부 자료

현재 대화의 파일 목록과 원본 내용에서 다음을 복구했다. 원본은 archive ZIP 안에 raw bytes로 보존했다.

| `CODEX_MASTER_PROMPT_INITIAL.md` | 48,555 | `180c5fb3877a04cafdac01018e417aee12b02039bc547ea4922e2bf5c3ac3031` |
| `AUTONOMOUS_CADENCE_MCP_FULL_ROADMAP.md` | 88,395 | `87659f672802d64565e13e3a099c544753427fed9e6dce8a396e09e68853bde5` |
| `CADENCE_MCP_IMPLEMENTATION_REVIEW_AND_ADE_SWEEP_ROADMAP.md` | 50,407 | `3ec19cd0d4a182ae4e07ea13f504aec724d755b94182d5765465f99ed3549452` |
| `CADENCE_MCP_PLAN_REVIEW_AND_HARDENING.md` | 52,387 | `3cd1e53c54b3f2631503e726fb0870663ededb01826061668009b27bf44dc2ef` |
| `MODEL_MATRIX_INITIAL.md` | 1,148 | `3c41ac6fe59fee9a488c47cb55f152e2fa2b60a67dd492abf2cbe42bb0fe4e54` |
| `HISTORICAL_ONLY/V3_READ_ONLY_FORENSIC_APPROVAL.md` | 9,564 | `b2ee7174afee8bb7d8299ca7dc80bb7c0d52df464170f3ec48cba9224f8fcf06` |
| `HISTORICAL_ONLY/V3_CONDITIONAL_ROLLBACK_APPROVAL.md` | 6,900 | `78a0076b51681a4330280da40bb5601be1578e62a307577366a88a01ed2cbcd0` |
| `HISTORICAL_STARTER/cadence-mcp-bridge-starter.zip` | 24,752 | `cd059a3bc91c38b18fd60ff280158d03123512d2b8f175542a01b9d3452abeaa` |
| `HISTORICAL_STARTER/cadence-mcp-bridge-starter.bundle` | 23,926 | `92dddf9dce8c1c978588f5edc0fe90f3dc121576903cc4345457212f82002bb7` |

원래 마스터는 초기 starter 시점의 snapshot이다. 이를 현재 repository 계약/진척도/실권한 백업이라고 부르지 않는다. 실제 원격 코드의 immutable plan 파일 원본을 현재 환경에서 새로 확보한 것도 아니다.

## 2. 현재 저장소 한계

2026-09-05 연결된 GitHub로 `Phjrab/cadence-mcp-bridge` metadata를 조회했으나 404가 반환되었다. 현재 HEAD, visibility, 새 WP/PR 상태는 재확인하지 못했다. 404만으로 삭제/Private/접속 해제를 단정하지 않는다.

2026-08-31 기록에는 v1.0.0, 고정 transient netlist replay, 22 typed MCP tools, V4 검증 완료 등의 기록이 있다. 이번 패키지 제작에서 실제 Windows/CentOS/Cadence 테스트는 수행하지 않았다. 사용자가 최신 local checkout에서 상태를 확인하도록 통합 프롬프트에 포함했다.

이 패키지는 설계와 문서의 복구/통합이다. 실제 기능 코드/배포/승인 발급/rollback/계측/MPW 제출/GitHub commit-push를 수행하지 않았다.

## 3. 공식 공개 참고자료

아래는 2026-09-05 문서 작성 중 확인한 공개 1차 자료다. 레거시 환경의 정확한 API 지원은 설치된 도움말과 실제 capability 시험이 우선이다.

- [E1] OpenAI 공식 Codex model 안내. GPT-5.6 Sol/Terra/Luna, 실제 model 선택과 effort 관련 안내. 이 package의 작업별 배정은 설계 제안이며 계정 entitlement 보증이 아니다.
  `https://developers.openai.com/codex/models/`
  당시 연결 대상: `https://learn.chatgpt.com/docs/models`
- [E2] OpenAI 공식 Codex MCP 안내. 현재 지원되는 설치/구성 방법의 확인 출처.
  `https://developers.openai.com/codex/mcp/`
- [E3] Model Context Protocol 공식 Security Best Practices. local process/권한 경계와 안전 고려사항의 확인 출처.
  `https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices`
- [E4] Cadence Community, “Basics of PDK”, Cadence의 generic PDK 설명. GPDK090의 flow 검증과 실제 제조 공정 signoff를 구분한다.
  `https://community.cadence.com/cadence_technology_forums/f/custom-ic-design/36796/basics-of-pdk/1349734`

과거 review 문서에 포함된 상세 Cadence/CDF/MC/strobe/GDS 참조는 복구 원본에 남아 있다. 이를 최신 설치의 모든 옵션이 검증됐다는 뜻으로 사용하지 않는다.

## 4. 통합 시 수정한 주요 오해

1. `PROJECT_STATE.md`가 없으면 WP-00으로 돌아가는 규칙을 제거하고 이력 복구를 우선한다.
2. 서로 다른 WP-12 의미를 새 stable ICF ID와 alias/evidence로 연결한다.
3. model 이름·SDK major를 오래된 문서만 보고 설치/승격하지 않는다. lockfile/current API 우선.
4. master/state가 있다는 사실과 실제 ADE runtime 실행을 분리한다.
5. count를 회로 의미 fingerprint로 취급하지 않는다.
6. apply 뒤 기록 대신 첫 write 이전 intent journal과 보호된 staging을 선행한다.
7. source/PDK raw 데이터 공개 금지와 승인된 typed design graph 관찰을 구분한다.
8. GPDK demonstration과 target fabrication/signoff/submission 상태를 분리한다.
9. PDK adapter/복구/DRC-LVS probe/백업을 후반에서 앞으로 이동한다.
10. 사람 승인 없는 runtime 권한 확대나 역사 승인 replay를 막는다.

## 5. 정확한 범위

- 16개 phase, 120개 새 작업 프롬프트: 계획이며 구현 수 아님.
- 170개 원래 capability 대응: 범위 보존이며 완료 수 아님.
- 21개 hardening 요구사항: traceability이며 실제 시험 통과 수 아님.
- file/hash/ID/DAG 검증: 문서 패키지 품질 검증이며 Cadence·security·signoff 인증 아님.
- package version `2.0.0`: 문서 버전이며 software v2.0.0 릴리스 아님.
