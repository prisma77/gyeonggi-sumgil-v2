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

- 기존 Android 단위 테스트 debug 35개, release 35개 통과. 서로 다른 70개 사례라는 뜻은 아니다.
- `test assembleDebug` 성공. 기존 위치 API 사용의 deprecated 경고가 남아 있다.
- 현재 연결 기기에 기존 패키지로 설치·실행 성공.
- 기기 홈 UI에서 AirKorea 측정 시각/PM10/PM2.5와 기상청 시각/기온/강수/습도/풍속 표시 확인.
  조회 표시 확인이며 관측소 좌표·현재 위치의 정확도까지 검증한 것은 아니다.
- 기기가 개발자 설정 화면으로 전환되어 경로 탭 화면 조작은 잠시 중단.
  기존 패키지에서 지도 인증·실제 경로선 표시 전체 흐름은 아직 미검증.
- 대기질·날씨 코드는 이번 단계에서 유지했지만, 위치/실제 응답/정보 정확성을 별도 검사 없이 보장하지 않는다.
- 호수 전체 순환, 현장 출입/통행, 불필요 우회/반복은 미승인.
- GitHub 원격 인증이 계정/토큰 오류로 거절됨. 단계별 로컬 커밋을 준비하며 push는 인증 후 수행.

공식 SDK/REST 근거 및 기존 API 관측은 `experiments/kakao-walking/README.md`, `STATUS.md` 참조.
