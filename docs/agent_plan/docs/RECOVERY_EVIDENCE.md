# 실행 journal·복구·증거·상태 머신

## 1. 예전 실패에서 바꿔야 할 점

V3 등 과거 기록에는 apply 후 exact-diff 실패로 최종 manifest/audit에 도달하지 못한 상태가 있었다. 최종 성공 때만 evidence를 만들면 실패 직후 실제 상태를 모른다.

신규 작업은 **첫 부작용 이전에 기록을 시작**한다.

```text
VALIDATED_PLAN → INTENT_DURABLE → BASELINE_CAPTURED
→ BACKUP_VERIFIED → APPLY_STARTED → APPLY_OBSERVED
→ DIFF_VERIFIED → [APPROVED_ROLLBACK or STAGING_VALIDATED]
→ FINAL_VERIFIED → MANIFEST_FINALIZED
```

각 transition에 event sequence, run ID, input/executor digest, target identity, previous state, stage result를 기록한다. final manifest는 journal을 요약하는 완료 증거이고 journal을 대체하지 않는다.

## 2. 저장 모델

```text
protected_runtime/
  approvals/           # operator-owned, runtime agent cannot edit
  projects/<logical-id>/
    revisions/<id>/    # immutable parent, explicit staging state
    campaigns/<id>/
      plan.json
      request-digest
      children.json
      state.json
      journal.jsonl
      manifests/
      artifacts/       # exact IDs and content hash
```

위 구조는 논리 예시이며 실제 filesystem root는 operator config로 결정한다. MCP 입력에서 absolute path를 받지 않는다.

Windows에서 modern storage를 쓸지 guest에서 file journal을 쓸지 capability에 맞춰 결정하되, network share나 legacy Python의 지원을 확인하지 않고 DB atomicity를 가정하지 않는다. append-only log도 agent가 원파일을 다시 쓸 수 있으면 완전한 tamper-proof가 아니다. threat model에 맞는 계정·독립 hash anchor·backup을 적용한다.

## 3. Durable write 요구

- root 존재·권한·최소 여유 공간·quota를 write 전에 검사한다.
- intent와 expected baseline을 실제 flush/fsync 후 다음 단계로 진행한다.
- temp file + atomic rename은 같은 filesystem 조건과 durability를 확인한다.
- state file과 journal 불일치 시 journal sequence와 실제 observed data로 reconcile한다.
- JSON parse 실패/부분 줄/truncation을 defaults로 덮어쓰지 않는다.
- finalization 실패를 최종 성공으로 반환하지 않는다. actual apply 여부와 final evidence 여부를 별도 상태로 남긴다.

## 4. Idempotency

`operation_id + canonical_request_digest + principal + target_revision + executor_digest`를 비교한다.

- 같은 ID·같은 digest: 기존 operation 상태를 반환한다.
- 같은 ID·다른 digest: conflict로 거부한다.
- 응답 timeout: 새 ID 생성보다 기존 상태 확인을 먼저 한다.
- server restart: durable ownership 증거로 합법적 continuation만 허용한다.
- parent-child mapping 등록과 worker 시작 사이의 실패를 시험한다.
- worker가 시작되지 않았는데 running으로 고정되거나, 시작됐는데 ID가 사라지지 않게 handshake한다.

## 5. 실패 분류

| 관찰 | 상태·조치 |
|---|---|
| 조회 timeout | 허용된 bounded read retry |
| license unavailable | bounded queued/waiting; 실제 compute와 별도 집계 |
| Spectre 정상 종료·spec fail | valid design experiment, 다음 후보는 승인 budget 안에서 가능 |
| measurement invalid | numeric result를 채우지 않고 measurement failure |
| write 시작 전 precondition fail | no-write blocked; 승인 없는 retry 금지 |
| apply 응답 유실 | unknown write; 추가 write 중지, read-only 확인 |
| known approved compensation 가능 | 승인된 exact recovery만 수행 |
| backup 신뢰 불명·예상 밖 diff | unsafe/ambiguous, forensic proposal와 별도 승인 |

retry policy 확장은 별도 검토한다. 과거 automatic retry=0를 문서 생성만으로 완화하지 않는다.

## 6. Revision과 compensation

가능하면 source를 수정한 뒤 되돌리는 대신 immutable parent를 유지하고 staging child를 만든다. 여러 cellview 변경이 실패해도 source는 손대지 않는다. validation 후 promotion pointer를 업데이트하는 방식으로 노출 범위를 제한한다.

모든 변경이 DB transaction처럼 원자적인 것은 아니다. 여러 도구·파일·OA 객체에 걸친 작업은 승인된 보상 동작, 실패 evidence, partial 상태로 다룬다. rollback 자체도 실패할 수 있으므로 증거를 남기고 자동 반복하지 않는다.

## 7. Fingerprint와 결과 유효성

- raw-file digest: 내용 보존과 artifact identity.
- schematic semantic digest: effective devices/params·terminal incidence·hierarchy·supply/bulk·pin semantics.
- layout semantic digest: device mapping·geometry·LPP·DBU·via/pin·connectivity와 intent.
- metadata diff: exact allowlist와 해당 tool/version/작업의 근거.

`schGeometryLastUpdated` 예전 값 쌍은 역사 사례다. 메타데이터를 포괄 제외하거나 임의 복원하지 않는다. unknown property는 삭제하지 않고 영향 분류를 보류한다.

LVS result는 schematic+layout+deck 조합에, PEX는 layout+extraction model에, post-layout는 PEX+TB+measurement에 결부한다. 어떤 dependency든 바뀌면 결과는 stale이며 현행 PASS로 사용할 수 없다. 과거 기록은 남는다.

## 8. Crash matrix

| 중단 지점 | 기대 증거 |
|---|---|
| intent 저장 직전 | write 없음 |
| intent 이후 worker 시작 전 | durable operation, 미시작 식별 |
| backup 직후 | 복구 source 검증과 write 미실행/불명 여부 |
| apply 도중/직후 | APPLY_STARTED, 실제 target readback 가능 |
| diff 도중 | unknown/partial validation, 다음 write 없음 |
| rollback 도중 | rollback partial, parent/backup 보호 |
| final manifest 직전 | 완료 stage journal은 남고 manifest incomplete 구분 |
| 응답 반환 직전 | 재요청 시 동일 run 결과, 중복 apply 없음 |
| 전원/디스크 실패 | source/PDK 불변 및 보존 가능한 마지막 evidence |

고장 주입은 승인된 synthetic/staging fixture에서만 수행한다. 사용자가 작업 중인 원본을 강제 crash시키지 않는다.

## 9. 백업·재난 복구

VM snapshot은 독립 백업을 대신하지 않는다. source/config/승인/evidence 보관과 실제 restore rehearsal을 시행한다. 열린 OA의 inconsistent 복사본을 성공 backup이라고 기록하지 않는다. restore 결과는 파일/회로 의미·tool compatibility로 재검증한다.

기존 VM OS/라이선스/도구를 업그레이드하는 것이 이 단계의 목적이 아니다. 미래 도구는 별도 실행 환경과 logical adapter로 추가할 수 있다.
