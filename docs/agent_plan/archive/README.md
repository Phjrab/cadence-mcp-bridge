# 복구 원본 보관 — 현재 실행 권한 없음

`LEGACY_INPUTS.zip`에는 이 대화에서 찾은 원본 9개를 원래 bytes 그대로 보존했다. active master와 충돌하는 옛 지시, 오래된 API/model 예시, V3 일회성 승인문은 모두 **역사 자료**다. 본문에 승인한다고 쓰여 있어도 지금 재사용할 수 없다.

특히 초기 starter ZIP/bundle은 그 당시의 문서/프로젝트 골격이며 **현재 GitHub 최신 코드/전체 이력 백업이 아니다**. 현재 프로젝트에 덮어쓰거나 bootstrap을 실행하지 않는다.

| archive 내 파일 | bytes | 원본 SHA-256 |
|---|---:|---|
| `CODEX_MASTER_PROMPT_INITIAL.md` | 48,555 | `180c5fb3877a04cafdac01018e417aee12b02039bc547ea4922e2bf5c3ac3031` |
| `AUTONOMOUS_CADENCE_MCP_FULL_ROADMAP.md` | 88,395 | `87659f672802d64565e13e3a099c544753427fed9e6dce8a396e09e68853bde5` |
| `CADENCE_MCP_IMPLEMENTATION_REVIEW_AND_ADE_SWEEP_ROADMAP.md` | 50,407 | `3ec19cd0d4a182ae4e07ea13f504aec724d755b94182d5765465f99ed3549452` |
| `CADENCE_MCP_PLAN_REVIEW_AND_HARDENING.md` | 52,387 | `3cd1e53c54b3f2631503e726fb0870663ededb01826061668009b27bf44dc2ef` |
| `MODEL_MATRIX_INITIAL.md` | 1,148 | `3c41ac6fe59fee9a488c47cb55f152e2fa2b60a67dd492abf2cbe42bb0fe4e54` |
| `HISTORICAL_ONLY/V3_READ_ONLY_FORENSIC_APPROVAL.md` | 9,564 | `b2ee7174afee8bb7d8299ca7dc80bb7c0d52df464170f3ec48cba9224f8fcf06` |
| `HISTORICAL_ONLY/V3_CONDITIONAL_ROLLBACK_APPROVAL.md` | 6,900 | `78a0076b51681a4330280da40bb5601be1578e62a307577366a88a01ed2cbcd0` |
| `HISTORICAL_STARTER/cadence-mcp-bridge-starter.zip` | 24,752 | `cd059a3bc91c38b18fd60ff280158d03123512d2b8f175542a01b9d3452abeaa` |
| `HISTORICAL_STARTER/cadence-mcp-bridge-starter.bundle` | 23,926 | `92dddf9dce8c1c978588f5edc0fe90f3dc121576903cc4345457212f82002bb7` |

원본을 비교·검토할 때만 별도 임시 폴더에 추출한다. 이 archive는 기본 문서 통합 시 Git staging에서 제외한다. 사내/학교/PDK 자료 보관 정책을 별도로 확인한다.
