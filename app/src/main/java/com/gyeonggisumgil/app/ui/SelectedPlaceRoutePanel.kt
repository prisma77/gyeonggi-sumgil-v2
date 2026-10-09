package com.gyeonggisumgil.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.gyeonggisumgil.app.data.places.PlaceCandidate
import com.gyeonggisumgil.app.data.routevalidation.ReviewGateway
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/** Source target confirmation precedes planning; only an explicit route button spends routing calls. */
@Composable
internal fun SelectedPlaceRoutePanel(
    place: PlaceCandidate, gateway: ReviewGateway, busy: Boolean, mapReady: Boolean,
    onBusy: (Boolean) -> Unit, onClear: () -> Unit,
    onPreview: (JSONArray) -> Unit, onCandidate: (JSONObject) -> Unit
) {
    val scope = rememberCoroutineScope()
    var shape by remember { mutableStateOf("lake_loop") }
    var distanceText by remember { mutableStateOf("") }
    var network by remember { mutableStateOf<JSONObject?>(null) }
    var target by remember { mutableStateOf<JSONObject?>(null) }
    var candidates by remember { mutableStateOf(emptyList<JSONObject>()) }
    var selectedId by remember { mutableStateOf<String?>(null) }
    var status by remember { mutableStateOf("선택한 장소의 보행망을 확보한 뒤 지도에서 수역·하천 대상을 확인하세요.") }
    val distance = distanceText.toIntOrNull()
    val validDistance = if (distanceText.isBlank()) shape == "lake_loop" else distance?.let { it in 500..5000 } == true

    fun clearCandidates() { candidates = emptyList(); selectedId = null; onClear() }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("선택 장소 경로 만들기", style = MaterialTheme.typography.titleMedium)
            Text("호수 순환·하천 왕복 시험입니다. 일반 공원의 임의 순환은 아직 지원하지 않습니다.")
            listOf("lake_loop" to "호수 한 바퀴", "river_out_and_back" to "하천 왕복").forEach { (value, title) ->
                OutlinedButton(onClick = {
                    shape = value; network = null; target = null; clearCandidates()
                    status = "경로 조건을 바꿨습니다. 선택한 장소의 보행망을 다시 확보하세요."
                }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("${if (shape == value) "✓ " else ""}$title") }
            }
            OutlinedTextField(distanceText, onValueChange = { distanceText = it; clearCandidates() },
                label = { Text(if (shape == "lake_loop") "목표 거리(m) · 비우면 한 바퀴" else "왕복 목표 거리(m) · 입력 필요") },
                singleLine = true, enabled = !busy, isError = !validDistance, modifier = Modifier.fillMaxWidth())
            Text("입력한 거리의 ±10%를 검사합니다. 집↔장소 접근은 제외하고 원본 보행 노드에서 출발합니다. 한 바퀴는 기본 거리로 변환하지 않습니다.",
                style = MaterialTheme.typography.bodySmall)
            Button(onClick = {
                clearCandidates(); network = null; target = null; onBusy(true)
                status = "선택 장소 주변 OSM 보행망 확보 중 · 도보 API 호출 없음"
                scope.launch {
                    try {
                        val response = withContext(Dispatchers.IO) { gateway.selectedNetwork(place.id, shape) }
                        check(response.getString("place_id") == place.id && response.getInt("routing_calls_sent") == 0)
                        check(response.getString("recommendation_quality") == "NOT_ACCEPTED")
                        network = response
                        status = if (response.getJSONArray("targets").length() == 0)
                            "선택 장소와 대조할 수역·하천 자료가 없습니다. 다른 장소로 대체하지 않았습니다."
                        else "원본 대상 후보를 골라 지도에서 확인하세요. 가까운 이름 없는 수역은 선택한 장소와 같은 대상이라는 보장이 없습니다."
                    } catch (cancelled: CancellationException) { throw cancelled }
                    catch (_: Exception) { status = "보행망 확보 실패 · 서버·검색 유효기간·OSM 한도 확인 필요. 자동 재시도하지 않습니다." }
                    finally { onBusy(false) }
                }
            }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("선택 장소 보행망 확보 (OSM 1회)") }
            Text(status)
            network?.let { response ->
                val source = response.getJSONObject("source")
                Text("${source.optString("attribution")} · ${source.optString("license")}\n수집: ${source.optString("retrieved_at")} · 현장 관측 아님\n${source.optString("url")}\n${source.optString("license_url")}",
                    style = MaterialTheme.typography.bodySmall)
                val targets = response.getJSONArray("targets")
                for (index in 0 until targets.length()) {
                    val option = targets.getJSONObject(index)
                    OutlinedButton(onClick = {
                        clearCandidates(); target = option; onPreview(option.getJSONArray("paths"))
                        status = "주황색은 OSM 수역 경계·하천 선형이며 보행 경로가 아닙니다. 선택한 장소의 대상이 맞는지 지도에서 확인하세요."
                    }, enabled = !busy && mapReady, modifier = Modifier.fillMaxWidth()) {
                        Text("${if (target?.optString("id") == option.getString("id")) "✓ " else ""}${option.getString("name")} · POI 차이 ${option.getDouble("poi_offset_m").toInt()}m\n" +
                            if (option.getString("match") == "EXACT_NAME_AND_PROXIMITY") "이름·위치 대조 · 직접 확인 필요" else "인근 이름 없는 수역 · 동일 대상 확인 필요")
                    }
                }
            }
            target?.let { confirmed ->
                Button(onClick = {
                    clearCandidates(); onBusy(true); status = "확인한 대상의 원본 연결·거리·순환 후보 검사 중 · 도보 API 호출 없음"
                    scope.launch {
                        try {
                            val response = withContext(Dispatchers.IO) {
                                gateway.selectedCandidates(place.id, confirmed.getString("id"), distance)
                            }
                            check(response.getString("place_id") == place.id && response.getInt("routing_calls_sent") == 0)
                            check(response.getString("recommendation_quality") == "NOT_ACCEPTED")
                            val list = response.getJSONArray("candidates")
                            candidates = (0 until list.length()).map { list.getJSONObject(it) }
                            status = if (candidates.isEmpty()) when (response.getString("status")) {
                                "SOURCE_LAP_DISTANCE_MISMATCH" -> "확보한 한 바퀴 길이가 목표 거리 범위에 맞지 않습니다. 반복이나 우회를 덧붙이지 않았습니다."
                                "NO_COMPLETE_ENCLOSING_SOURCE_CYCLE" -> "전체 수역을 둘러싸는 연결된 보행 순환을 찾지 못했습니다. 끊어진 길을 연결하지 않았습니다."
                                "SOURCE_ROUNDTRIP_DISTANCE_UNAVAILABLE" -> "연결된 동일 길 왕복으로 목표 거리를 확보하지 못했습니다."
                                else -> "원본 보행망의 출발점·연결·입력 조건을 만족하는 후보가 없습니다."
                            } else "원본 후보 ${candidates.size}개입니다. 후보를 선택한 뒤 아래 실제 경로 조회로 검증하세요. 현재 통행·추천은 미승인입니다."
                        } catch (cancelled: CancellationException) { throw cancelled }
                        catch (_: Exception) { status = "후보 검사 실패 · 거리·선택 대상·유효기간·서버 확인 필요" }
                        finally { onBusy(false) }
                    }
                }, enabled = !busy && mapReady && validDistance, modifier = Modifier.fillMaxWidth()) { Text("이 대상 확인 후 후보 계산") }
            }
            candidates.forEach { profile ->
                OutlinedButton(onClick = {
                    selectedId = profile.getString("id"); onCandidate(profile)
                }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                    Text("${if (selectedId == profile.getString("id")) "✓ " else ""}${profile.getString("label")}")
                }
            }
            if (candidates.isNotEmpty()) Text("원본 노드·연결·형상을 자동 검사한 후보입니다. 실제 보행 경로·현재 통행은 별도 검사이며 POI에서 출발점까지 접근 경로는 포함하지 않습니다.",
                style = MaterialTheme.typography.bodySmall)
        }
    }
}
