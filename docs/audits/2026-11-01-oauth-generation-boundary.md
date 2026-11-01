# OAuth snapshot 자격 세대·소유 결속 독립 검토

2026-11-01. 범위는 `common/operations/managed_connections.py`와 해당 회귀 시험의 독립 재현·diff 검토다. 감사 작업자는 이 문서만 작성했다. 코드·시험 수정과 focused suite 실행은 부모 작업자가 담당했다. 실제 계정, provider, 자격 backend, Keychain/native bridge, 브라우저, 발행, 설정 변경, 커밋은 수행하지 않았다.

## 판정과 현행 설계 범위

최종 diff에서 이번 검토가 발견한 필수 오류는 해소됐다. 승인 설계의 관리 저장소 active generation, 동일 snapshot에서 합성하는 credential catalog와 registry의 소유 검증, 유효 active reference 계약을 보완하는 수정이다. 근거는 [승인 설계](../superpowers/specs/2026-10-31-sns-oauth-connections-design.md)의 관리 연결 overlay 절과 자격 저장·회전 절이다.

이번 수정은 이미 전달받은 snapshot 안의 참조 정합성만 검증한다. 자격 읽기 직전 최신 DB 재조회, 요청 시작 시 세대 CAS, provider 요청 권한, 실제 자격 존재·만료 증명은 구현하지 않는다. 그러한 실행 경계는 [기존 runtime 경계 감사](2026-11-01-oauth-runtime-credential-boundary.md)의 별도 후속 조건으로 남는다. `authorization=None` 호환 동작도 이번 수정에서 새 active 권한 증거로 바뀌지 않는다.

## 수정 전 독립 재현

실제 비밀 없는 `CredentialRef`와 순수 `ManagedSnapshot`을 사용했다. `ref1`과 `ref2`는 같은 개인 YouTube 연결의 세대 1·2이며, `key2`는 세대 2의 canonical key다.

|조합|수정 전 결과|
|---|---|
|행 ref2·active generation 2, catalog 참조 `key2 → ref1`|catalog와 registry가 세대 1 참조를 승인했다.|
|행 ref1·active generation 2, catalog 참조 `key1 → ref1`|catalog와 registry가 세대 1 참조를 승인했다.|
|행 ref2·active generation 2, catalog에는 ref1만 있음|catalog는 오래된 참조를 반환하고 registry는 현재 key 조회에서 `KeyError`를 냈다.|
|현재 ref에 arbitrary key를 붙임 또는 현재 catalog 항목 누락|registry에서 `KeyError`가 발생했다.|
|행의 `connection_id`와 map key가 다름 또는 generation이 `True`|정상 소유·정수 세대로 구별하지 못했다.|

ref1과 ref2를 모두 catalog 참조에 넣으면 수정 전 catalog에는 둘 다 포함됐지만 registry가 합성한 자격에는 현재 ref2만 들어갔다. 이 경우 registry 자체가 오래된 자격을 합성했다고 과장하지 않는다.

## 첫 diff에서 발견한 추가 우회와 최종 수정

첫 diff는 catalog가 참조하는 행의 결속을 검사했지만 registry의 각 투영 행에는 key 존재만 검사했다. 유효한 `conn` 행과 그 자격 ref를 빌리는 `other` 행을 함께 넣으면 catalog는 `conn`으로 검증을 마친 뒤, registry는 `other`에도 같은 ref를 붙였다. `other`의 active generation을 3으로 바꾸거나 계정을 학과로 바꾸어도 개인 `conn`의 세대 2 자격을 붙일 수 있었다. 이는 같은 snapshot 안의 연결·계정·세대 소유 검증 문제다.

부모 작업자가 최종 반영한 `_validate_credential_binding(identifier, row, ref, key)`는 catalog와 registry의 각 활성 투영 행 양쪽에서 다음을 검사한다.

- `CredentialRef` 타입과 canonical key, token kind와 OAuth namespace.
- map identifier, 행의 connection ID, ref connection ID의 일치.
- 행과 ref의 account·platform·현재 credential reference 일치 및 provider/platform 대응.
- 행 credential generation의 정확한 정수 타입과 ref generation 일치.

registry의 현재 catalog 항목 누락도 `StoreError('credential_owner_mismatch')`로 거절한다. 기존 pending lease·명시 non-active authorization의 자격 제외와 auth unknown 투영은 유지한다. raw snapshot row, SQLite writer/CAS, 원본 registry, legacy 자격·프로필, enabled 정책을 변경하는 diff는 없다.

## 독립 검증과 시험 검토

최종 diff에서 순수 probe를 다시 실행하여 다음을 확인했다.

- 단일행 stale ref/key/generation·잘못된 ID·boolean generation을 catalog와 registry 양쪽에서 거절했다.
- 유효한 catalog를 이용하는 두 행 alias의 map-ID·다른 active generation·다른 account 조합도 registry에서 거절했다.
- 현재 catalog 항목 누락을 포함하여 총 16회 거절 모두 `credential_owner_mismatch`였고, 위 재현에서는 `KeyError`가 발생하지 않았다.
- 정상 세대 2 snapshot은 catalog와 registry에서 성공했다. pending refresh lease와 명시 unknown authorization의 두 차단 투영은 자격 없음·auth unknown·enabled false를 유지했다.

이 독립 검증은 전체 suite나 실제 자격 수락 시험이 아니다. 부모가 추가한 회귀 시험은 stale snapshot 거절, durable 현재 세대·base registry 보존, 정식 refresh 완료 후 세대 2만 catalog에 존재함, 정상 registry 투영, 유효 catalog를 빌리는 다른 연결의 개인/학과 세 조합을 다룬다. 부모의 focused suite 결과는 이 문서의 독립 실행 결과에 합산하지 않았다.
