package com.gyeonggisumgil.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.gyeonggisumgil.app.BuildConfig
import com.gyeonggisumgil.app.data.ai.AiIntentProbeCases
import com.gyeonggisumgil.app.data.ai.AiPromptTemplates
import com.gyeonggisumgil.app.data.ai.AiRouteModelDecisionParser
import com.gyeonggisumgil.app.data.ai.intentProbeFailures
import com.gyeonggisumgil.app.data.gemini.GeminiApi
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Manual request-interpretation experiment. Does not call a routing API or generate a course. */
@Composable
internal fun AiIntentReviewPanel() {
    if (!BuildConfig.DEBUG) return
    val cases = AiIntentProbeCases.expanded
    var selected by remember { mutableStateOf(cases.first()) }
    var expanded by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(false) }
    var calls by remember { mutableStateOf(0) }
    var result by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val api = remember { GeminiApi(BuildConfig.GEMINI_API_KEY) }

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("산책 요청 해석 시험", style = MaterialTheme.typography.titleMedium)
            Text("디버그 시험 · 실제 코스 생성 아님", style = MaterialTheme.typography.bodySmall)
            Text("공개 장소 예시만 전송합니다. 현재 위치·주거 주소·관측 자료는 전송하지 않습니다.",
                style = MaterialTheme.typography.bodySmall)
            OutlinedButton(onClick = { expanded = true }, enabled = !loading, modifier = Modifier.fillMaxWidth()) {
                Text("시험 예시: ${selected.places.first()}")
            }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                cases.forEach { case ->
                    DropdownMenuItem(text = { Text(case.message) }, onClick = {
                        selected = case; expanded = false; result = null
                    })
                }
            }
            Text(selected.message)
            Text("기대 조건: ${selected.distance?.let { "${it}m" } ?: "거리 미지정"} · " +
                "${selected.minutes?.let { "${it}분" } ?: "시간 미지정"} · ${selected.shape}")
            Button(onClick = {
                if (loading || calls >= 8) return@Button
                val input = selected
                calls++
                loading = true
                result = null
                scope.launch {
                    try {
                        val raw = withContext(Dispatchers.IO) {
                            api.generateRouteDecision(AiPromptTemplates.buildRouteDecisionPrompt(
                                input.message, input.history, false, "관측 자료 없음", "관측 자료 없음", "검색 도구 실행 전"
                            ))
                        }
                        val failures = intentProbeFailures(input, raw)
                        val decision = AiRouteModelDecisionParser.parse(raw)
                        result = if (decision == null) "해석 실패 · 추천 미승인" else buildString {
                            appendLine(if (failures.isEmpty()) "해석 조건 통과 · 경로 추천 미승인" else "해석 검사 실패 · 추천 미승인")
                            appendLine("장소 검색어: ${decision.placeQueries.joinToString()}")
                            appendLine("거리: ${decision.distanceMeters?.let { "${it}m" } ?: "미지정"}")
                            appendLine("시간: ${decision.durationMinutes?.let { "${it}분" } ?: "미지정"}")
                            appendLine("형태: ${decision.routeShape}")
                            appendLine("확인 질문: ${decision.clarifyingQuestion ?: "없음"}")
                            appendLine("정규화 요청: ${decision.routeRequestText}")
                            if (failures.isNotEmpty()) appendLine(failures.joinToString("\n"))
                        }
                    } catch (cancelled: CancellationException) {
                        throw cancelled
                    } catch (error: Exception) {
                        result = "요청 실패 · 자동 재시도 없음 (${error.javaClass.simpleName})"
                    } finally {
                        loading = false
                    }
                }
            }, enabled = !loading && calls < 8 && BuildConfig.GEMINI_API_KEY.isNotBlank(), modifier = Modifier.fillMaxWidth()) {
                Text(if (loading) "요청 해석 중" else "선택한 예시로 AI 조회 1회 (유료)")
            }
            Text("화면 내 요청 횟수: $calls/8 · ${BuildConfig.GEMINI_MODEL}", style = MaterialTheme.typography.bodySmall)
            result?.let { Text(it) }
        }
    }
}
