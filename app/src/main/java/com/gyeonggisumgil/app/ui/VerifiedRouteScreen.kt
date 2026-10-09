package com.gyeonggisumgil.app.ui

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.util.Base64
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.ui.platform.LocalLifecycleOwner
import com.gyeonggisumgil.app.BuildConfig
import com.gyeonggisumgil.app.GyeonggiSumgilApplication
import com.gyeonggisumgil.app.MapSdkStartup
import com.gyeonggisumgil.app.data.places.PlaceCandidate
import com.gyeonggisumgil.app.data.routevalidation.LocalReviewGateway
import com.gyeonggisumgil.app.data.routevalidation.ReviewGateway
import com.gyeonggisumgil.app.data.routevalidation.ReviewMap
import com.kakao.vectormap.KakaoMapSdk
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import kotlin.math.ceil

/** First integrated route feature. Trial inputs are explicit; no place substitution or recommendation. */
@Composable
fun VerifiedRouteScreen(requestedPlaceLabel: String?, onClearRequestedPlace: () -> Unit) {
    val context = LocalContext.current
    var confirmedPlace by remember { mutableStateOf<PlaceCandidate?>(null) }
    val mapSdkStartup = (context.applicationContext as GyeonggiSumgilApplication).mapSdkStartup
    if (mapSdkStartup !is MapSdkStartup.Ready) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("산책 경로 검증", style = MaterialTheme.typography.titleLarge)
            PlaceDiscoveryPanel(requestedPlaceLabel.orEmpty(), confirmedPlace) { confirmedPlace = it }
            if (requestedPlaceLabel != null) Text("홈에서 선택한 장소: $requestedPlaceLabel")
            if (mapSdkStartup is MapSdkStartup.MissingKey) {
                Text("카카오 네이티브 키가 설정되지 않았습니다.")
                Text("local.properties의 KAKAO_NATIVE_APP_KEY를 설정한 뒤 다시 빌드해 주세요.")
            } else {
                Text("현재 실행 환경에서 카카오 지도 라이브러리를 불러오지 못했습니다.")
                Text("카카오 지도 SDK 지원 CPU: arm64-v8a, armeabi-v7a")
                Text("현재 실행 환경 CPU: ${Build.SUPPORTED_ABIS.joinToString()}")
                Text("Android Studio 실행 기기에서 ARM Android 휴대폰을 선택해 주세요. x86/x86_64 에뮬레이터에서는 이 SDK의 지도를 확인할 수 없습니다.")
            }
            Text("지도 확인 전까지 이 화면의 경로 조회는 중단됩니다. 홈과 AI 상담 화면은 이용할 수 있습니다.")
        }
        return
    }
    val owner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    val gateway: ReviewGateway = remember { LocalReviewGateway() }
    val renderer = remember { ReviewMap(context) }
    var profiles by remember { mutableStateOf(emptyList<JSONObject>()) }
    var selected by remember { mutableStateOf<JSONObject?>(null) }
    var mode by remember { mutableStateOf("SHORTEST") }
    var profileMenu by remember { mutableStateOf(false) }
    var modeMenu by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(true) }
    var catalogAttempt by remember { mutableStateOf(0) }
    var mapReady by remember { mutableStateOf(false) }
    var mapErrorCode by remember { mutableStateOf<Int?>(null) }
    var mapStatus by remember { mutableStateOf("로컬 검증 서버 연결 중") }
    var result by remember { mutableStateOf<JSONObject?>(null) }
    var previewingTarget by remember { mutableStateOf(false) }
    var durationText by remember { mutableStateOf("38") }
    var walkingSpeed by remember { mutableStateOf(4.0) }
    var riverCandidates by remember { mutableStateOf(emptyList<JSONObject>()) }
    var generation by remember { mutableStateOf<JSONObject?>(null) }
    var requestStatus by remember { mutableStateOf("시험 입력을 직접 선택하세요. 장소 검색과 코스 자동 생성은 다음 단계입니다.") }

    DisposableEffect(owner, renderer) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> renderer.resume()
                Lifecycle.Event.ON_PAUSE -> renderer.pause()
                else -> Unit
            }
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer); renderer.finish() }
    }

    LaunchedEffect(gateway, catalogAttempt) {
        loading = true
        mapStatus = "로컬 검증 서버 연결 중"
        try {
            val response = withContext(Dispatchers.IO) { gateway.profiles() }
            val list = response.getJSONArray("profiles")
            profiles = (0 until list.length()).map { list.getJSONObject(it) }
            check(profiles.isNotEmpty())
            requestStatus = "장소를 검색·확인하거나 시험 입력을 직접 선택하세요."
            if (BuildConfig.KAKAO_NATIVE_APP_KEY.isBlank()) {
                mapStatus = "카카오 네이티브 키 미설정 · 경로 조회 중단"
            } else {
                mapStatus = "카카오 지도 인증 중"
                renderer.start(profiles.first().getJSONArray("start"), ready = {
                    scope.launch { mapReady = true; mapErrorCode = null; mapStatus = "카카오 지도 준비 완료" }
                }, error = { code ->
                    scope.launch {
                        mapReady = false
                        mapErrorCode = code
                        mapStatus = "지도 인증/연결 실패 (${code ?: "미분류"}) · 현재 패키지 ${context.packageName}"
                    }
                })
            }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            mapStatus = "서버 연결 실패 · PC 검증 서버와 USB 연결 확인 필요"
            requestStatus = "서버와 USB 연결을 확인한 뒤 아래의 다시 연결 버튼을 누르세요. 자동 재시도는 하지 않습니다."
        } finally {
            loading = false
        }
    }

    fun clearResult() { result = null; previewingTarget = false; renderer.clear() }

    fun clearCandidates() {
        val baseId = selected?.optString("base_profile_id")
        if (!baseId.isNullOrBlank()) selected = profiles.firstOrNull { it.getString("id") == baseId }
        riverCandidates = emptyList(); generation = null; clearResult()
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("산책 경로 검증", style = MaterialTheme.typography.titleLarge)
        PlaceDiscoveryPanel(requestedPlaceLabel.orEmpty(), confirmedPlace, blocked = loading) { place ->
            confirmedPlace = place; selected = null; riverCandidates = emptyList(); generation = null; clearResult()
            if (place != null) renderer.center(JSONArray(listOf(place.point.longitude, place.point.latitude)))
            requestStatus = if (place == null) "시험 입력을 직접 선택하세요." else
                "확인한 장소의 보행망을 확보하고 대상을 확인하세요."
        }
        confirmedPlace?.let { place ->
            key(place.id) {
                SelectedPlaceRoutePanel(place, gateway, loading, mapReady,
                    onBusy = { loading = it },
                    onClear = { selected = null; clearResult() },
                    onPreview = { paths -> previewingTarget = true; renderer.previewTarget(paths) },
                    onCandidate = { profile ->
                        check(profile.getString("selected_place_id") == place.id)
                        selected = profile; clearResult(); renderer.center(profile.getJSONArray("start"))
                        requestStatus = "선택한 장소의 원본 후보 선택 · 실제 API 검증 전 · 현재 통행 미확인"
                    })
            }
        }
        Text("실제 도보 API 경로 · 추천 승인 전 시험", color = MaterialTheme.colorScheme.primary)
        selected?.optJSONObject("request_scenario")?.let { scenario ->
            Text("요청: ${scenario.getString("requested_place")}에서 ${scenario.getInt("requested_park_distance_m")}m 산책")
            Text("출발 주소: ${scenario.getString("departure_address")} · 집↔공원 접근은 별도 조회이며 이 지도는 공원 순환 후보입니다.",
                style = MaterialTheme.typography.bodySmall)
        }
        if (requestedPlaceLabel != null) {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("홈에서 선택한 장소: $requestedPlaceLabel")
                    Text("위 검색에서 장소명·주소를 확인한 뒤 같은 장소의 보행망을 확보하세요. 다른 시험 입력으로 자동 대체하지 않습니다.")
                    OutlinedButton(onClick = onClearRequestedPlace, enabled = !loading) { Text("장소 선택을 해제하고 시험 입력 보기") }
                }
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { profileMenu = true }, enabled = !loading && profiles.isNotEmpty() && requestedPlaceLabel == null && confirmedPlace == null,
                    modifier = Modifier.fillMaxWidth()) {
                    Text(selected?.getString("label") ?: "시험 입력 선택")
                }
                DropdownMenu(expanded = profileMenu, onDismissRequest = { profileMenu = false }) {
                    profiles.forEach { profile ->
                        DropdownMenuItem(text = { Text(profile.getString("label")) }, onClick = {
                            riverCandidates = emptyList(); generation = null
                            selected = profile; profileMenu = false; clearResult()
                            renderer.center(profile.getJSONArray("start"))
                            requestStatus = "경유점 5개 · 동일 출발·도착. 입력점만 검토했으며 통행과 코스 품질은 미승인입니다."
                        })
                    }
                }
                if (confirmedPlace == null && selected?.optString("shape") == "river_out_and_back") {
                    Text("하천 왕복 목표 2~3km · 기본 38분, 4km/h 가정. 거리와 시간을 함께 검사합니다.")
                    OutlinedTextField(value = durationText, onValueChange = {
                        durationText = it; clearCandidates()
                    }, label = { Text("산책 시간(분)") }, singleLine = true,
                        enabled = !loading, modifier = Modifier.fillMaxWidth(),
                        isError = durationText.toIntOrNull()?.let { it !in 1..120 } != false)
                    Text("원본 길이로 후보를 고를 때 사용할 보행 속도 가정입니다. 실제 API 예상 시간과 따로 비교합니다.",
                        style = MaterialTheme.typography.bodySmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf(3.0, 4.0, 5.0).forEach { speed ->
                            OutlinedButton(onClick = { walkingSpeed = speed; clearCandidates() }, enabled = !loading) {
                                Text("${if (walkingSpeed == speed) "✓ " else ""}${speed.toInt()}km/h")
                            }
                        }
                    }
                    Button(onClick = {
                        val profile = selected ?: return@Button
                        val minutes = durationText.toIntOrNull() ?: return@Button
                        val baseId = profile.optString("base_profile_id").takeIf { it.isNotBlank() }
                            ?: profile.getString("id")
                        val speed = walkingSpeed
                        clearCandidates(); loading = true
                        requestStatus = "원본 보행로에서 반환점 후보 계산 중 · 도보 API 호출 없음"
                        scope.launch {
                            try {
                                val response = withContext(Dispatchers.IO) { gateway.riverCandidates(baseId, minutes, speed) }
                                check(response.getInt("routing_calls_sent") == 0)
                                check(response.getString("recommendation_quality") == "NOT_ACCEPTED")
                                generation = response
                                val list = response.getJSONArray("candidates")
                                riverCandidates = (0 until list.length()).map { list.getJSONObject(it) }
                                requestStatus = if (riverCandidates.isEmpty()) "요청 조건을 만족하는 원본 후보가 없습니다."
                                    else "출발점은 유지하고 반환점 후보를 계산했습니다. 후보를 직접 선택한 뒤 실제 경로를 조회하세요."
                            } catch (cancelled: CancellationException) {
                                throw cancelled
                            } catch (_: Exception) {
                                clearCandidates(); requestStatus = "후보 계산 실패 · 입력 시간·원본 보행로·서버 확인 필요"
                            } finally { loading = false }
                        }
                    }, enabled = !loading && requestedPlaceLabel == null && confirmedPlace == null &&
                        durationText.toIntOrNull()?.let { it in 1..120 } == true,
                        modifier = Modifier.fillMaxWidth()) { Text("시간에 맞는 반환점 후보 계산") }
                    generation?.let { response ->
                        val range = response.getJSONArray("available_estimated_minutes")
                        Text("확보한 원본 구간으로 예상 ${range.getDouble(0)}–${range.getDouble(1)}분 · ${walkingSpeed.toInt()}km/h 가정 · 휴식 미포함",
                            style = MaterialTheme.typography.bodySmall)
                        Text("서로 가까운 반환점을 반복 제시하지 않도록 원본 경로를 따라 ${response.optDouble("turnpoint_separation_m", 75.0)}m 이상 간격으로 후보를 비교합니다.",
                            style = MaterialTheme.typography.bodySmall)
                        if (riverCandidates.isEmpty()) Text(when (response.getString("status")) {
                            "INSUFFICIENT_WAYPOINT_BUDGET" -> "경유점 최대 5개로 원본 굴곡을 실험 기준 안에 반영할 수 없습니다."
                            else -> "2~3km 거리와 요청 시간의 ±25%를 함께 만족하는 반환점이 없습니다. 시간 조건 또는 확보한 보행로 길이를 확인하세요."
                        }, color = MaterialTheme.colorScheme.error)
                    }
                    riverCandidates.forEachIndexed { index, profile ->
                        val meta = profile.getJSONObject("river_candidate")
                        val waypointSelection = meta.getJSONObject("waypoint_selection")
                        waypointSelection.optJSONArray("excluded_source_indices")?.let { excluded ->
                            Text("후보 ${index + 1}: 갈림길·보행로 종류 변경·교량 주변 원본 입력 ${excluded.length()}개를 중간 경유점 선택에서 제외했습니다. 실제 통행 보장은 아닙니다.",
                                style = MaterialTheme.typography.bodySmall)
                        }
                        if (meta.getJSONObject("waypoint_selection").optBoolean("source_shape_tolerance_exceeded")) {
                            Text("후보 ${index + 1}: 왕복 양쪽 경유점 배치 · 원본 굴곡 요약 오차 ${"%.1f".format(meta.getJSONObject("waypoint_selection").getDouble("max_chord_deviation_m"))}m, 5m 기준 초과. 실제 경로로 전체 보행로 일치 검사 필요.", style = MaterialTheme.typography.bodySmall)
                        }
                        OutlinedButton(onClick = {
                            selected = profile; clearResult(); renderer.center(profile.getJSONArray("start"))
                            requestStatus = "${index + 1}번 반환점 후보 선택 · 경유점 ${meta.getJSONArray("via_node_ids").length()}개 · 원본 예상이며 실제 경로·통행은 미확인"
                        }, enabled = !loading, modifier = Modifier.fillMaxWidth()) {
                            Text("${if (selected?.optString("id") == profile.getString("id")) "✓ " else ""}반환점 ${index + 1}: 원본 왕복 ${meta.getDouble("source_expected_roundtrip_m")}m · 예상 ${meta.getDouble("source_estimated_minutes")}분")
                        }
                    }
                }
                OutlinedButton(onClick = { modeMenu = true }, enabled = !loading, modifier = Modifier.fillMaxWidth()) { Text("경로 방식: $mode") }
                DropdownMenu(expanded = modeMenu, onDismissRequest = { modeMenu = false }) {
                    listOf("SHORTEST", "BROAD_FIRST", "ACCESSIBLE").forEach { option ->
                        DropdownMenuItem(text = { Text(option) }, onClick = {
                            mode = option; modeMenu = false; clearResult()
                            requestStatus = "경로 방식을 바꿨습니다. 다시 조회할 때 선택한 입력으로 1회 요청합니다."
                        })
                    }
                }
                Button(onClick = {
                    val profile = selected ?: return@Button
                    val id = profile.getString("id")
                    val requestedMode = mode
                    loading = true; clearResult(); requestStatus = "선택한 입력으로 도보 API 1회 조회 중"
                    scope.launch {
                        try {
                            val response = withContext(Dispatchers.IO) { gateway.route(id, requestedMode) }
                            check(response.getString("id") == id && response.getString("mode") == requestedMode)
                            confirmedPlace?.let { check(response.getString("selected_place_id") == it.id) }
                            check(response.getString("recommendation_quality") == "NOT_ACCEPTED")
                            renderer.draw(response)
                            result = response
                            requestStatus = "조회 완료 · 현재 통행 및 코스 품질 확인 전까지 추천 미승인"
                        } catch (cancelled: CancellationException) {
                            throw cancelled
                        } catch (_: Exception) {
                            clearResult(); requestStatus = "조회 또는 표시 실패 · 이전 경로 폐기. 호출 한도·네트워크·응답 확인 필요. 자동 재시도 없음."
                        } finally { loading = false }
                    }
                }, enabled = !loading && mapReady && selected != null &&
                    ((confirmedPlace != null && selected?.optString("selected_place_id") == confirmedPlace?.id) ||
                        (confirmedPlace == null && requestedPlaceLabel == null && selected?.optString("selected_place_id").isNullOrBlank())) &&
                    (selected?.optString("shape") != "river_out_and_back" || selected?.optJSONObject("river_candidate") != null),
                    modifier = Modifier.fillMaxWidth()) { Text(if (loading) "확인 중" else "이 입력으로 실제 경로 조회 (1회)") }
            }
        }
        Text(mapStatus, style = MaterialTheme.typography.bodySmall)
        if (mapErrorCode == 401) {
            val keyHashes = remember(context) { currentSigningKeyHashes(context) }
            val sdkRegistration = remember(context) { readSdkRegistration(context) }
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("카카오 지도 등록정보 확인", style = MaterialTheme.typography.titleSmall)
                    Text("카카오디벨로퍼스의 앱 → 플랫폼 키 → 네이티브 앱 키에서 Android 등록정보를 확인하세요.",
                        style = MaterialTheme.typography.bodySmall)
                    SelectionContainer {
                        Column {
                            Text("패키지명: ${context.packageName}", style = MaterialTheme.typography.bodySmall)
                            if (keyHashes.isEmpty()) {
                                Text("키 해시를 읽지 못했습니다. Android 서명 설정을 확인하세요.", style = MaterialTheme.typography.bodySmall)
                            } else {
                                keyHashes.forEach { keyHash ->
                                    Text("키 해시: $keyHash", style = MaterialTheme.typography.bodySmall)
                                }
                            }
                            sdkRegistration?.let { registration ->
                                Text("SDK 키 해시: ${registration.keyHash ?: "읽지 못함"}", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                    Text(sdkRegistration?.let { registration ->
                        "SDK 초기화: ${if (registration.initialized) "완료" else "미완료"}" +
                            " · 앱 키 설정: ${if (registration.configuredKeyMatches) "일치" else "불일치"}" +
                            " · 패키지 전달: ${if (registration.packageMatches) "일치" else "불일치"}"
                    } ?: "SDK 등록정보를 읽지 못했습니다.", style = MaterialTheme.typography.bodySmall)
                    Text("local.properties의 KAKAO_NATIVE_APP_KEY가 선택한 앱의 네이티브 키인지 확인하세요. 설정 저장 후 경로 탭을 다시 열어 인증을 확인하세요.",
                        style = MaterialTheme.typography.bodySmall)
                    Text("같은 앱의 카카오맵 → 사용 설정 → 상태가 ON인지, 네이티브 키가 활성 상태인지도 확인하세요.",
                        style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        if (!loading && profiles.isEmpty()) {
            OutlinedButton(onClick = { catalogAttempt += 1 }, modifier = Modifier.fillMaxWidth()) {
                Text("검증 서버 다시 연결")
            }
            Text("시험 입력 목록만 다시 가져옵니다. 실제 도보 API는 경로 조회 버튼을 눌러야 호출됩니다.",
                style = MaterialTheme.typography.bodySmall)
        }
        result?.let { response ->
            val inspection = response.getJSONObject("inspection")
            val failed = inspection.optJSONArray("failures")?.length()?.let { it > 0 } == true
            val distanceReview = inspection.optJSONObject("source_distance_comparison")?.optString("status") == "REVIEW_REQUIRED"
            Text(if (failed) "검사 실패 · 추천 미승인\n${describeCodes(inspection.optJSONArray("failures"))}"
                else if (distanceReview) "원본 왕복과 경로 길이가 달라 원인 검토 필요 · 추천 미승인"
                else "조회 완료 · 경로 조건 검사와 현재 통행 확인은 별개 · 추천 미승인",
                color = if (failed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
        }
        AndroidView(factory = { renderer.view }, modifier = Modifier.fillMaxWidth().height(300.dp))
        Text(if (previewingTarget) "주황색: OSM 원본 수역 경계·하천 선형. 실제 보행 경로나 추천 코스가 아닙니다. 선택 장소의 대상인지 확인하세요."
        else (if (result?.optString("shape") == "river_out_and_back")
            "S: 출발·복귀 / R: 반환점 / 숫자: 실제 요청 경유점\n같은 길 왕복은 지도에서 두 방향의 선이 겹칠 수 있습니다."
        else "S: 동일 출발·도착 / 숫자: 요청 경유점(최대 5개) / 선: 반환된 실제 구간") +
            "\n원 중심은 요청 좌표입니다. 선과 떨어진 점은 경유점 검사 결과를 확인하세요.\n파란색도 추천 승인이 아닙니다. 붉은색은 검사 실패입니다.", style = MaterialTheme.typography.bodySmall)
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(requestStatus)
                result?.let { Text(describeReview(it), style = MaterialTheme.typography.bodySmall) }
                selected?.let { profile ->
                    profile.optJSONObject("input_change")?.let { change ->
                        Text(if (profile.has("selected_place_id"))
                            "확인한 장소의 원본 보행망에서 생성한 입력입니다. 집↔장소 접근 경로는 포함하지 않습니다."
                        else if (change.has("alternative_start_node"))
                            "호수 외곽 보행망에서 새로 고른 비교 입력입니다. 출발점도 달라졌습니다. 원래 요청을 대체하지 않습니다."
                        else if (change.optInt("index", -1) == 5)
                            "4번을 보행로의 원본 노드로 바꾼 비교 입력입니다. 원래 요청을 대체하지 않습니다."
                        else "입력점을 바꾼 별도 비교 시험입니다. 원래 요청을 대체하지 않습니다.")
                    }
                    profile.optJSONObject("input_validation")?.let { Text(describeInputs(it), style = MaterialTheme.typography.bodySmall) }
                    Text(describeSource(profile.getJSONObject("source")), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

private data class SdkRegistration(
    val initialized: Boolean,
    val configuredKeyMatches: Boolean,
    val packageMatches: Boolean,
    val keyHash: String?
)

private fun readSdkRegistration(context: Context): SdkRegistration? = try {
    KakaoMapSdk.INSTANCE?.let { sdk ->
        SdkRegistration(
            initialized = KakaoMapSdk.isInitialized(),
            configuredKeyMatches = sdk.appKey == BuildConfig.KAKAO_NATIVE_APP_KEY,
            packageMatches = sdk.context?.packageName == context.packageName,
            keyHash = sdk.hashKey?.takeIf { it.matches(Regex("[A-Za-z0-9+/]{27}=")) }
        )
    }
} catch (_: Exception) {
    null
}

private fun currentSigningKeyHashes(context: Context): List<String> = try {
    val info = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        context.packageManager.getPackageInfo(context.packageName,
            PackageManager.PackageInfoFlags.of(PackageManager.GET_SIGNING_CERTIFICATES.toLong()))
    } else {
        @Suppress("DEPRECATION")
        context.packageManager.getPackageInfo(context.packageName, PackageManager.GET_SIGNING_CERTIFICATES)
    }
    info.signingInfo?.apkContentsSigners?.map { signature ->
        Base64.encodeToString(MessageDigest.getInstance("SHA-1").digest(signature.toByteArray()), Base64.NO_WRAP)
    }.orEmpty()
} catch (_: Exception) {
    emptyList()
}

private fun describeSource(source: JSONObject) =
    "입력: ${source.optString("attribution")} · ${source.optString("license")}\n수집: ${source.optString("retrieved_at")} (현장 관측 시각 아님)\n출처: ${source.optString("url")}\n이용 조건: ${source.optString("license_url")}"

private fun describeCodes(array: JSONArray?): String = if (array == null || array.length() == 0) "없음" else
    (0 until array.length()).joinToString("\n") { index ->
        when (val code = array.getString(index)) {
            "WAYPOINT_VISIT_OR_ORDER_MISMATCH" -> "경유점 방문·순서 조건 불일치"
            "OUTSIDE_REFERENCE_WALKWAY" -> "확인한 외곽 보행로와 반환 경로 불일치"
            "TARGET_WATER_NOT_ENCLOSED" -> "전체 수역을 둘러싸는 조건 불충족"
            "LAP_DEGENERATE_GEOMETRY" -> "면을 둘러싸는 순환선이 아님"
            "LAP_DISCONNECTED_GEOMETRY" -> "구간 끝점이 이어지지 않아 순환 평가 보류"
            "LAP_OPEN_GEOMETRY" -> "선형이 정확히 닫히지 않아 순환 평가 보류"
            "LAP_NON_SIMPLE_GEOMETRY" -> "반복·자기 접촉/교차가 있어 한 바퀴 판정 보류"
            "TARGET_WATER_INVALID_GEOMETRY" -> "수역 경계 형상 검토 필요"
            "TARGET_WATER_BOUNDARY_CONTACT_REQUIRES_REVIEW" -> "경로와 수역 경계가 겹쳐 정확도 검토 필요"
            "WATER_CROSSING_REQUIRES_BRIDGE_CHECK" -> "OSM 수역과 경로 겹침 · 교량·경계 확인 필요"
            "WATER_OVERLAP_ANALYSIS_LIMIT_REACHED" -> "수역 겹침 분석 한도 초과 · 판정 보류"
            "REPETITION_AND_TOPOLOGY_REVIEW_REQUIRED" -> "반복·순환 구조의 추가 검토 필요"
            "LEG_WAYPOINT_ALIGNMENT_REQUIRES_REVIEW" -> "API 구간 경계와 경유점 대응 검토 필요"
            "TURNPOINT_AND_DIRECTION_REVIEW_REQUIRED" -> "하천 반환점과 왕복 방향의 추가 검토 필요"
            "RIVER_SOURCE_CORRIDOR_NOT_BIDIRECTIONAL" -> "원본 구간의 동일 길 왕복 연결 불충족"
            "RIVER_REFERENCE_MISSING" -> "반환점이 지정된 원본 하천 선형 없음"
            "RIVER_STEP_CONNECTION_REVIEW_REQUIRED" -> "구간 끝점 차이로 하천 방향 평가 보류"
            "RIVER_TOO_SHORT_FOR_DIRECTION_TOLERANCE" -> "짧은 구간으로 방향 검사 기준 적용 보류"
            "RIVER_OUTSIDE_SOURCE_CORRIDOR" -> "원본 하천 보행로에서 벗어나는 구간 있음"
            "RIVER_DEPARTURE_OR_RETURN_MISMATCH" -> "하천 출발·복귀점 불일치"
            "RIVER_TURNPOINT_NOT_REACHED" -> "요청한 하천 반환점에 도달하지 않음"
            "RIVER_PROGRESS_AMBIGUOUS" -> "가까운 보행 구간이 겹쳐 진행 방향 판정 보류"
            "RIVER_UNNECESSARY_DIRECTION_REVERSAL" -> "왕복 중 불필요한 역방향 이동 감지"
            "RIVER_ANALYSIS_LIMIT_REACHED" -> "하천 선형 분석 한도 초과 · 판정 보류"
            "TARGET_DURATION_MISMATCH" -> "API 예상 시간이 요청 시간의 ±25% 범위를 벗어남"
            "TARGET_DISTANCE_MISMATCH" -> "API 반환 거리가 목표 거리 범위를 벗어남"
            "TARGET_DISTANCE_UNAVAILABLE" -> "목표 거리와 비교할 API 거리 자료 없음"
            "SOURCE_API_DISTANCE_DIFFERENCE_REVIEW_REQUIRED" -> "원본 왕복과 API 선형 길이 차이의 원인 검토 필요"
            "SOURCE_API_DISTANCE_UNAVAILABLE" -> "원본 왕복과 비교할 API 거리 자료 없음"
            else -> code
        }
    }

private fun describeInputs(audit: JSONObject): String {
    val points = audit.optJSONArray("points") ?: return "입력점 출처 평가 못함"
    val failures = audit.optJSONArray("failures")
    val summary = if (audit.optString("status") == "SOURCE_MATCHED_REVIEW_REQUIRED")
        "입력 ${points.length()}점은 원본 OSM 보행 노드와 일치 · 현재 통행 미확인"
    else "입력점 출처·연결 검사 실패: ${describeCodes(failures)}"
    val details = (0 until points.length()).map { points.getJSONObject(it) }.filter { it.optBoolean("bridge_tagged") }
        .joinToString(", ") { if (it.getString("label") == "S") "S" else "${it.getString("label")}번" }
    val waterScope = audit.optJSONArray("unresolved")?.let { warnings ->
        if ((0 until warnings.length()).any { warnings.optString(it) == "WATER_INNER_AREAS_NOT_MODELED" })
            "\n수역은 외곽 경계만 사용 · 섬과 내부 경계는 미모델링" else ""
    }.orEmpty()
    return summary + (if (details.isNotEmpty()) "\n$details: OSM 교량 태그 있음 · 현재 통행·API 스냅 원인 미확인" else "") +
        waterScope + "\n원본 노드 연결은 실제 통행이나 호수 한 바퀴의 증명이 아닙니다."
}

private fun describeReview(response: JSONObject): String {
    val inspection = response.getJSONObject("inspection")
    val distance = inspection.optDouble("distance_m")
    val time = inspection.optDouble("time_s")
    return "HTTP ${response.getInt("http_status")} / ${inspection.optString("api_status")} · 추천 미승인" +
        (if (distance.isFinite() && time.isFinite()) "\nAPI ${distance.toInt()}m · ${ceil(time / 60).toInt()}분 (${time.toInt()}초)" else "\n유효 거리·시간 없음") +
        "\n구간 ${response.getJSONArray("paths").length()}개 · 호출 ${response.getInt("calls_sent")}/${response.getInt("call_limit")}" +
        "\n경유점과 반환 선형의 차이: " + (inspection.optJSONArray("waypoint_min_distance_m")?.let { offsets ->
            (0 until offsets.length()).joinToString(", ") { index ->
                val offset = offsets.getDouble(index)
                "${index + 1}번 ${offset}m${if (offset > 30) " (검사 기준 30m 초과)" else ""}"
            }
        } ?: "평가 못함") +
        inspection.optJSONObject("lap_validation")?.let { lap ->
            "\n호수 순환: " + when (lap.optString("status")) {
                "PASS_GEOMETRY_ONLY" -> "선형 조건만 통과 · 실제 통행 미확인"
                "FAIL" -> "순환 선형 조건 불충족"
                else -> "판정 보류"
            } + "\n${describeCodes(lap.optJSONArray("failures"))}\n${describeCodes(lap.optJSONArray("unresolved"))}" +
            (if (lap.has("max_step_join_gap_m"))
                "\n구간 연결 차이 최대 ${"%.3f".format(lap.getDouble("max_step_join_gap_m"))}m · 출발/복귀 차이 ${"%.3f".format(lap.getDouble("endpoint_gap_m"))}m\n분석의 수치 동등성 기준 ${lap.getDouble("numeric_join_tolerance_m")}m · 실제 경로를 보정하지 않음"
            else "") + (lap.optJSONArray("step_join_mismatches")?.let { gaps ->
                val details = (0 until minOf(gaps.length(), 5)).joinToString(", ") { i ->
                    val gap = gaps.getJSONObject(i)
                    "${gap.getInt("after_step")}→${gap.getInt("after_step")+1}구간 ${"%.3f".format(gap.getDouble("gap_m"))}m"
                }
                if (details.isBlank()) "" else "\n연결 차이: $details${if (gaps.length()>5) " 외 ${gaps.length()-5}개" else ""}"
            } ?: "")
        }.orEmpty() +
        inspection.optJSONObject("water_overlap_evidence")?.let { evidence ->
            if (!evidence.has("inside_source_water_samples")) "\nOSM 수역 겹침: 평가 못함"
            else "\nOSM 수역 내부 검사점 ${evidence.getInt("inside_source_water_samples")}개 · 경계 안쪽 최대 ${evidence.getDouble("max_inside_offset_m")}m" +
                (if (evidence.optBoolean("bridge_source_available"))
                    "\n원본 보행 교량 5m 이내 검사점 ${evidence.getInt("near_source_bridge_samples")}개 · 태그 대조만 수행, 통행 보장 아님"
                else "\n교량 원본 없음 · 교량 대조 평가 못함") +
                (evidence.optJSONArray("steps")?.let { steps ->
                    val indices = (0 until minOf(steps.length(), 5)).joinToString(", ") { i ->
                        steps.getJSONObject(i).getInt("step").toString()
                    }
                    if (indices.isBlank()) "" else "\n수역 겹침 검사 구간: $indices${if (steps.length()>5) " 외 ${steps.length()-5}개" else ""}"
                } ?: "")
        }.orEmpty() +
        response.optJSONObject("river_candidate")?.takeIf { it.has("requested_duration_minutes") }?.let { candidate ->
            "\n요청 ${candidate.getInt("requested_duration_minutes")}분 · 원본 예상 ${candidate.getDouble("source_estimated_minutes")}분 (${candidate.getDouble("assumed_walking_speed_kmh")}km/h 가정)"
        }.orEmpty() +
        inspection.optJSONObject("target_validation")?.let { target ->
            "\n시간 조건: " + when (target.optString("status")) {
                "PASS_API_TIME_ONLY" -> "API 예상 시간 기준 ±25% 이내 · 실제 소요 시간 보장 아님"
                "FAIL" -> "요청 시간과 불일치"
                else -> "평가 못함"
            }
        }.orEmpty() +
        inspection.optJSONObject("distance_validation")?.takeIf { it.optString("status") != "NOT_REQUESTED" }?.let { distanceCheck ->
            "\n거리 조건 ${distanceCheck.getJSONArray("distance_range_m").getDouble(0).toInt()}~${distanceCheck.getJSONArray("distance_range_m").getDouble(1).toInt()}m: " + when (distanceCheck.optString("status")) {
                "PASS_API_DISTANCE_ONLY" -> "API 반환 거리 충족 · 실제 보행거리 보장 아님"
                "FAIL" -> "목표 거리 불충족 · 추천 불가"
                else -> "평가 못함"
            }
        }.orEmpty() +
        inspection.optJSONObject("source_distance_comparison")?.takeIf { it.has("api_reported_distance_m") }?.let { comparison ->
            "\n원본 단순 왕복 ${comparison.getDouble("source_expected_roundtrip_m")}m / API 거리 ${comparison.getDouble("api_reported_distance_m")}m" +
                "\n거리 차이 ${comparison.getDouble("reported_minus_source_m")}m · API 선형과 원본 차이 ${comparison.getDouble("geometry_minus_source_m")}m" +
                "\n자료별 차이·출발/복귀 처리 검토 필요. 이 차이만으로 불필요한 우회를 확정하지 않습니다."
        }.orEmpty() +
        inspection.optJSONObject("river_validation")?.let { river ->
            "\n하천 왕복: " + when (river.optString("status")) {
                "PASS_GEOMETRY_ONLY" -> "반환점·방향 선형 조건만 통과 · 현재 통행 미확인"
                "FAIL" -> "왕복 선형 조건 불충족"
                else -> "판정 보류"
            } + (if (river.has("turnpoint_min_distance_m"))
                "\n반환점 차이 ${river.getDouble("turnpoint_min_distance_m")}m · 원본 길 최대 차이 ${river.getDouble("max_corridor_offset_m")}m" else "") +
                (if (river.has("max_step_connection_difference_m"))
                    "\n응답 구간 끝점 최대 차이 ${river.getDouble("max_step_connection_difference_m")}m · 판정 보류 구간 ${river.getInt("discontinuous_step_count")}개" else "") +
                (if (river.has("outbound_backtrack_m"))
                    "\n역방향 이동: 갈 때 ${river.getDouble("outbound_backtrack_m")}m / 올 때 ${river.getDouble("inbound_backtrack_m")}m" else "")
        }.orEmpty() +
        "\n순서: ${inspection.optString("waypoint_order_check", "평가 못함")}" +
        "\n동일 선분 반복: ${inspection.optDouble("exact_edge_retraced_distance_m", 0.0)}m (다른 좌표 분할의 반복은 미포함)" +
        (if (response.optString("shape") == "river_out_and_back") "\n왕복에 필요한 재방문도 포함하며 불필요한 반복량을 뜻하지 않습니다." else "") +
        "\n검사 실패: ${describeCodes(inspection.optJSONArray("failures"))}" +
        "\n추가 검토: ${describeCodes(inspection.optJSONArray("unresolved"))}" +
        response.optJSONObject("candidate_comparison")?.let { comparison ->
            "\n후보 비교: ${comparison.getInt("tested_candidates")}/${comparison.getInt("source_candidates")}개 조회" +
                (if (comparison.optString("status") == "NO_VALIDATED_CANDIDATE")
                    " · 검증을 통과한 후보 없음. 실패한 후보를 점수로 보완하여 추천하지 않습니다."
                else " · 선형 검증 후보 있음. 현재 통행과 추천 승인은 별도입니다.") +
                "\n미조회 후보 ${comparison.getInt("untested_candidates")}개 · 자동 추가 조회 없음"
        }.orEmpty() +
        "\n현재 출입·통행 미확인. ACCESSIBLE은 무장애 보장이 아닙니다." +
        "\n경로: 카카오 도보 API · 조회 ${response.getString("requested_at")}\n실제 요금·쿼터는 콘솔 확인 필요." +
        response.optJSONObject("water_source")?.takeIf { it.length() > 0 }?.let { "\n수역:\n${describeSource(it)}" }.orEmpty()
}
