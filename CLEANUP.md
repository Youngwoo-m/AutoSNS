# AutoSNS 디스크 정리 목록

작성 2026-08-24 · 현재 총 **3.1GB** · 회수 가능 최대 **약 1.6GB**

아직 **아무것도 삭제하지 않았습니다.** 아래에서 실행할 등급을 골라 주세요.

---

## 등급 1 — 안전 (즉시 삭제 가능) · 약 **1,192MB**

지워도 로그인·예약 발행에 영향 없고, 필요하면 자동 재생성됩니다.

### 1-1. 크롬 캐시 — 811MB

로그인 정보가 아니라 웹 캐시입니다. 삭제해도 세션 유지되며, 다음 실행 때 다시 채워집니다.

| 경로 | 용량 |
|---|---|
| `insta-cardnews/chrome-profile-insta/Default/Cache` | 279M |
| `naver-blog-auto/chrome-profile/Default/Cache` | 138M |
| `insta-cardnews/.../Default/Code Cache` | 132M |
| `naver-blog-auto/.../Default/Code Cache` | 133M |
| 양쪽 `component_crx_cache` | 각 28M |
| 양쪽 `GrShaderCache` | 16M / 12M |
| 양쪽 `GPUCache`·`ShaderCache`·`GraphiteDawnCache`·`Dawn*Cache` | 합 약 18M |

```bash
cd ~/devAPP/AutoSNS && for p in naver-blog-auto/chrome-profile insta-cardnews/chrome-profile-insta; do rm -rf "$p/Default/Cache" "$p/Default/Code Cache" "$p/Default/GPUCache" "$p/Default/DawnGraphiteCache" "$p/Default/DawnWebGPUCache" "$p/GrShaderCache" "$p/ShaderCache" "$p/GraphiteDawnCache" "$p/component_crx_cache"; done
```

> **선행 조건:** 크롬이 그 프로필로 실행 중이 아니어야 합니다. 발행 스케줄(화·수·금 19:00, 화·금 08:30)과 겹치지 않는 시간에 실행하세요.

### 1-2. 인스타 카드 zip — 217MB

`*.zip` 22개 전부 동명 `cards_*` 폴더와 **내용이 같습니다**(22/22 짝 확인 완료). 폴더를 남기면 zip은 불필요합니다.

```bash
rm -f ~/devAPP/AutoSNS/insta-cardnews/posts/*.zip
```

### 1-3. 유튜브 프레임 중간산출물 — 164MB

`posts/frames_TIKTOK_*` 38개. mp4로 렌더링이 끝난 뒤의 PNG 시퀀스라 완성 영상이 있으면 불필요합니다.

```bash
rm -rf ~/devAPP/AutoSNS/youtube-shorts-auto/posts/frames_*
```

---

## 등급 2 — 확인 후 삭제 · 약 **423MB**

발행은 끝났지만 원본 재활용 가능성이 있는 것들입니다. **재생성 불가**이므로 판단이 필요합니다.

| 대상 | 개수 | 용량 | 판단 포인트 |
|---|---|---|---|
| `insta-cardnews/posts/cards_*` 폴더 | 25 | 224M | 1-2의 zip을 남기고 이쪽을 지우는 선택도 가능(둘 중 하나만) |
| `youtube-shorts-auto/posts/*.mp4` 미참조분 | 43 | 102M | 예약 발행이 참조하지 않는 과거 영상. 유튜브에 이미 업로드됨 |
| `naver-blog-auto/posts/*.png` | 43 | 82M | 발행 완료된 배너·기사 이미지 |
| `insta-cardnews/posts/*.mp4` 릴스 | 16 | 15M | 인스타에 이미 게시됨 |

---

## 절대 삭제 금지

| 대상 | 이유 |
|---|---|
| `Default/Network/Cookies` (양쪽 각 28K) | **로그인 세션 본체.** 지우면 재로그인 필요 |
| `Default/Login Data`, `Preferences`, `Web Data`, `Local State` | 프로필 인증·설정 |
| `posts/short_TIKTOK_CAREER5~8.mp4`, `short_TIKTOK_QUIZ01~10.mp4` | **예약 발행 대기분 14개(54MB).** 8/25~11/24 사용 예정 |
| `_profile_backup_20260720/` (776K) | 로그인 세션 백업. 세션 만료 시 복구 수단 |
| `chrome-profile*/**/LOG.old` | 이름과 달리 사용 중인 프로필 내부 파일 |
| `title_history.json`, `trigger_state.json`, `publish_schedule.json` | 중복 발행 방지 상태 |

---

## 요약

| 등급 | 회수량 | 위험 |
|---|---|---|
| 1 (안전) | 1,192MB | 없음 — 재생성됨 |
| 2 (확인 필요) | 423MB | 원본 소실 |
| **합계** | **1,615MB** | 3.1GB → 약 1.5GB |

**권장:** 등급 1만 실행해도 1.2GB가 줄어듭니다. 등급 2는 필요할 때 개별 판단하시길 권합니다.
