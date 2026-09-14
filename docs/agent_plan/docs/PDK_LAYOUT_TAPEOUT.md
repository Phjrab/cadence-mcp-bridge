# Layout·공식 검증·제작 PDK·최종 제출 설계

## 1. 개발 flow와 제작 flow의 구분

GPDK090은 generic 개발·회귀 검증 환경으로 사용한다. 전체 flow가 성공해도 특정 제조공정에서 제작 가능한 signoff를 의미하지 않는다.[E4]

```text
FLOW_VALIDATED_GPDK090
→ FAB_PDK_VALIDATED
→ SUBMISSION_READY
→ HUMAN_APPROVED_FOR_SUBMISSION
```

마지막 상태는 실제 제출 또는 주문이 일어났다는 뜻과도 별개다. portal confirmation 및 제출된 exact hash는 실제 제출 작업에서만 기록한다.

## 2. Schematic-PCell round-trip

Logical device → CDF/instance params → generated effective model → PCell geometry → extracted/LVS device params를 검증한다.

총 W와 finger W, m과 nf, model type과 PCell type, pin order와 body, orientation과 source/drain mapping을 PDK별로 명시한다. callback 없이 직접 property를 설정한 결과와 GUI에서 설정한 결과가 다를 수 있으므로 현재 PDK/API에서 functional fixture로 확인한다.

## 3. Layout intent

대칭/매칭/centroid/ratio/dummy/contact 환경/guard ring/well ties/power routing/sensitive pair·coupling/keepout·area를 의미 계약으로 보존한다. DRC clean은 matching 성능 보증이 아니다. 길이 일치만으로 RC balance를 확정하지 않는다.

Matching algorithm이 답을 못 찾으면 intent relaxation proposal과 영향·승인 필요성을 제시한다. 물리 의도를 몰래 삭제하지 않는다.

## 4. 검증기 먼저

각 backend별 executable/version/license/PDK deck/runset/result format을 확인한다. known clean과 deliberately bad fixture를 모두 실행해야 parser가 검증된다.

False clean 방지:
- nonempty correct layout/top/hierarchy.
- expected rule/deck/version/options 및 사용한 input hash.
- tool 정상 완료와 complete result.
- exclusions/blackboxes/waivers의 목록과 승인.
- parser truncation/unknown result/empty report는 invalid.
- expected violation fixture에서 위반 검출.

DRC/LVS 라이선스가 없으면 adapter stub/fixture tests와 actual unavailable 상태를 분리하고 F05에서 병목을 알린다. frontend banner만으로 지원을 주장하지 않는다.

## 5. 안전한 자동 수정

DRC violation-to-object mapping은 revision/hierarchy coordinate transform을 포함한다. ambiguous mapping은 자동 apply하지 않는다.

수정마다 connectivity/device params/pins/bulk/matching/area/budget을 확인한다. 위반을 없애기 위해 필요한 도형을 삭제하거나 schematic을 틀린 layout에 맞추면 안 된다. geometric improvement는 DRC 결과뿐 아니라 LVS/intent 재검증과 연결한다.

## 6. PEX/post-layout

Signoff용 PEX는 같은 revision의 유효한 LVS 후 실행한다. 연구용 pre-LVS extraction을 나중에 지원하더라도 `diagnostic_only`로 구분하고 signoff에 사용하지 않는다.

Actual extracted view/DSPF 등 형식·config binding·port order·device model·RC corner를 검증한다. schematic fallback과 parasitic/device 이중 포함을 차단한다. RC process와 transistor process 조건은 별도 축이다.

Post-layout에는 actual extraction digest와 동일 stimulus/load/measurement 조건이 있어야 한다. fill/pad/routing이 바뀌면 PEX와 post-layout evidence는 stale다.

## 7. Device reliability와 chip realism

지원하는 검사 범위를 capability matrix에 남긴다: ERC, antenna, density/fill, well/latch-up, ESD/IO integration, EM/IR, voltage stress, aging, thermal/package effects. 어떤 도구나 모델도 제공되지 않으면 미평가로 남긴다. 필수 제출 요건이라면 해당 capability 부족은 gate blocker다.

Startup, bias/reference, CMFB, output load, PSRR/CMRR, power sequence, measurement access는 core spec부터 고려한다. chip top 단계에서 ideal TB가 사라진 뒤도 동작해야 한다.

## 8. MyChip onboarding

공식 제공받은 package/user guide/model/decks/PCells/pad/stream map/submission rule로만 기술 전제를 정한다. 특정 공정 노드·device 이름·전압·SOP 핀 수를 과거 답변에서 가져오지 않는다.

PDK 정식 사용·보관·모델 서비스 전송 조건을 확인한다. private repo도 원문 업로드를 자동 허용하지 않는다. 실제 지원 도구가 별도 OS/version을 요구하면 기존 VM은 보존하고 새 environment adapter를 추가한다.

Intent/topology/metric을 재사용할 수 있으나 W/L/bias/current/layout는 새 모델로 재최적화한다. VDD=1 V가 어려우면 feasibility·tradeoff로 보고하고 spec 변경을 승인받는다.

## 9. 제출할 파일 자체 검증

최종 OA revision이 아닌 최종 GDS/OASIS bytes와 evidence를 묶는다.
- official stream map, DBU/precision, pin labels/purposes.
- top/hierarchy/blackbox/exclusion/cell coverage.
- final pad/ESD/fill/seal ring/die boundary.
- stream round-trip geometry·electrical equivalence.
- 공식 flow가 지원하는 final-file DRC/LVS 또는 인정된 동등성 검사.
- PEX/postlayout가 최종 변경과 일치.
- exact final file digest와 승인 package digest.

Round-trip reopen만 성공한 것은 충분하지 않다. 최종 stream을 수정하면 제출 승인을 재검증한다.

## 10. 인간 gate·fabrication·실리콘

waiver, 승인 모델/규정 변경, 최종 제출·주문·비용은 사람 책임의 별도 승인이다. automation code release 승인과 chip tapeout 승인을 혼동하지 않는다.

칩을 받은 후 device/lot/package/board/instrument/calibration/actual supply/온도 조건을 기록한다. 측정 uncertainty와 package/PCB 영향을 분리하여 sim-to-silicon을 비교하고 다음 revision proposal을 만든다. 자동 재주문하지 않는다.
