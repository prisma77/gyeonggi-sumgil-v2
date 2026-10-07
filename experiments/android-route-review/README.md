# Android 경로 검증 앱

> 사용자 요청으로 실행 대상이 기존 `com.gyeonggisumgil.app`으로 변경됐다.
> 이 폴더의 별도 Android 프로젝트는 이전 검증 참고 자료다.
> **현재는 저장소 루트의 앱을 실행**한다. [통합 실행 안내](../../docs/reboot-route-integration.md)를 따른다.
> 이 폴더의 PC `bridge.py`, 시험 목록, 경계 검사는 계속 사용한다.
> 아래 `.review` 패키지 등록과 별도 Android 빌드 방법은 이전 실험 기록이다.

별도 Gradle 프로젝트와 패키지 `com.gyeonggisumgil.review`로 만든 개발용 화면.
기존 Android 앱 소스·설정·설치 패키지를 변경하지 않는다.
시험 입력 선택 → 수동 1회 조회 → 실제 API 선형과 검사 결과 표시만 담당한다.
장소 검색·자연어·추천 생성·현재 위치·날씨·대기질은 아직 구현하지 않았다.

## 경계와 데이터

- `ReviewGateway`: Android가 받는 최소한의 시험 입력·결과 인터페이스.
- `LocalReviewGateway`: USB `adb reverse`로 PC loopback 서버 접속. 운영 서버 아님.
- `ReviewMap`: 카카오 Android SDK로 반환된 각 step을 개별 RouteLine으로 표시.
  끊어진 구간 사이에 직선을 만들지 않고, API 경로를 보정·대체하지 않는다.
- `bridge.py`: REST 키는 PC에서만 읽고, 기존 실험 검사기에 실제 응답을 전달한다.
  GET `/profiles`는 유료 API를 호출하지 않는다. POST `/route`는 검토된 입력 id와 mode만 허용.
  한 요청에 실제 도보 API 1회, 자동 재시도 없음. 서버 기본 누적 한도 6회.
  loopback 바인딩, 요청 크기 제한, 브라우저 Origin 차단, `Cache-Control: no-store`.
- 카카오 원문·좌표·검색 결과를 파일·DB·로그에 보관하지 않는다. 좌표는 응답 처리와
  Android 화면 표시 중 메모리에서만 사용. 화면 종료 시 지도를 종료하고 결과 참조 해제.
  네이티브 키는 SDK 인증에 필요한 APK 설정이고, REST 키는 APK에 포함하지 않는다.
- `catalog.json`은 독립 OSM 원본에서 검토한 기존 실험 파일을 참조하는 **시험 목록**이다.
  새 검토 파일을 추가할 수 있다. 특정 공원용 좌표를 Android 코드에 넣지 않았다.
  자동 후보 생성·장소 검색 결과 선택·운영 추천 입력으로 사용하지 않는다.
- 호수 원본과 한 점 비교 입력은 별도 선택 항목. 비교 입력은 자동 요청 대체가 아니다.
  모든 응답은 `NOT_ACCEPTED`. 시험 구간 통과를 전체 하천·호수 품질 승인으로 확대하지 않는다.
- S는 동일 출발/도착, 1–5는 **요청한 입력점**이다. 실제 방문 차이는 검사 결과에서 확인한다.
  선 색은 기하 검사 실패 시 붉은색, 그 외 파란색. 파란색도 추천 승인을 뜻하지 않는다.

## 카카오 설정

루트의 기존 `local.properties`에서 정확한 키 이름만 읽는다. 값을 Git에 올리지 않는다.

```properties
KAKAO_NATIVE_APP_KEY=지도용 네이티브 키
KAKAO_REST_API_KEY=PC 서버용 REST 키
```

카카오디벨로퍼스에서 같은 앱의 네이티브 키에 Android 앱 정보를 등록한다.
현재 PC의 기본 debug 서명을 keytool SHA-1 인증서로 확인한 값:

```text
패키지: com.gyeonggisumgil.review
디버그 키 해시: ExtIkfKlzEW953nke0Y3LuFnwWM=
```

다른 PC/서명을 사용하면 키 해시를 다시 계산한다. 키 해시는 앱 키와 다른 값이다.
카카오맵 사용 설정 ON, 네이티브 키 일치, 패키지 및 키 해시 등록을 확인한다.
등록·활성화·무료 쿼터·청구 상태는 계정 콘솔에서 확인해야 한다.

## 실행 (저장소 루트의 PowerShell)

SDK 경로만 별도 프로젝트의 ignored `local.properties`에 설정한다.
루트의 키를 복사하지 않는다. 필요 시 Android Studio에서 이 별도 폴더를 연다.

```powershell
$reviewSdkProperties = Get-Content local.properties | Where-Object { $_ -match '^sdk\.dir=' }
Set-Content experiments/android-route-review/local.properties $reviewSdkProperties -Encoding ascii
$env:JAVA_HOME = 'C:/Program Files/Android/Android Studio/jbr'
.\gradlew.bat assembleDebug -p experiments/android-route-review --console=plain
```

PC 서버를 별도 터미널에서 실행한다. REST 요청 원문을 저장하지 않는다.

```powershell
python -B experiments/android-route-review/bridge.py --max-calls 6
```

연결 기기의 id를 `adb devices`에서 확인해 명령에 지정한다.

```powershell
adb -s DEVICE_ID reverse tcp:8769 tcp:8769
adb -s DEVICE_ID install -r experiments/android-route-review/app/build/outputs/apk/debug/app-debug.apk
adb -s DEVICE_ID shell am start -n com.gyeonggisumgil.review/.MainActivity
```

앱에서 시험 입력과 mode를 선택하고 버튼을 한 번 누른다.
지도 인증 실패 시 버튼을 비활성화해 경로를 소비하지 않는다.
입력·mode 변경, 새 조회 시작 또는 오류 시 이전 결과를 지운다.
회전·앱 재생성은 결과를 복원하거나 API를 자동 재호출하지 않는다.
서버 한도 초과는 오류로 표시하며 재시작은 명시적인 새 호출 예산이다.
서버 종료는 터미널 Ctrl+C. 사용 후 reverse도 해제할 수 있다.

```powershell
adb -s DEVICE_ID reverse --remove tcp:8769
```

release variant는 비활성화했다. 운영 인증·TLS 서버·배포용 설정은 다음 설계 대상이다.

## 검증 구분

```powershell
python -B -m unittest discover -s experiments/android-route-review -p 'test_*.py'
python -B -m unittest discover -s experiments/kakao-walking -p 'test_*.py'
```

서버 경계 6개 + 경로 검사 45개는 합성/원본 입력 검사다. 실제 추천 품질 검사와 구분한다.
빌드 성공도 기기 지도 인증·실제 선형 표시·현장 통행을 증명하지 않는다.
단계별 실제 실행 결과는 `STATUS.md`에서 기록한다.

실제 bridge 응답 전달 검사는 별도로 실행한다. 이 명령은 도보 API **1회**를 소비한다.
선형은 파일에 저장하거나 출력하지 않고 구간/좌표 개수·거리·시간·검사 상태만 출력한다.

```powershell
python -B experiments/android-route-review/smoke_bridge.py --route river
```

## 공식 문서 (2026-10-08 확인)

- [Android 시작/인증/SDK 2.15.2](https://apis.map.kakao.com/android_v2/docs/getting-started/quickstart/)
- [RouteLine](https://apis.map.kakao.com/android_v2/docs/api-guide/routeline/)
- [카카오맵 활성화와 플랫폼 정보](https://developers.kakao.com/docs/ko/kakaomap/common)
- [도보 REST API](https://developers.kakao.com/docs/ko/kakaomap/rest-api#도보-경로-조회)
- [인증 오류 클래스](https://apis.map.kakao.com/android_v2/reference/com/kakao/vectormap/MapAuthException.html)

SDK는 선형을 표시하며 산책 코스나 호수 순환을 계산하는 도구로 가정하지 않는다.
공식 API가 반환하지 않은 연결·좌표·거리를 만들지 않는다.
