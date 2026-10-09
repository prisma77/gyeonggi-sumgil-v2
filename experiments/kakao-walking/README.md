# 카카오 도보 경로 실험

기존 Android 앱과 독립된 Python 표준 라이브러리 실험이다. 기존 앱·Gradle·키 파일을 수정하지 않는다.
실제 API 응답을 검증하기 위한 준비 도구이며 앱 추천 기능이나 순환 자동 생성기가 아니다.

## 확인 기준: 2026-10-08

- [도보 REST API](https://developers.kakao.com/docs/ko/kakaomap/rest-api#도보-경로-조회): `GET /v2/routing/walk`, REST API 키 필요.
- 입력·출력 좌표계는 명시적으로 WGS84, 좌표 배열은 `[경도, 위도]`로 처리한다.
- `via_x`, `via_y` 경유지 최대 5개. 6개는 제한 확인을 위한 명시적 부정 실험에만 사용한다.
- `SAME_POINT`가 문서에 정의된다. 동일 출발·도착 + 경유지의 실제 동작은 미검증이다.
- `totalDistance`는 m, `totalTime`은 초. 경로선은 `legs[].steps[].path.points`.
- [쿼터·요금](https://developers.kakao.com/docs/ko/getting-started/quota): 도보 무료 일간 1,000건, 유료 10원/건.
- [사용 조건](https://developers.kakao.com/docs/ko/kakaomap/common): 개발자 계정의 첫 활성화 앱만 무료 쿼터. 새 실험 앱이 무료라고 가정하지 않는다.
- [카카오 담당자 답변](https://devtalk.kakao.com/t/api/151736): 대중교통 사례에서 이동 안내 중 임시 메모리 유지·종료 후 폐기를 허용하고 결과·가공 데이터 DB 저장을 제한한다. 도보 개발용 응답 보관은 확인 전 사용하지 않는다.

## 키 준비

프로젝트 루트의 기존 `local.properties`에 사용자가 `KAKAO_REST_API_KEY` 항목을 설정하거나 실행 환경변수로 전달한다.
네이티브 앱 키를 REST 키로 대체하지 않는다. 키 값은 출력·로그·보고서에 기록하지 않는다.
자동 키 발급·앱 활성화·비즈월렛 설정은 하지 않는다.

```powershell
python experiments/kakao-walking/probe.py preflight
```

`preflight`는 네트워크 호출이 없다. 키의 존재만 확인하며 인증 유효성·카카오맵 활성화·무료 쿼터를 증명하지 않는다.
키 누락 시 종료 코드 2로 중단한다.

## 장소 확인

```powershell
python experiments/kakao-walking/probe.py search "수원 원천호수"
```

검색 후보 ID·이름·주소·분류·장소 링크를 일시적으로 표시한다. 첫 결과를 자동 선택하지 않는다.
주차장·시설과 공원/호수를 구별하고 원천호수·신대호수 같은 서로 다른 대상을 합치지 않는다.
검색 결과는 코드나 파일로 저장하지 않는다.

## 실험 대상과 입력 자료

호수 후보: 원천호수, 일산호수. 하천 후보: 탄천, 왕숙천.
이 이름들은 시험 대상 후보이며 지원을 확정한 장소가 아니다.
실제 대상·출입점·보행망의 범위를 먼저 확인한다.

`site.template.json`을 **별도 파일로 복사**하고, 저장·사용 가능한 독립 자료로 아래 항목을 채운다.

- `walk_source`: 보행 선형의 HTTPS 원본 URL, 취득 시각, 이용 조건.
- `walk_points`: 실제 선형에 있는 서로 다른 보행점 최소 8개, `[경도, 위도]`. 호수는 둘레 순서, 하천은 진행 순서.
- `reference_walkway`: 확인한 본 산책 구간의 충분히 상세한 실제 선형. 직선으로 임의 연결한 코스 사용 금지.
- `reference_segments`: 전체 순환 참고 선형이 아직 없다면 각각의 실제 원본 선분을 별도로 입력한다.
  네트워크 근접 검사는 본 둘레길과의 일치·불필요한 경로 배제를 보장하지 않는다.
- `walk_points_reviewed`: 출처·대상·보행점 검토가 끝난 뒤에만 `true`.
- 호수 `water_source`, `water_boundary`: 선택한 수역의 실제 경계와 출처. 공원 중심 좌표를 경계로 대체하지 않는다.

기존 앱의 수작업 좌표는 이 입력의 근거로 사용하지 않는다. 외부 자료는 정확도·갱신 시각·연결성·통행 제한을 검토한다.
OSM 사용 시 [ODbL 및 출처표시](https://www.openstreetmap.org/copyright)를 준수한다.
현재 템플릿은 비어 있으며 실험 입력으로 승인되지 않는다. 데이터 부족 시 실제 호출을 중단한다.

```powershell
python experiments/kakao-walking/probe.py probe experiments/kakao-walking/my-lake.json --max-calls 12 --mode SHORTEST
```

기본 매트릭스: A→B, 경유 1/3/5개, 경유 6개 부정 실험, A→A, A→경유5개→A.
호수는 반대 경유 순서도 검사한다. 하천은 출발→반환점과 반환점→출발을 각각 호출한다.
반환점은 입력된 마지막 보행점이다. 목표 거리 자동 조정은 아직 구현하지 않는다.
호수 매트릭스는 8회, 하천 매트릭스는 9회 요청한다. 오류로 더 일찍 중단할 수 있다.
호수의 5개 경유점은 입력의 둘레 순서에 분산한다. 하천의 5개 경유점에는 실제 반환점을 포함한다.
원본 점 간격이 고르지 않을 수 있으며 실제 둘레를 충분히 강제하는지 검토한다. 성공 응답도 한 바퀴를 보장하지 않는다.

`BROAD_FIRST`, `SHORTEST`, `ACCESSIBLE`을 각각 비교하되 총 호출 상한은 실험자가 합산한다.
프로세스당 상한은 기본 12회, 최대 100회. 자동 재시도·제공자 대체·출발점 이동은 없다.
401/403/429 및 네트워크 실패 시 즉시 중단한다. 6경유 부정 실험의 HTTP 400만 다음 케이스로 진행한다.
여러 실행의 실제 차감량·실패 호출 과금·무료 잔량은 카카오 콘솔에서 확인한다.

## 검사와 판정 범위

실시간 stdout에 상태·개수·거리·시간·검사 결과를 출력한다. 원문 응답·경로 좌표·헤더·키는 저장하지 않는다.
응답은 호출 중 메모리에서만 검사한다. 외부 LLM에 전달하지 않는다. 결과를 파일로 리다이렉트하지 않는다.

- HTTP 상태와 본문 `status`를 분리한다. `OK`만 선형 검사 대상.
- 좌표 유효성, 필수 선형, 0거리/시간, 구간 연결, 시작·끝점 일치를 검사한다.
- 구간 거리·시간 합계와 총합, 선형 계산 거리와 API 거리를 비교한다.
- 실제 참고 선형과의 길이 가중 근접 비율을 검사한다. 기본 20m, 90%는 **초기 실험 기준**이다.
- 호수는 복귀, 수역 경계 꼭짓점·중점 포함, 수역 횡단 의심을 검사한다.
- 수역 포함 검사는 완전한 토폴로지 증명이 아니다. 복잡한 경계·자기 교차·교량·반복은 추가 검토 대상이다.
- 작은 평행 도로는 참고 선형 근접 검사만으로 구별하지 못할 수 있다.

기준값: 구간 연결 10m, 시작·끝점 차이 30m, 거리 합계 1% 또는 2m, 선형 거리 차이 10% 또는 30m.
API 단순화·지도 해상도에 따라 조정해야 하며 보행 안전 기준으로 사용하지 않는다.
왕복의 필요한 중복은 허용하되 반환점·방향·불필요한 반복을 사람이 추가 확인한다.
경유점은 실제 반환 선분에 30m 이내로 순서대로 근접하는지 검사한다. 이 값은 스냅 진단 기준이며 실제 방문 증명은 아니다.
`legs`의 개수와 경유지 개수 관계는 공식 문서에 보장되지 않아 구간 경계 불일치는 추가 검토 대상으로 표시한다.

`geometry_check=PASS`는 일부 선형 검사의 통과만 의미한다.
순환·왕복의 추가 검토가 남으면 `INCOMPLETE`, 명시적 위반은 `FAIL`.
모든 응답의 `walking_access=UNVERIFIED`, `field_check=NOT_EXECUTED`, `recommendation_quality=NOT_ACCEPTED`를 유지한다.
실제 지도 중첩·경유점 방문·반복·교량·통행 제한·현장 확인 전에는 추천 기능으로 승격하지 않는다.

## 오프라인 검증

```powershell
python -B -m unittest discover -s experiments/kakao-walking -p 'test_*.py' -v
```

테스트의 좌표·응답은 명시적 합성 자료다. 실제 공원·실제 API 응답·추천 품질 증거가 아니다.
검사 목적: 가짜 순환, 호수를 감싸는 외곽 도로, 연결 단절, 거리 불일치, 정보 부족을 성공으로 판정하지 않기.

## 실제 응답 실험 완료 기준

1. 장소·독립 보행 선형·수역 출처 확인.
2. REST 인증·활성화·쿼터 조건 확인.
3. 최대 경유지·동일 출발/도착·응답 선형·비용을 실제 호출로 확인.
4. 실제 지도와 경로 중첩 확인, 경유지 방문 및 반복·우회 검토.
5. 호수/하천별 사용 가능·조건부·지원 불충분 판정. 필요한 현장 확인을 별도 기록.

앱 구현은 이 판정 이후 진행한다. APK 빌드와 실제 추천 품질은 별도로 보고한다.

## 확보한 OSM 자료와 입력 초안

`sources/*.osm.json`은 실제 Overpass 응답과 조회식·취득 시각·ODbL 출처를 함께 보관한다.
**이 저장 방식은 공개 OSM 자료에만 적용한다. 카카오 검색·도보 응답은 저장하지 않는다.**
자료 취득 시각과 `timestamp_osm_base`는 현장 관측 시각이 아니다.

- 원천호수 후보: OSM 수역 `way/480950645`, 주변 보행 관련 구간 143개.
  OSM 명칭은 원천저수지다. 같은 이름의 다른 지역 수역 `way/1335302902`는 사용하지 않았다.
  [수원시 공원 안내](https://www.suwon.go.kr/sw-www/sw-visitsuwon/sw-visitsuwon-01/sw-visitsuwon-01-03.jsp)와 공원 OSM 위치를 대조했다.
- 탄천: 하천 `way/768407483`의 원본 중간 노드를 기준으로 반경 500m에 해당하는 구간 56개.
  Overpass `around`는 해당 반경에 닿는 **전체 way**를 반환하므로 모든 좌표가 500m 안에 있다는 뜻이 아니다.
- `drafts/river.site.json`: `way/1286519135`의 12개 실제 노드를 사용한 짧은 실험 초안.
  원본 선형 길이 141.4m. 카카오 거리·예상 시간·추천 거리로 사용하지 않는다.
  `foot=designated`, 자전거와 공유하는 구간이며 `source=bing 2010` 태그가 있다.
  현재 통행·장소 검색 일치·출입점·반환점 검토 전이므로 `walk_points_reviewed=false`를 유지한다.

원천호수의 단순 cycle basis 탐색에서는 전체 수역 경계를 감싸는 후보를 찾지 못했다.
이 탐색은 모든 순환을 열거하지 않으므로 **보행망에 순환이 없다는 증거가 아니다.**
교량·수역 경계 정확도·연결성·조합 가능한 순환을 추가 확인해야 한다. 호수 전체 순환의 참고 선형은 아직 확정하지 않았다.
[수원시 게시 시민기자 기사](https://news.suwon.go.kr/?p=46&reqIdx=202609292259012410&viewMode=view)에
2026년 9월 28일~10월 31일 거울못쉼터 데크 공사 정보가 있어 운영 기관 공지·현장 상태 확인이 필요하다.
이 기사만으로 통제 범위나 현재 통행 가능 여부를 확정하지 않는다.

```powershell
# 조회식당 1회 요청, 기존 파일 덮어쓰기와 자동 재시도 없음
python -B experiments/kakao-walking/fetch_osm.py experiments/kakao-walking/queries/river-walkways.ql experiments/kakao-walking/sources/new-river-source.osm.json

# 선택한 실제 노드 순서가 원본 보행 구간으로 연결되는지 검사해 검토 전 초안 생성
python -B experiments/kakao-walking/prepare_site.py experiments/kakao-walking/sources/river-walkways.osm.json experiments/kakao-walking/drafts/river.selection.json experiments/kakao-walking/drafts/new-river.site.json

# 타일·외부 스크립트 없이 실제 원본 선형만 표시하는 자료 검토 화면
python -B experiments/kakao-walking/render_sources.py
```

`prepare_site.py`는 실제 연속 OSM node ID만 연결한다. 가까운 좌표·교차 선형을 근거로 연결을 만들지 않는다.
면 형상·보행 제한 구간·명시적 보행 허용이 없는 자전거도로를 제외하고 `oneway:foot`를 따른다.
장벽·조건부 통행·공사·정확도는 미검증 상태로 표시한다.

`review.html`은 브라우저에서 직접 열 수 있다. 표시된 선을 클릭하면 원본 구간 ID를 확인한다.
좌표·코스는 앱에 하드코딩하지 않았으며 이 자료는 실험과 검토용이다.

## 실제 호출 이후의 재현 범위

`drafts/river.probe.json`, `drafts/lake.probe.json`은 **독립 OSM 좌표**의 API 실험 입력이다.
`walk_points_reviewed=true`는 출처·기존 노드·태그·실험 샘플 검토만 뜻하며 현재 보행 가능성이나 코스 품질 승인이 아니다.
원본 초안 `*.site.json`은 검토 전 상태를 유지한다.

`prepare_lake_probe.py`는 수역 주변의 실제 원본 보행 노드 8개를 선택한다.
가까운 원본 노드가 없으면 중단하며 좌표 보간·임의 연결·순환 확보 주장은 하지 않는다.
`reference_scope`는 전체 보행망 후보라는 점을 명시한다.

```powershell
# 단일 진단 호출; 전체 매트릭스를 다시 호출하지 않는다
python -B experiments/kakao-walking/probe.py probe experiments/kakao-walking/drafts/lake.probe.json --case same_point_via_5 --max-calls 1 --mode SHORTEST
```

현재 카카오 접근과 경유지·동일 출발/도착의 응답 동작은 확인했다.
하천은 짧은 시험 구간의 왕복 응답 확인, 호수는 경유점 차이·수역 경계·교량 문제로 승인 보류 상태다.
원문과 반환 좌표를 저장하지 않았으므로 재검사에는 새 API 호출이 필요하다.

현재까지 장소 검색 누적 2회와 도보 요청 누적 26회였다. 실제 과금은 확인하지 않았다.
공식 유료 단가를 모든 요청에 적용한 단순 합계는 264원이나 무료 쿼터·실패 요청 차감·세금 등을 반영한 청구액이 아니다.
앱 정보의 [카카오맵 무료 쿼터] 뱃지와 [통계] > [쿼터], 비즈월렛 내역을 대조해야 한다.
단가·무료 적용 조건의 근거는 위 공식 문서 링크를 따른다.

## 호수 입력의 통제된 비교

`compare_input_point.py`는 지정한 입력 점의 **별도 비교 후보**를 만든다.
같은 원본 연결망에서 명시적 `foot` 허용 태그가 있고 교량 태그가 없는 실제 노드를 찾는다.
지정한 이동 상한을 넘거나 연결된 원본 후보가 없으면 중단한다. 현재 보행 가능성을 증명하지 않는다.
자동 경유점 대체 정책으로 앱에 넣지 않는다.

현재 비교 파일은 원본 입력 중 한 점만 변경한다. 원본 파일·수역·허용 근접 거리·실패 기준을 유지한다.
좌표는 OSM 원본이며 변경 내역과 선택 방법은 `input_change`에 남긴다.

```powershell
python -B experiments/kakao-walking/compare_input_point.py experiments/kakao-walking/sources/lake-walkways.osm.json experiments/kakao-walking/drafts/lake.probe.json experiments/kakao-walking/drafts/new-comparison.site.json --index 5 --max-move 100
```

원래 입력과 비교 입력의 `SHORTEST`, `BROAD_FIRST`, `ACCESSIBLE`을 검사했다.
비교 입력은 경유점 근접·순서 검사를 통과했으나 전체 수역 경계 조건을 충족하지 못했다.
`ACCESSIBLE`은 두 입력에서 경로를 찾지 못했다. 무장애 보행을 지원하거나 특정 장소 전체를 지원하지 않는다고 일반화하지 않는다.

추가 진단의 수역 내부 30×30 격자는 원본 수역 안에 있는 표본의 순환 횟수와 경로 내부 비율을 계산한다.
개방·단절 선형은 진단을 중단하며 가상의 연결선으로 닫지 않는다.
진단 결과를 근거로 수역 경계 실패를 성공으로 바꾸거나 추천을 승인하지 않는다.
정확히 같은 끝점 쌍의 재통과 길이는 반복의 **하한치**이며 선형 분할이 다르면 반복을 놓칠 수 있다.
현재 모든 호수 후보는 교량·경계 정확도·통제 정보·실제 지도 중첩 확인 전까지 승인 보류다.

## 입력점과 단일 순환 검증 강화 — 2026-10-08

검토 전 초안도 도보 API 없이 원본 자료와 대조할 수 있다.

```powershell
python -B experiments/kakao-walking/audit_inputs.py experiments/kakao-walking/drafts/lake.site.json experiments/kakao-walking/sources/lake-walkways.osm.json
```

`audit_inputs.py`는 좌표가 해당 원본 보행 node와 정확히 일치하는지, 출처 메타데이터와
수역 원본이 일치하는지, 실제 node ID를 공유한 보행 허용 구간으로 요청 순서와 복귀가
연결되는지 검사한다. 가까운 좌표나 평면상 교차를 연결로 만들지 않으며 `oneway:foot`를 따른다.
교량·명시적 `foot`·조건부 태그를 구분해 보고한다.
원본 노드 태그와 현재 통행은 미확인이다. 이 도구는 `walk_points_reviewed`를 변경하지 않는다.
태그 의미는 [OSM foot](https://wiki.openstreetmap.org/wiki/Key:foot),
[OSM bridge](https://wiki.openstreetmap.org/wiki/Key:bridge) 참조.

`validate_lap.py`는 실제 step의 연결과 출발점 복귀를 검사한다.
2026-10-09 보완: 1mm 이하 끝점 차이는 분석 모델에서만 수치상 동등하게 처리한다.
실제 API 응답에서 관측한 0.885mm 차이를 실제 단절로 취급했던 과도한 판정을 수정했다.
원본 API 좌표와 지도 선형은 바꾸지 않으며, 1mm를 넘는 간격은 연결하거나 닫지 않는다.
끝점 차이는 반올림하지 않은 거리와 step 번호로 보고한다. 미세한 숫자 차이가 실제 길의 단절을 뜻하지는 않는다.
자기 교차·접촉·중복을 포함하는 선형은 별도 분석이 필요하므로 보류하며 왕복·퇴화 선형은 실패한다.
단순한 닫힌 선형에 대해 수역 모든 꼭짓점과 **전체 경계 선분의 교차**를 검사한다.
꼭짓점·중점 표본만 검사했을 때 놓칠 수 있는 좁은 홈의 경계 통과를 회귀 검사한다.
수역 경계와의 접촉은 정확도 검토 대상으로 남긴다.

`PASS_GEOMETRY_ONLY`는 이 모델의 단일 수역 포함 조건만 통과했다는 뜻이다.
지역 평면 투영·부동소수점 판정을 사용하며 지형·수역 경계의 현실 정확도나 현재 통행을 증명하지 않는다.
접근 구간의 왕복, 공유 교량, 서로 다른 선형 분할의 반복을 자동 제거하거나 정상적인 한 바퀴로 승인하지 않는다.
수역 격자와 정확한 동일 선분 반복은 계속 진단 용도다. 단절·개방 선형의 수역 포함·격자 결과는 만들지 않는다.

오프라인 검사 70개 통과. 합성 자료 검사와 기존 실제 입력의 차단 검사이며 코스 품질 증거가 아니다.
Android bridge 검사 8개와 실제 후속 실험은 `docs/reboot-route-integration.md`의 최신 기록을 따른다.

## 연결된 원본 보행망에서 외곽 후보 찾기 — 2026-10-09

`fetch_osm_bbox.py`는 기존 원본 수역의 경계에서 150m 확장한 작은 영역을
[공식 OSM Map API](https://wiki.openstreetmap.org/wiki/API_v0.6#Retrieving_map_data_by_bounding_box:_GET_/api/0.6/map)로 한 번 읽는다.
JSON way의 좌표는 반환된 node ID의 실제 좌표로만 구성한다. ODbL 출처·수집 시각을 함께 저장한다.
Overpass 질의 두 건이 HTTP 504로 실패해 독립적인 원본 추출 방법을 사용했으며 자동 재시도하지 않았다.
계단도 보행망에 포함하되 `foot`·`access` 제한과 `oneway:foot`를 유지한다.
계단의 보행 허용은 휠체어 접근 가능성의 증명이 아니다.

`plan_source_cycle.py`는 특정 공원 좌표 없이 지정한 원본 수역과 시작 node를 사용한다.
수역과 교차하는 원본 간선을 제외하고 방향 그래프에서 한 번 회전하는 닫힌 경로를 탐색한다.
그 안에서 자기 교차가 없고 전체 수역을 감싸는 단순 원본 순환을 검사한다.
출발점의 진입 왕복을 제외하면 출발점 변경을 명시하고, 순환 위 지상 원본 노드를 순서대로 고른다.
경계가 오목해 평균점이 수역 밖이면 분석용 내부 기준점을 원본 경계의 scanline 구간에서 계산한다.
이 기준점은 산책 입력이나 반환 경로 좌표로 쓰지 않는다. 필요한 원본 연결이 없으면 중단한다.
교량을 배제한 간선 탐색은 전체 수역 포함을 위한 기하 검색이며 교량 통행 불가 판정이 아니다.
기본 결과는 검토 전 초안이며, 독립 입력 검토를 수행한 뒤에만 `--review-source-inputs`로 실험할 수 있다.
이 플래그는 현재 통행이나 추천 품질을 승인하지 않는다.

```powershell
python -B experiments/kakao-walking/plan_source_cycle.py experiments/kakao-walking/sources/lake-walkways-bbox.osm.json experiments/kakao-walking/drafts/new-cycle.site.json --water-way 480950645 --start-node 5548419116
```

원천호수 원본 순환 후보는 3,017.1m지만 실제 카카오 경로는 3,204m로 다르다.
경유점 방문 검사는 통과했지만 3번 차이 28.7m, 동일 선분 재통과 하한 22.1m,
선택한 외곽 원본 경로와의 근접 비율 63.79%로 추천 승인은 계속 미완료다.
99.83%의 수역 격자 포함도 표본 진단이며 전체 수역 순환 성공으로 사용하지 않는다.

## 다른 호수·하천 구간 실험

신대호수와 탄천 527m 별도 보행로를 추가했다. 실제 도보 조회 4회와 휴대폰 지도 확인 결과는
[OTHER_ROUTES.md](OTHER_ROUTES.md)에 기록했다. 테스트 92개 통과와 실제 추천 승인 여부를 구분한다.

`source_water.py`는 닫힌 원본 수역 way 또는 단일 닫힌 outer way를 가진 multipolygon relation을 읽는다.
여러 outer나 분할 outer는 지원하지 않는다. inner 영역은 현재 미모델링으로 표시한다.
`prepare_lake_probe.py --water-relation <ID> --ground-only`는 실제 호숫가 지상 원본 노드만 선택한다.
완성된 보행 순환이 확보되지 않았으면 `closed_walkway_found=false`를 유지한다.

시험 파일의 선택적 `via_sample_indices`는 원본 노드 목록에서 순서대로 경유지 5개를 지정한다.
중복·역순·범위 초과·5개 초과와 하천의 실제 끝점 누락을 거절한다.
현재 신대호수 북쪽 비교는 5번을 다른 원본 노드로 옮긴 별도 시험으로,
원래 파일·출발점·다른 경유점은 그대로 유지했다. source 입력 검토와 현장 통행 승인은 다르다.

## 요청 시간에 따른 하천 반환점 후보

원본 양방향 보행로의 기존 노드에서 반환점 후보를 최대 3개 계산한다.
출발점은 유지하고, 실제 노드에서 원본 굴곡을 반영하는 경유지를 최대 5개 선택한다.
원본 길이·명시한 보행 속도로 계산한 예상과 실제 API 거리·시간을 분리해 표시한다.
후보 계산은 도보 호출이 없으며 요청 시간을 맞출 데이터가 부족하면 후보를 반환하지 않는다.
반환점 도달·왕복 방향·불필요한 역행과 실제 API 시간 차이를 검사한다.
실제 10분·12분 조회와 30분 데이터 부족 확인, 실험 기준·남은 한계는
[RIVER_ALGORITHM.md](RIVER_ALGORITHM.md)에 기록했다. 추천·현재 통행은 미승인이다.

후속 앱 하천 기본 목표는 2~3km이며 거리와 시간을 함께 검사한다.
`river-extended`는 같은 출발점에서 확장된 독립 OSM 입력의 시험이다.
왕복 양쪽에 총 5개 이하의 실제 원본 경유점을 배치하며 실제 응답은 2,664m·2,508초다.
원본 선형 불일치와 구간 끝점 차이가 남아 추천은 미승인이다. 세부 결과는 위 기록의 마지막 절을 따른다.

후속 알고리즘은 반환점 간격 75m, 원본 입력 모호성 선별, 연결 보류 중 독립 step 검사,
실패/보류 후보의 비교 차단을 추가했다. `compare_candidates.py`는 검증된 선형 후보만 비교하고
통과 후보가 없으면 ID를 반환하지 않는다. 실제 7회 실험과 기기 확인에서도 현재 탄천 코스는 미승인이다.
테스트 130개 통과와 실제 추천 품질을 구분한다. 기록의 마지막 절 참조.
