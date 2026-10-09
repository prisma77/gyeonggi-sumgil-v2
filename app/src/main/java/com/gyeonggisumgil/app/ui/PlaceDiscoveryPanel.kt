package com.gyeonggisumgil.app.ui

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.gyeonggisumgil.app.data.places.LocalPlaceSearchGateway
import com.gyeonggisumgil.app.data.places.PlaceCandidate
import com.gyeonggisumgil.app.data.places.PlaceSearchGateway
import com.gyeonggisumgil.app.data.places.PlaceSearchResult
import com.gyeonggisumgil.app.data.places.findSearchLocation
import com.gyeonggisumgil.app.data.places.hasSearchLocationPermission
import com.gyeonggisumgil.app.data.places.searchLocationFor
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** Place confirmation only; a provider POI is not a walkable entrance or a verified course. */
@Composable
internal fun PlaceDiscoveryPanel(initialQuery: String, confirmed: PlaceCandidate?,
                                 blocked: Boolean = false,
                                 onSelection: (PlaceCandidate?) -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val gateway: PlaceSearchGateway = remember { LocalPlaceSearchGateway() }
    var query by remember(initialQuery) { mutableStateOf(initialQuery) }
    var loading by remember { mutableStateOf(false) }
    var result by remember(initialQuery) { mutableStateOf<PlaceSearchResult?>(null) }
    var status by remember(initialQuery) { mutableStateOf("장소를 지정하지 않으면 현재 위치 3km 주변에서 공원·호수·하천을 찾습니다.") }

    fun search() {
        if (loading || blocked) return
        val requested = query.trim()
        onSelection(null); result = null; loading = true
        status = "현재 위치와 장소 후보 확인 중"
        scope.launch {
            try {
                val location = context.findSearchLocation()
                val origin = searchLocationFor(requested, location)
                result = withContext(Dispatchers.IO) { gateway.search(requested, origin) }
                status = when {
                    result!!.candidates.isEmpty() -> "일치하는 산책 장소를 찾지 못했습니다. 다른 장소로 대체하지 않았습니다. 장소명·지역을 확인해 주세요."
                    result!!.locationUsed -> "현재 위치 기준의 검색 후보입니다. 장소명·주소를 확인하고 선택하세요. " +
                        "위치 확인 당시 정확도 약 ${origin!!.accuracyMeters.toInt()}m · 측정 후 ${origin.ageMillis / 1000}초."
                    else -> "현재 위치를 확인하지 못해 입력한 장소명으로 검색했습니다. 지역·주소를 확인하고 선택하세요."
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: IllegalArgumentException) {
                status = "현재 위치를 확인하지 못했습니다. 위치 권한·정확도·위치 설정을 확인하거나 장소·지역을 입력해 주세요."
            } catch (_: Exception) {
                status = "장소 검색 실패 · PC 검증 서버·USB 연결·검색 한도를 확인해 주세요. 자동 재시도하지 않습니다."
            } finally { loading = false }
        }
    }

    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        if (grants.values.any { it }) search()
        else { result = null; onSelection(null); status = "위치 권한이 없습니다. 장소·지역을 입력하면 이름으로 검색할 수 있습니다." }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("산책 장소 찾기", style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(query, onValueChange = {
                query = it; result = null; onSelection(null)
                status = "입력한 장소명으로 검색합니다. 비워두면 현재 위치 주변을 찾습니다."
            }, label = { Text("장소명·지역 (비우면 주변 검색)") }, singleLine = true,
                enabled = !loading && !blocked, modifier = Modifier.fillMaxWidth())
            Button(onClick = {
                if (query.isBlank() && !context.hasSearchLocationPermission()) {
                    permission.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
                } else search()
            }, enabled = !loading && !blocked && query.trim().length <= 100, modifier = Modifier.fillMaxWidth()) {
                Text(if (loading) "장소 찾는 중" else if (query.isBlank()) "현재 위치 주변 찾기" else "입력한 장소 찾기")
            }
            Text(status)
            result?.let { response ->
                val searchTime = runCatching {
                    Instant.parse(response.queriedAt).atZone(ZoneId.of("Asia/Seoul"))
                        .format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"))
                }.getOrDefault(response.queriedAt)
                Text("카카오 장소 검색 · 검색 시각(KST) $searchTime", style = MaterialTheme.typography.bodySmall)
                Text("표시 거리는 검색 기준점에서의 거리이며 실제 보행 거리와 다릅니다.", style = MaterialTheme.typography.bodySmall)
                if (response.truncated) Text("검색 결과 일부를 최대 5개 표시합니다. 전체 장소 목록은 아닙니다. 지역·장소명을 좁혀 주세요.",
                    style = MaterialTheme.typography.bodySmall)
                response.candidates.filter { confirmed == null || it.id == confirmed.id }.forEach { place ->
                    OutlinedButton(onClick = { onSelection(place) }, enabled = !loading && !blocked, modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.fillMaxWidth()) {
                            Text("${if (confirmed?.id == place.id) "✓ " else ""}${place.name}")
                            Text(place.address, style = MaterialTheme.typography.bodySmall)
                            Text(place.category, style = MaterialTheme.typography.bodySmall)
                            place.distanceMeters?.let { Text("검색 기준점에서 약 ${it.toInt()}m", style = MaterialTheme.typography.bodySmall) }
                        }
                    }
                }
            }
            confirmed?.let { place ->
                Text("확인한 장소: ${place.name} · ${place.address}")
                Text("장소 좌표는 출입구나 보행 가능 지점의 보장이 아닙니다. 보행망 확보와 대상 확인 후 경로를 검증해야 합니다.")
                OutlinedButton(onClick = { onSelection(null) }, enabled = !loading && !blocked) { Text("장소 선택 해제") }
            }
        }
    }
}
