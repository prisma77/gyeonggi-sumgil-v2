package com.gyeonggisumgil.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
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
    var mapReady by remember { mutableStateOf(false) }
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

    LaunchedEffect(gateway) {
        try {
            val response = withContext(Dispatchers.IO) { gateway.profiles() }
            val list = response.getJSONArray("profiles")
            profiles = (0 until list.length()).map { list.getJSONObject(it) }
            check(profiles.isNotEmpty())
            if (BuildConfig.KAKAO_NATIVE_APP_KEY.isBlank()) {
                mapStatus = "카카오 네이티브 키 미설정 · 경로 조회 중단"
            } else {
                mapStatus = "카카오 지도 인증 중"
                renderer.start(profiles.first().getJSONArray("start"), ready = {
                    scope.launch { mapReady = true; mapStatus = "카카오 지도 준비 완료" }
                }, error = { code ->
                    scope.launch {
                        mapReady = false
                        mapStatus = "지도 인증/연결 실패 (${code ?: "미분류"}) · 현재 패키지 com.gyeonggisumgil.app"
                    }
                })
            }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            mapStatus = "서버 연결 실패 · PC 검증 서버와 USB 연결 확인 필요"
            requestStatus = "서버 연결 후 경로 탭을 다시 여세요. 자동 재시도는 하지 않습니다."
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
        AndroidView(factory = { renderer.view }, modifier = Modifier.fillMaxWidth().height(300.dp))
        Text("S: 동일 출발·도착 / 1–5: 요청점 / 선: 반환된 실제 구간\n파란색도 추천 승인이 아닙니다. 붉은색은 검사 실패입니다.", style = MaterialTheme.typography.bodySmall)
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(requestStatus)
                result?.let { Text(describeReview(it), style = MaterialTheme.typography.bodySmall) }
                selected?.let { profile ->
                    if (!profile.isNull("input_change")) Text("한 점을 바꾼 비교 입력입니다. 원래 요청의 자동 대체가 아닙니다.")
                    Text(describeSource(profile.getJSONObject("source")), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

private fun describeSource(source: JSONObject) =
    "입력: ${source.optString("attribution")} · ${source.optString("license")}\n수집: ${source.optString("retrieved_at")} (현장 관측 시각 아님)\n출처: ${source.optString("url")}\n이용 조건: ${source.optString("license_url")}"

private fun describeCodes(array: JSONArray?): String = if (array == null || array.length() == 0) "없음" else
    (0 until array.length()).joinToString("\n") { array.getString(it) }

private fun describeReview(response: JSONObject): String {
    val inspection = response.getJSONObject("inspection")
    val distance = inspection.optDouble("distance_m")
    val time = inspection.optDouble("time_s")
    return "HTTP ${response.getInt("http_status")} / ${inspection.optString("api_status")} · 추천 미승인" +
        (if (distance.isFinite() && time.isFinite()) "\nAPI ${distance.toInt()}m · ${ceil(time / 60).toInt()}분 (${time.toInt()}초)" else "\n유효 거리·시간 없음") +
        "\n구간 ${response.getJSONArray("paths").length()}개 · 호출 ${response.getInt("calls_sent")}/${response.getInt("call_limit")}" +
        "\n경유점 차이(m): ${inspection.optJSONArray("waypoint_min_distance_m") ?: "평가 못함"}" +
        "\n순서: ${inspection.optString("waypoint_order_check", "평가 못함")}" +
        "\n검사 실패: ${describeCodes(inspection.optJSONArray("failures"))}" +
        "\n추가 검토: ${describeCodes(inspection.optJSONArray("unresolved"))}" +
        "\n현재 출입·통행 미확인. ACCESSIBLE은 무장애 보장이 아닙니다." +
        "\n경로: 카카오 도보 API · 조회 ${response.getString("requested_at")}\n실제 요금·쿼터는 콘솔 확인 필요." +
        response.optJSONObject("water_source")?.takeIf { it.length() > 0 }?.let { "\n수역:\n${describeSource(it)}" }.orEmpty()
}
