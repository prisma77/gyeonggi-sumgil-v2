# Gemini 요청 해석 실험 — 2026-10-09

## 이번 단계

앱의 `GeminiApi.generateRouteDecision`, `AiPromptTemplates`, `AiRouteModelDecisionParser`를
그대로 사용하는 PC/JVM 실험이다. Android 경로 화면에 AI 요청 해석을 연결한 단계는 아니다.
LLM에 좌표·경유점·선형·실제 거리를 생성하도록 요청하지 않는다.
공개 장소명만 사용하며 사용자 주거 주소, 현재 좌표, 관측 자료는 전송하지 않는다.

- 기본 모델: `gemini-3.8-flash`. `local.properties`의 `GEMINI_MODEL`로 변경 가능하며 재빌드가 필요하다.
- 인증 키: 기존 `GEMINI_API_KEY`. 키를 URL 대신 `x-goog-api-key` 헤더로 보낸다.
- `thinkingLevel: low`, 분류 출력 상한 900토큰, JSON 응답 형식.
- Gemini 3.8 변경 사항에 따라 temperature/topP 파라미터를 제거했다.
- 연결 실패 자동 재시도를 끄고, 실험의 요청 수를 최대 3회로 제한한다.
- 일반 단위 테스트에서는 실제 API 실험을 건너뛴다. 아래의 별도 실행은 비용이 발생한다.

공식 근거: [Gemini 3.8 Flash와 마이그레이션 안내](https://ai.google.dev/gemini-api/docs/generate-content/latest-model).

## 실제 관측 결과

2026-10-09 17:14 KST, 3건 모두 HTTP 200, finishReason STOP.

| 입력 | 확인한 반환 결과 | 판정 |
| --- | --- | --- |
| 미사호수공원 안에서만 3km 걷기, 공원까지 이동 거리 제외 | 장소 `미사호수공원`, 3000m, 정규화 문장에 공원 내부·이동 거리 제외 유지 | 통과 |
| 광교호수 한바퀴 산책 코스 | 장소 `광교호수`, lake_loop, 거리·시간 null, 거리 추가 질문 없음 | 통과 |
| 이전 요청 `탄천 왕복 2km` → 최신 입력 `같은 곳에서 3km로 바꿔줘` | 장소 `탄천`, river_out_and_back 유지, 3000m로 변경 | 통과 |

입력 3517토큰, 출력 362토큰, 반환 usageMetadata의 생각 토큰 0.
무료 크레딧 적용 여부와 최종 청구 금액은 이 실험에서 확인하지 않았다.
오프라인 단위 테스트 41개 통과, 유료 실험 테스트 1개는 기본 실행에서 제외.
APK 빌드 및 lint 완료(오류 0). 지도 관련 실기기 검증은 이번 실험에 포함하지 않았다.

## 해석 결과의 한계

- 3개 사례의 단회 관측이며 다양한 표현이나 반복 요청의 품질을 보장하지 않는다.
- 미사 입력에 모델이 lake_loop를 반환했지만 이 입력은 한바퀴를 명시하지 않았다.
  그 반환값만으로 순환 요구가 확정되었다고 판단하지 않는다. 여기서는 장소·거리 범위만 검사했다.
- 광교호수/탄천은 검색어다. 세부 호수, 하천 출발 구간, 장소 존재·통행을 확인한 결과가 아니다.
- 공원 내부 거리 범위는 현재 정규화 문장에 보존한다. 경로 엔진에 연결하기 전에
  접근 거리와 코스 거리를 명시적으로 구분하는 구조화된 요청 계약이 필요하다.
- 호수 한바퀴를 2.5km로 바꾸는 프롬프트 기본값을 제거했다.
  기존 미사용 경로 헬퍼의 다른 기본값까지 모두 교체한 것은 아니다.
- 실제 선형 생성, 공원 구간 3km 충족, 호수 순환 여부는 Routing API와 별도 검사로 판단한다.
- 기존 Google Maps grounding 메서드는 현재 앱 실행 흐름에서 사용하지 않으며 이번 실험 대상도 아니다.

## 수동 재실행

일반 테스트는 `SUMGIL_RUN_GEMINI_PROBE` 없이 실행한다. 실제 API를 다시 시험할 때만 아래 명령을 사용한다.
Gradle 테스트 결과는 `app/build/test-results/testDebugUnitTest`에 저장된다(ignored).
API 키와 원문 HTTP 응답은 출력하지 않으며, 공개 시험 요청의 분류 JSON과 토큰 합계만 기록한다.

```powershell
$env:JAVA_HOME = 'C:/Program Files/Android/Android Studio/jbr'
$env:SUMGIL_RUN_GEMINI_PROBE = '1'
try {
    .\gradlew.bat testDebugUnitTest --tests 'com.gyeonggisumgil.app.data.gemini.GeminiLiveProbeTest' --rerun-tasks --console=plain '-Dorg.gradle.jvmargs=-Xmx4096m -Dfile.encoding=UTF-8' --max-workers=2
} finally {
    Remove-Item Env:SUMGIL_RUN_GEMINI_PROBE
}
```

## 다음 완료 기준

1. 거리 범위와 한바퀴 요구를 별도 필드로 검증하고 잘못된 모델 추론을 자동 채택하지 않는다.
2. 장소 검색 결과에서 사용자 요청과 일치하는 후보를 확인한다.
3. 확인된 입력을 기존 실제 도보 경로 생성·검증 흐름에 연결한다.

## 여러 장소로 확대한 실험 — 2026-10-09 17:39 KST

장소명에 호수·공원·천이 있다는 이유로 순환/왕복을 추측하던 규칙을 제거했다.
한바퀴, 왕복 등 명시된 형태만 반영하며 거리/시간만 제시하면 unknown으로 둔다.
수정한 앱 프롬프트·클라이언트·파서를 사용해 아래 8건을 각각 1회 시험했다.

| 요청 | 거리/시간 | 형태 및 확인 질문 | 관측 |
| --- | --- | --- | --- |
| 미사호수공원 내부만 3km, 이동 거리 제외 | 3000m / 시간 없음 | unknown, 거리 범위 보존 | 통과 |
| 왕송호수 한바퀴 | 거리·시간 없음 | lake_loop, 기본 거리 삽입 없음 | 통과 |
| 일산호수공원 30분 걷기 | 거리 없음 / 30분 | unknown, 순환 추측 없음 | 통과 |
| 광교호수공원 신대호수 한바퀴 | 거리·시간 없음 | lake_loop, 주 검색어에 신대호수 유지 | 통과 |
| 안양천 2.5km 왕복 | 2500m / 시간 없음 | river_out_and_back | 통과 |
| 중랑천 30분 산책 | 거리 없음 / 30분 | unknown, 왕복 추측 없음 | 통과 |
| 올림픽공원 한바퀴 | 거리·시간 없음 | loop, 호수 순환으로 바꾸지 않음 | 통과 |
| 중앙공원 3km, 지역 미지정 | 3000m / 시간 없음 | unknown, 어느 지역인지 질문 | 통과 |

8회 모두 HTTP 200 / STOP. 입력 10748토큰, 출력 821토큰, 생각 토큰 0.
앞선 3건과 별도 호출이며, 크레딧 차감 방식은 확인하지 않았다.
일반 오프라인 테스트 46개 통과, 유료 실험 2개는 기본 실행에서 제외. APK 빌드·lint 통과.

품질 판정기는 원하지 않은 lake_loop, 좌표 필드 추가, 현재 위치 몰래 대체,
한바퀴에 기본 거리 삽입을 실패로 처리하며 해당 실패 예시를 오프라인 회귀 검사로 추가했다.
모델이 조건을 잘 추출했는지만 판정한다. 모호한 장소 확인 질문의 표현은 프롬프트로 유도했으며,
실제 검색 후보에 기반한 동명이인 판별이나 장소 존재 여부 검증은 수행하지 않았다.
이 판정기는 현재 시험 코드에 있으며 앱 경로 엔진의 승인 조건에 연결되지 않았다.

기존 17:14 실험의 미사 lake_loop 관측은 변경 전 기록이다.
이번 17:39 실험에서 같은 입력은 unknown으로 반환되었지만 단회 성공을 항상 성공으로 일반화하지 않는다.

### 확대 실험 수동 실행

이 실행은 기존 3건을 함께 호출하지 않고 8건만 호출한다. 자동 재시도·리다이렉트를 끄며
HTTP/통신 오류 발생 시 남은 요청을 중단한다. 품질 불일치는 기록하고 다른 사례 검사를 계속한다.

```powershell
$env:JAVA_HOME = 'C:/Program Files/Android/Android Studio/jbr'
$env:SUMGIL_RUN_GEMINI_PROBE = 'expanded'
try {
    .\gradlew.bat testDebugUnitTest --tests 'com.gyeonggisumgil.app.data.gemini.GeminiLiveProbeTest.expandedPublicPlaceIntentProbe' --rerun-tasks --console=plain '-Dorg.gradle.jvmargs=-Xmx4096m -Dfile.encoding=UTF-8' --max-workers=2
} finally {
    Remove-Item Env:SUMGIL_RUN_GEMINI_PROBE
}
```

### 실제 경로 시험으로 넘어갈 때

- AI의 장소명은 검색어로만 취급한다. 카카오 장소 검색 후보의 지역·분류·식별자를 확인한다.
  중앙공원처럼 지역이 없는 입력은 후보 확인 전 경로 호출을 하지 않는다.
- 서로 다른 호수/공원/하천의 독립 출처 보행 자료를 확보한다. 시험 장소명을 운영 코스 생성 규칙으로 하드코딩하지 않는다.
- 호수 한바퀴는 대상 경계와 주변 보행 네트워크를 함께 확인한다. 연결된 폐곡선이라는 이유만으로 한바퀴로 승인하지 않는다.
- 3km와 30분은 Routing API 결과에서 별도로 검증한다. 공원 코스 거리와 접근 거리는 구분한다.
- 하천 왕복은 반전점과 원래 길 복귀, 양방향 통행 가능성을 검사한다.
- 일산호수공원·왕송호수·신대호수 등 3곳 이상의 독립 사례로 점검하되 데이터 부족은 보류로 기록한다.
  실제 도보 API 요청과 지도 확인은 이번 AI 해석 실험에 포함하지 않는다.
