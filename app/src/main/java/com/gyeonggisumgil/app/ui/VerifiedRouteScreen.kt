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
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
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
            requestStatus = "시험 입력을 직접 선택하세요. 장소 검색과 코스 자동 생성은 다음 단계입니다."
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

    fun clearResult() { result = null; renderer.clear() }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("산책 경로 검증", style = MaterialTheme.typography.titleLarge)
        Text("실제 도보 API 경로 · 추천 승인 전 시험", color = MaterialTheme.colorScheme.primary)
        if (requestedPlaceLabel != null) {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("홈에서 선택한 장소: $requestedPlaceLabel")
                    Text("이 장소의 검증된 경로는 아직 연결되지 않았습니다. 다른 시험 입력으로 자동 대체하지 않습니다.")
                    OutlinedButton(onClick = onClearRequestedPlace, enabled = !loading) { Text("장소 선택을 해제하고 시험 입력 보기") }
                }
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { profileMenu = true }, enabled = !loading && profiles.isNotEmpty() && requestedPlaceLabel == null,
                    modifier = Modifier.fillMaxWidth()) {
                    Text(selected?.getString("label") ?: "시험 입력 선택")
                }
                DropdownMenu(expanded = profileMenu, onDismissRequest = { profileMenu = false }) {
                    profiles.forEach { profile ->
                        DropdownMenuItem(text = { Text(profile.getString("label")) }, onClick = {
                            selected = profile; profileMenu = false; clearResult()
                            renderer.center(profile.getJSONArray("start"))
                            requestStatus = "경유점 5개 · 동일 출발·도착. 입력점만 검토했으며 통행과 코스 품질은 미승인입니다."
                        })
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
                }, enabled = !loading && mapReady && selected != null && requestedPlaceLabel == null,
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
            Text(if (failed) "검사 실패 · 추천 미승인\n${describeCodes(inspection.optJSONArray("failures"))}"
                else "조회 완료 · 순환·현재 통행 확인 전까지 추천 미승인",
                color = if (failed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
        }
        AndroidView(factory = { renderer.view }, modifier = Modifier.fillMaxWidth().height(300.dp))
        Text("S: 동일 출발·도착 / 1–5: 요청점 / 선: 반환된 실제 구간\n원 중심은 요청 좌표입니다. 선과 떨어진 점은 경유점 검사 결과를 확인하세요.\n파란색도 추천 승인이 아닙니다. 붉은색은 검사 실패입니다.", style = MaterialTheme.typography.bodySmall)
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(requestStatus)
                result?.let { Text(describeReview(it), style = MaterialTheme.typography.bodySmall) }
                selected?.let { profile ->
                    profile.optJSONObject("input_change")?.let { change ->
                        Text(if (change.has("alternative_start_node"))
                            "호수 외곽 보행망에서 새로 고른 비교 입력입니다. 출발점도 달라졌습니다. 원래 요청을 대체하지 않습니다."
                        else "4번을 보행로의 원본 노드로 바꾼 비교 입력입니다. 원래 요청을 대체하지 않습니다.")
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
            "WATER_CROSSING_REQUIRES_BRIDGE_CHECK" -> "수역 통과 의심 구간의 교량 확인 필요"
            "REPETITION_AND_TOPOLOGY_REVIEW_REQUIRED" -> "반복·순환 구조의 추가 검토 필요"
            "LEG_WAYPOINT_ALIGNMENT_REQUIRES_REVIEW" -> "API 구간 경계와 경유점 대응 검토 필요"
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
    return summary + (if (details.isNotEmpty()) "\n$details: OSM 교량 태그 있음 · 현재 통행·API 스냅 원인 미확인" else "") +
        "\n원본 노드 연결은 실제 통행이나 호수 한 바퀴의 증명이 아닙니다."
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
            } + "\n${describeCodes(lap.optJSONArray("failures"))}\n${describeCodes(lap.optJSONArray("unresolved"))}"
        }.orEmpty() +
        "\n순서: ${inspection.optString("waypoint_order_check", "평가 못함")}" +
        "\n동일 선분 반복: ${inspection.optDouble("exact_edge_retraced_distance_m", 0.0)}m (다른 좌표 분할의 반복은 미포함)" +
        "\n검사 실패: ${describeCodes(inspection.optJSONArray("failures"))}" +
        "\n추가 검토: ${describeCodes(inspection.optJSONArray("unresolved"))}" +
        "\n현재 출입·통행 미확인. ACCESSIBLE은 무장애 보장이 아닙니다." +
        "\n경로: 카카오 도보 API · 조회 ${response.getString("requested_at")}\n실제 요금·쿼터는 콘솔 확인 필요." +
        response.optJSONObject("water_source")?.takeIf { it.length() > 0 }?.let { "\n수역:\n${describeSource(it)}" }.orEmpty()
}
