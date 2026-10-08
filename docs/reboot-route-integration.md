# 기존 앱에 경로 검증 통합 — 2026-10-08

## 작업 방향

사용자 요청에 따라 초기의 기존 코드 보존/별도 앱 방침을 변경했다.
기존 설치 패키지 `com.gyeonggisumgil.app`을 유지하며 업데이트한다.
홈 화면, 색상/탭 구조, AirKorea·기상청 조회/갱신, AI 대기질·날씨 상담 UI를 유지한다.
경로 탭은 카카오 API 실제 응답과 검사 결과를 표시하는 화면으로 교체한다.

- `VerifiedRouteScreen`: 사용자가 시험 입력과 mode를 선택한 뒤 1회 요청.
- `data/routevalidation/ReviewGateway`: 로컬 PC bridge와 앱의 경계.
- `data/routevalidation/ReviewMap`: 카카오 SDK 실제 step별 선형, S/1–5 요청점 표시.
- `experiments/android-route-review/bridge.py`: PC에 REST 키 유지, API 응답은 메모리에서만 처리.
- 홈의 산책로에서 넘어오면 요청 장소를 표시하고, 그 장소의 경로가 아직 연결되지 않았다고 설명한다.
  사용자가 선택을 해제하기 전에는 다른 시험 입력으로 대체하지 않는다.
- AI 상담의 기존 Grounding/고정 코스/임의 경유점 경로 생성 호출을 실행 흐름에서 제거했다.
  대기질·날씨 질문은 기존 상담 API로 처리. 경로 질문은 검증 탭 진행 상황을 안내한다.
- 이전 RouteScreen/코스 생성 헬퍼와 Naver/Tmap 의존성은 일부 참고 코드로 남아 있다.
  Tmap 역지오코딩은 기존 대기질 주소 조회에서도 사용하므로 이번 단계에서 일괄 제거하지 않았다.
  기존 코드가 남아 있다는 사실을 새 경로 품질 승인으로 해석하지 않는다.

## 빌드·실행

Android Studio에서 **저장소 루트**를 연다. 별도 `experiments/...` Android 프로젝트를 실행 대상으로 사용하지 않는다.
SDK/키는 루트의 ignored `local.properties`를 사용한다.

```properties
KAKAO_NATIVE_APP_KEY=기존 카카오 앱의 네이티브 키
KAKAO_REST_API_KEY=PC 검증 서버에서만 사용할 REST 키
```

대기질·날씨의 기존 `AIRKOREA_SERVICE_KEY`, `KMA_SERVICE_KEY`,
역지오코딩용 `TMAP_APP_KEY`, 상담용 `GEMINI_API_KEY` 설정은 유지한다.
REST 키는 Android BuildConfig에 넣지 않는다.

카카오 설정에 사용하는 Android 패키지는 `com.gyeonggisumgil.app`이다.
현재 PC 기본 debug 서명의 키 해시는 `ExtIkfKlzEW953nke0Y3LuFnwWM=`.
별도 `.review` 패키지 등록은 현재 실행 흐름에 필요 없다.

```powershell
$env:JAVA_HOME = 'C:/Program Files/Android/Android Studio/jbr'
.\gradlew.bat test assembleDebug --console=plain
python -B experiments/android-route-review/bridge.py --max-calls 6
```

PC bridge는 별도 터미널에서 실행한다. 기기 id는 현재 연결 목록에서 확인한다.

```powershell
adb devices
adb -s DEVICE_ID reverse tcp:8769 tcp:8769
adb -s DEVICE_ID install -r app/build/outputs/apk/debug/app-debug.apk
adb -s DEVICE_ID shell am start -n com.gyeonggisumgil.app/.MainActivity
```

현재는 개발용 localhost 연결이다. 운영 인증/TLS 서버를 구축하기 전까지 일반 배포 대상으로 삼지 않는다.
실제 API는 버튼 클릭으로만 호출하며 자동 재시도/자동 장소 대체가 없다.
검증 서버 연결 실패 시 같은 화면의 `검증 서버 다시 연결` 버튼으로 시험 입력 목록만 수동 재조회한다.
이 재연결은 `/profiles` GET만 수행하며 카카오 도보 API 호출, 이전 경로 재조회, 자동 재시도를 하지 않는다.
지도 인증 401 발생 시 화면에서 현재 패키지명과 Android `PackageManager.GET_SIGNING_CERTIFICATES`의 현재 APK 서명에서 얻은 SHA-1/Base64 키 해시를 표시한다.
이 값은 등록정보 확인용이며 앱 키 값이나 인증 응답 원문을 표시하지 않는다.
401 안내에서는 `KakaoMapSdk.INSTANCE`의 실제 키 해시, 초기화 여부,
SDK 앱 키와 BuildConfig 값의 일치 여부, SDK Context의 패키지명 일치 여부도 확인한다.
앱 키 값 자체는 표시하지 않으며 SDK 키 해시는 SHA-1/Base64 형식으로 확인 가능한 값만 표시한다.
카카오디벨로퍼스에서 해당 네이티브 키의 Android 정보를 저장한 뒤 경로 탭을 다시 열어 인증을 확인한다.
키 해시의 Base64 끝 문자 `=`도 포함해야 한다. 등록정보뿐 아니라 해당 네이티브 키의 활성 상태와 같은 앱의 카카오맵 사용 설정도 확인한다.
공식 근거: [카카오 앱/플랫폼 키 설정](https://developers.kakao.com/docs/ko/app-setting/app),
[카카오맵 사용 설정](https://developers.kakao.com/docs/ko/kakaomap/common),
[지도 SDK 인증 오류 안내](https://apis.map.kakao.com/android_v2/docs/getting-started/quickstart/).
탭 종료 시 MapView와 결과 참조를 정리하고, 좌표/응답을 파일·DB에 저장하지 않는다.

## 단계별 GitHub 업로드

한 번에 전체 리부트를 올리지 않고 검증 가능한 변경 단위로 커밋/업로드한다.

1. API 실험 도구와 독립 원본 입력·검사: Python 검사 45개 및 실제 API 관측.
2. 기존 UI 유지와 경로 검증 탭 연결: Android 회귀 검사·빌드·기기 확인.
3. 장소 검색 후보의 이름/주소/분류 표시와 사용자 확정.
4. 확정 장소에 대한 경로 후보 생성 및 검증.
5. 관측 데이터와 한계에 근거한 후보 비교/설명.

각 커밋은 빌드/코드 검사와 실제 추천 품질 검증 결과를 구분해 기록한다.
호수 한 바퀴 자동 생성·하천 전체 품질은 확인되지 않았으므로 완료로 표시하지 않는다.

## 현재 검증 기록

- 기존 통합 단계에서 Android 단위 테스트 debug 35개, release 35개 통과. 서로 다른 70개 사례라는 뜻은 아니다.
- `test assembleDebug` 성공. 기존 위치 API 사용의 deprecated 경고가 남아 있다.
- 현재 연결 기기에 기존 패키지로 설치·실행 성공.
- 기기 홈 UI에서 AirKorea 측정 시각/PM10/PM2.5와 기상청 시각/기온/강수/습도/풍속 표시 확인.
  조회 표시 확인이며 관측소 좌표·현재 위치의 정확도까지 검증한 것은 아니다.
- 초기에는 기존 패키지 `com.gyeonggisumgil.app`의 실제 경로 탭에서 지도 인증 401을 확인했다.
  지도 준비 실패 시 실제 경로 조회 버튼이 비활성화됨을 기기 UI 트리로 확인했다.
- 서버 중단 → 연결 실패 안내/수동 재연결 버튼 표시 → 서버 재시작 → 버튼 클릭으로 시험 입력 목록 복구를 실기기에서 확인했다.
  서버 `/profiles` 응답으로 `calls_sent=0`도 확인했다. 이 검증 중 카카오 도보 API를 호출하지 않았다.
- 인증 안내에 표시된 실제 APK의 키 해시가 PC debug 인증서에서 계산한 값과 일치함을 확인했다.
  빌드된 네이티브 키가 `local.properties` 값과 같은지 확인했으며 REST 키는 BuildConfig에 없음을 확인했다.
  사용자는 같은 네이티브 키의 패키지 등록정보, 키 활성 상태, 카카오맵 사용 설정 ON을 모두 확인했다고 답했다.
  이는 사용자 확인이며 콘솔을 도구로 직접 읽어 검증한 것은 아니다.
- 401 진단 중 실기기에서 SDK 초기화 완료,
  SDK 앱 키와 BuildConfig 일치, SDK Context의 패키지명 일치,
  SDK 실제 키 해시와 APK 서명에서 계산한 키 해시 일치를 확인했다.
  이 범위에서 SDK 초기화/키 전달 불일치는 관측되지 않았다.
- 사용자가 제공한 콘솔 스크린샷의 네이티브 키는 로컬 설정과 일치했지만 키 해시 끝의 `=`는 보이지 않았다.
  사용자가 전체 해시를 다시 저장하고 설정 화면을 다시 열어 마지막 `=`가 유지됨을 확인했다고 답한 뒤,
  앱을 새 프로세스로 실행하여 **카카오 지도 준비 완료**와 실제 지도 표시를 확인했다.
  설정 재저장 이후 인증 성공을 관측했으며, 서버의 인증 거절 상세 사유까지 직접 확인한 것은 아니다.
- 이전 401 추적 정보: 서버 시각 `2026-10-08 11:39:25 UTC` (`20:39:25 KST`),
  요청 ID `a1de7d03a902158fbab95c262e50c2e0`.
  요청 헤더/응답 본문/원본 로그/앱 키는 기록하지 않았다.
  이 정보는 인증 성공 전의 기록이며 현재 오류 상태를 뜻하지 않는다.
- 대기질·날씨 코드는 이번 단계에서 유지했지만, 위치/실제 응답/정보 정확성을 별도 검사 없이 보장하지 않는다.
- 호수 전체 순환, 현장 출입/통행, 불필요 우회/반복은 미승인.
- GitHub 대상은 기존 저장소와 구분된 `prisma77/gyeonggi-sumgil-v2`다.
  이후 변경은 사용자가 검토하고 직접 커밋/Push한다. 작업 완료 시 기존 경기숨길 형식의 커밋 메시지를 함께 제공한다.

## 인증 성공 후 실제 경로 검증 — 2026-10-08

동일 출발·도착, 경유점 5개, `SHORTEST` 조건으로 앱에서 탄천과 원천호수 기존 입력을 각각 조회했다.
서버 호출 횟수는 처음 `0/6`에서 `2/6`이 되었으며 두 응답 모두 HTTP 200 / `OK`였다.
호수 입력은 한 점을 바꾼 비교 입력으로 자동 대체하지 않았다.

| 입력 | API 거리·시간 | 반환 구간 | 경유점 검사 | 추천 품질 |
| --- | --- | --- | --- | --- |
| 탄천 짧은 구간 왕복 시험 | 288m · 256초 | 6개 | 차이 1.9/0.6/0.2/0.8/0.5m, 순서 `PASS_WITHIN_30M` | 미승인: 반환 지점·진행 방향 검토 및 현재 통행 확인 필요 |
| 원천호수 기존 입력 | 3,297m · 4,465초 | 12개 | 차이 21.8/3.9/1.4/79.6/1.1m, 순서 `FAIL` | 미승인: `WAYPOINT_VISIT_OR_ORDER_MISMATCH`, `TARGET_WATER_NOT_ENCLOSED` |

호수의 추가 검토 항목은 `LEG_WAYPOINT_ALIGNMENT_REQUIRES_REVIEW`,
`WATER_CROSSING_REQUIRES_BRIDGE_CHECK`, `REPETITION_AND_TOPOLOGY_REVIEW_REQUIRED`다.
지도가 보이거나 출발점으로 돌아오는 것만으로 호수 한 바퀴를 인정하지 않는다.
거리·시간은 API 응답 값이며 사용자에게 맞는 목표 산책 시간이나 현장 보행 시간을 보장하지 않는다.

첫 조회에서 탄천을 표시한 뒤 호수를 표시하면 검사 실패 경로도 파란색으로 남는 표시 버그를 발견했다.
두 색상의 `RouteLineStylesSet`에 같은 ID를 사용하고 있었다.
설치된 SDK 2.15.2의 `RouteLineManager.addStylesSet`은 이미 등록된 ID이면 기존 스타일을 반환한다.
선 삭제 후에도 스타일 ID 재사용이 발생하므로 실패/미승인 상태에 서로 다른 고정 ID를 부여했다.
공식 API의 ID 정의와 조회 방식은 [RouteLineStylesSet](https://apis.map.kakao.com/android_v2/reference/com/kakao/vectormap/route/RouteLineStylesSet.html),
[RouteLineManager](https://apis.map.kakao.com/android_v2/reference/com/kakao/vectormap/route/RouteLineManager.html) 참조.

수정 후 `assembleDebug` 성공, 기존 패키지 업데이트 설치 성공.
`testDebugUnitTest` 재실행: 35개 통과, 실패/오류/건너뜀 0개. 이 단위 검사가 실제 코스 품질을 승인하는 것은 아니다.
같은 MapView에서 탄천 → 원천호수 순서로 다시 각각 1회 조회하여 탄천 파란색 → 호수 붉은색 표시를 실기기 화면으로 확인했다.
두 번째 조회도 표의 거리·시간·검사 결과와 같았으며 서버 호출 횟수는 최종 `4/6`이다.
마지막 조회 시각은 탄천 `2026-10-08T12:04:11.287029+00:00`, 원천호수 `2026-10-08T12:04:51.997373+00:00`.
실제 요금·쿼터 잔량은 카카오 콘솔에서 별도로 확인해야 한다.
API 응답과 경로선 좌표를 파일·DB에 저장하지 않았으며 화면은 메모리에서만 확인했다.

빌드·인증·실제 응답 표시 검증은 완료했지만 두 시험 입력의 추천 품질 승인은 완료하지 않았다.
특히 이 탄천 시험은 짧은 구간이고, 호수 기존 입력은 경유점/전체 순환 검사에 실패했다.

## 푸시 전 정적 검사 — 2026-10-08

Android Studio의 커밋 검사에서 48개 오류/16개 경고가 표시되었고,
사용자가 첫 오류를 `Unresolved reference: kakao`로 확인했다.
Gradle 빌드는 `com.kakao.maps.open:android:2.15.2` 의존성을 정상적으로 사용해 성공했다.
IDE에 변경된 의존성 정보가 반영되지 않았을 가능성이 있어 `File → Sync Project with Gradle Files` 실행 후 커밋 검사를 다시 확인하도록 안내했다.
IDE에서 모든 오류가 사라졌는지는 아직 확인하지 않았다.
공식 근거: [Gradle 구성 변경과 동기화](https://developer.android.com/build#sync-files).

별도 `lintDebug`에서는 기존 코드의 오류 4개가 발견되었다.

- 위치 조회 3곳: 현재 위치 요청 직전에 권한을 재확인하고 `SecurityException`을 처리해 위치 없음으로 반환한다.
  마지막 위치 조회는 권한 예외와 사용할 수 없는 provider 예외를 명시적으로 처리한다.
- 기본 테마: API 29부터 지원되는 `android:forceDarkAllowed`를 `values-v29`로 옮긴다.
  공통 테마의 전체 화면 설정은 유지하고 API 28에서는 해당 속성을 사용하지 않는다.

수정 후 `assembleDebug testDebugUnitTest lintDebug` 성공.
단위 테스트 35개 통과(실패/오류/건너뜀 0개), Lint 오류 0개/경고 11개/정보 3개.
남은 Lint 경고는 target SDK, 의존성 버전, 런처 아이콘, 기존 지도 접근성 관련 항목이다.
이 추가 수정 후 위치 권한 회수 상황의 실기기 동작과 API 28 기기 테마는 별도 검증하지 않았다.
추가 카카오 도보 API 호출은 하지 않았다.

공식 SDK/REST 근거 및 기존 API 관측은 `experiments/kakao-walking/README.md`, `STATUS.md` 참조.
