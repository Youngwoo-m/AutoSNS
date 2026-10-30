# 관리 제작·미디어 계약

이 문서는 서버 제작 통합자가 소비하는 미디어 경계를 설명한다. 원본 계정의 공급자 정책과 실제 발행 대상은 분리한다. 개인의 `allowed_media=('text',)`는 구독 모델의 호출 범위다. 서버 등록 로컬 재사용·Voicebox·Remotion·PDF 처리를 유료 이미지 모델로 간주하거나, 이를 이유로 유료 모델 fallback을 허용하지 않는다.

## 입력과 완료 조건

`render_registered_media(kind, manifest, *, artifact_root: Path, runners: Mapping) -> dict`를 호출한다. kind는 `reuse_image`, `voicebox_audio`, `remotion_video`, `pdf_document` 네 가지다. 실행 registry와 검토 callback은 서버 구성으로만 주입한다. 요청·모델 JSON으로 callable, CLI, 경로 외부 템플릿, HTML/JS/Python을 등록하지 않는다. 알 수 없는 kind와 필수 생성 그림 공급자 부재는 `blocked/missing_required_media`다.

완료 반환은 `status='completed'`, `assets=[{path, filename, media_type, size, sha256, evidence}]`, `evidence`다. 실패는 `status='blocked'`, `reason_code`, `assets=[]`다. artifact_root 밖 경로와 심볼릭 링크는 거부한다. 파일당 100 MiB, 제작 통합의 콘텐츠 전체 500 MiB 한도를 유지한다. 반환 자산은 서버가 다시 hash를 확인하고 ContentStore에 CAS로 추가한다. 검토 도중 파일이 변경되면 완료하지 않는다. 실패한 임시 산출물은 임의로 덮어쓰거나 지우지 않는다.

## 등록별 schema

- `reuse_image`: `{path, sha256, source, reuse_request_id}`. PNG/JPEG/WebP 실제 파일을 검사한다. `runners['reuse_authorization'](manifest=..., asset=...)`의 서버 기록이 `authorized=True`, `reviewed=True`이며 hash·source·reuse_request_id가 모두 같아야 한다. 모델의 자체 재사용 승인 주장은 입력 schema에 없다.
- `voicebox_audio`: `{text, seed?, output?}`. 출력은 WAV다. `VoiceboxAudioRunner(client, profile_id=서버지정)`를 `runners['voicebox_audio']`에 명시 등록한다. client는 `ready()`, `generate(**body)`, 필요 시 `wait_completed(id)`, `audio(id)->bytes`를 제공한다. 기존 shorts_voice.py의 Voicebox 본문(language=ko, engine=qwen, model_size=0.6B, normalize=True, max_chunk_chars=250)을 사용한다. 준비 안 된 서비스는 blocked이며 up/down/kill/restart 또는 다른 TTS fallback을 하지 않는다. `inspect_audio(asset=..., manifest=..., probe=...)`가 checked/script_matches/intelligible을 확인해야 한다. 실측 20초 이하와 `AI 합성 음성(본인 목소리 복제)` 고지가 필요하다.
- `remotion_video`: 기존 SurveyShort의 exam/field/source/footer/disclosure/voice?/scenes/output? schema만 받는다. scene은 title/caption/image/image_asset_id/kind/seconds와 audio?/overlay?/captionSize?다. 디오라마 2~3장, 전체 장면 길이 20초 이하, 모든 파일 및 음성이 필요하다. `RemotionVideoRunner(template_root, template_hash=서버검토hash, font_path=서버파일, spawn=..., scene_assets=서버등록, reuse_authorization=서버검증, generation_authorization=서버검증)`는 코드·설정·lockfile hash를 확인하고 고정 `npx --no-install remotion render src/survey-short/index.ts SurveyShort`를 실행한다. 모델 JSON으로 명령을 구성하지 않는다. font를 고정 public 파일명으로 복사한다. ffprobe 실측 1080×1920, 음성 stream, 20초 이하, 등록 font hash, 합성 음성 고지 및 `inspect_video(asset=..., manifest=..., probe=...)`의 모든 장면·음성·폰트·고지 검사 없이는 완료하지 않는다. callback 결과는 scenes=[{index:1,checked:True}, ...], audio_checked/font_checked/disclosure_checked=True다.
- `pdf_document`: `{title, body, output?}`의 일반 텍스트만 받는다. `PdfDocumentRunner(서버renderer)`는 renderer(title=..., body=..., output=Path)에 전달한다. 기본 `probe_pdf(Path)`는 고정 pdfinfo로 page_count만 관측한다. 현재 설치된 PDF 객체/name/action 안전 검사기가 없으므로 정상 문서도 safe_parser=False, reason_code=pdf_object_inspection_unavailable이다. raw 토큰 blacklist나 pdfinfo의 JavaScript=no를 안전성 근거로 쓰지 않는다. 기본 경로는 렌더 완료 및 ContentStore ingest를 차단한다. `inspect_pdf_page(path=..., sha256=..., page_number=1..N)`가 모든 페이지에 checked=True, 동일 page_number, 실제 rendered_path를 반환해야 한다. 각 렌더 파일의 hash를 전체 페이지 evidence에 저장한다. 기본 검사기가 없으면 blocked다. 완료 MIME은 `application/pdf`이며 ContentStore의 PDF 지원은 제작 저장 담당이 연결한다.

`runners['probe'](Path)` 또는 기본 ffprobe가 seconds/width/height/has_audio를 반환한다. PDF는 서버 주입 pdf_probe를 사용할 수 있다. probe/검사기의 주입 결과는 서버 신뢰 경계이며 HTTP payload에서 받지 않는다. fixture 검사 기록은 실제 리뷰 수행으로 등록하지 않는다.

## 통합 책임

생산 단위·예약·binding·최종 revision/manifest의 불변 연결은 ProductionStore/RuntimeStore 담당이다. 이 모듈은 quota/DB/발행 adapter/credential/profile/permit을 받지 않는다. prepare 회차만 제작하고 publication/verify 회차에서 재제작하지 않는다. 실제 공급자 capability가 확인되지 않은 상태와 실제 근거 검토기가 미등록인 상태는 완료할 수 없다.

## 장면 입력 자산의 서버 등록 (Fix round 1)

`runners['scene_assets']`는 asset_id별 `RegisteredSceneAsset` 객체를 담는 서버 registry다. 모델/HTTP의 dict를 이 객체로 자동 변환하지 않는다. 각 장면의 image_asset_id가 이 registry를 가리켜야 하며 scene.image도 등록 path와 동일해야 한다. 등록은 frozen dataclass이며 provenance도 deep freeze한다. 파일의 실제 hash와 source/provenance를 검사하고 evidence.inputs에 남긴다. 렌더 뒤에도 입력 hash를 다시 확인한다. Remotion leaf를 직접 호출할 때도 생성자에 동일 서버 registry와 승인 callback을 제공해야 한다.

`RegisteredSceneAsset(asset_id, path, sha256, source, origin, provenance, reuse_request_id=None)`의 origin은 reuse 또는 generated다. reuse provenance는 `{kind:'reuse',record_id:서버출처기록}`이며 사용자 reuse_request_id가 필수다. 기존 reuse_authorization의 authorized/reviewed/sha256/source/reuse_request_id 전체 일치를 장면마다 다시 요구한다. 파일 존재·이미지 고지·검토 완료 주장만으로 이를 대체하지 않는다.

generated provenance는 `{kind:'generated',provider_id,execution_id,policy_revision,request_hash}`다. 실제 허용 생성 이력과 hash를 검증하는 서버 `generation_authorization(registration=객체, asset=실파일메타)`가 authorized=True 및 동일 sha256/provenance_hash를 반환해야 한다. 해당 검증기가 없으면 missing_required_media다. 모델 manifest의 provenance/승인 필드는 scene schema가 거부한다. 공개 생성 공급자는 기본 등록하지 않는다.

PDF의 서버 주입 pdf_probe도 실제 객체 검사 결과만 반환해야 한다. 시험의 parser/inspection fixture는 임시 경계 시험이며 운영 registry로 연결하지 않는다. 현재 기본 PDF 경로가 문서를 완료하지 못한다는 제한은 의도된 fail-closed 상태다.
