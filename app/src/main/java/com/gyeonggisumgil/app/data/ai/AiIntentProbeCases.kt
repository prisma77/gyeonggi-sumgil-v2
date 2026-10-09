package com.gyeonggisumgil.app.data.ai

import com.google.gson.JsonParser

/** Request fixtures only. These place names are not routing coordinates or verified place matches. */
internal data class AiIntentProbeCase(
    val id: String,
    val message: String,
    val history: String = "",
    val places: List<String>,
    val distance: Int? = null,
    val minutes: Int? = null,
    val shape: AiRouteShapeHint = AiRouteShapeHint.Unknown,
    val clarification: Boolean = false,
    val parkOnly: Boolean = false
)

internal object AiIntentProbeCases {
    val expanded = listOf(
        AiIntentProbeCase("misa_park_distance", "미사호수공원 안에서만 3km 걷고 싶어. 공원까지 이동하는 거리는 제외해.",
            places = listOf("미사호수공원"), distance = 3000, parkOnly = true),
        AiIntentProbeCase("wangsong_lap", "왕송호수 한 바퀴 산책하고 싶어", places = listOf("왕송호수"),
            shape = AiRouteShapeHint.LakeLoop),
        AiIntentProbeCase("ilsan_time", "일산호수공원에서 30분 걷고 싶어", places = listOf("일산호수공원"), minutes = 30),
        AiIntentProbeCase("sindae_lap", "광교호수공원 신대호수 한 바퀴 산책하고 싶어", places = listOf("신대호수"),
            shape = AiRouteShapeHint.LakeLoop),
        AiIntentProbeCase("anyang_return", "안양천에서 2.5km 왕복 산책 코스", places = listOf("안양천"), distance = 2500,
            shape = AiRouteShapeHint.RiverOutAndBack),
        AiIntentProbeCase("jungnang_time", "중랑천에서 30분 산책하고 싶어", places = listOf("중랑천"), minutes = 30),
        AiIntentProbeCase("olympic_lap", "올림픽공원 한 바퀴 산책 코스", places = listOf("올림픽공원"),
            shape = AiRouteShapeHint.Loop),
        AiIntentProbeCase("ambiguous_park", "중앙공원에서 3km 산책하고 싶어", places = listOf("중앙공원"), distance = 3000,
            clarification = true)
    )
}

internal fun intentProbeFailures(case: AiIntentProbeCase, raw: String): List<String> {
    val failures = mutableListOf<String>()
    fun verify(condition: Boolean, label: String) { if (!condition) failures += label }
    try {
        val root = JsonParser.parseString(raw).asJsonObject
        verify(root.keySet() == setOf("intent", "needs_clarification", "clarifying_question",
            "route_request_text", "place_queries", "distance_meters", "duration_minutes", "activity",
            "route_shape", "use_current_location"), "JSON 필드 불일치")
        val decision = AiRouteModelDecisionParser.parse(raw) ?: return listOf("해석 JSON 파싱 실패")
        verify(decision.intent == AiRouteModelIntent.Route, "경로 요청 분류 불일치")
        verify(case.places.all { decision.placeQueries.firstOrNull()?.contains(it) == true }, "요청 장소 불일치")
        verify(decision.placeQueries.all { (case.message + " " + case.history).contains(it) }, "요청하지 않은 장소 추가")
        verify(case.distance == decision.distanceMeters, "거리 조건 불일치")
        verify(case.minutes == decision.durationMinutes, "시간 조건 불일치")
        verify(case.shape == decision.routeShape, "순환·왕복 조건 불일치")
        verify(case.clarification == decision.needsClarification, "확인 질문 조건 불일치")
        verify(!decision.useCurrentLocation, "현재 위치로 대체")
        if (case.clarification) {
            val question = decision.clarifyingQuestion.orEmpty()
            verify(question.contains("지역") || question.contains("어디") || question.contains("도시"), "지역 확인 질문 누락")
        }
        if (case.parkOnly) {
            verify(decision.routeRequestText.contains("공원"), "공원 거리 범위 누락")
            verify(listOf("제외", "안에서만", "구간만", "내에서").any { decision.routeRequestText.contains(it) }, "접근 거리 제외 조건 누락")
        }
    } catch (_: Exception) {
        failures += "해석 JSON 형식 오류"
    }
    return failures
}
