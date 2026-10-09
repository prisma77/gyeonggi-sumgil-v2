package com.gyeonggisumgil.app.data.gemini

import com.google.gson.JsonParser
import com.gyeonggisumgil.app.data.ai.AiRouteModelDecisionParser
import com.gyeonggisumgil.app.data.ai.AiRouteModelIntent
import com.gyeonggisumgil.app.data.ai.AiRouteShapeHint
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue

/** Request fixtures only. These place names are not routing coordinates or verified place matches. */
internal data class GeminiIntentProbeCase(
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

internal object GeminiIntentProbeCases {
    val expanded = listOf(
        GeminiIntentProbeCase("misa_park_distance", "미사호수공원 안에서만 3km 걷고 싶어. 공원까지 이동하는 거리는 제외해.",
            places = listOf("미사호수공원"), distance = 3000, parkOnly = true),
        GeminiIntentProbeCase("wangsong_lap", "왕송호수 한 바퀴 산책하고 싶어", places = listOf("왕송호수"),
            shape = AiRouteShapeHint.LakeLoop),
        GeminiIntentProbeCase("ilsan_time", "일산호수공원에서 30분 걷고 싶어", places = listOf("일산호수공원"), minutes = 30),
        GeminiIntentProbeCase("sindae_lap", "광교호수공원 신대호수 한 바퀴 산책하고 싶어", places = listOf("신대호수"),
            shape = AiRouteShapeHint.LakeLoop),
        GeminiIntentProbeCase("anyang_return", "안양천에서 2.5km 왕복 산책 코스", places = listOf("안양천"), distance = 2500,
            shape = AiRouteShapeHint.RiverOutAndBack),
        GeminiIntentProbeCase("jungnang_time", "중랑천에서 30분 산책하고 싶어", places = listOf("중랑천"), minutes = 30),
        GeminiIntentProbeCase("olympic_lap", "올림픽공원 한 바퀴 산책 코스", places = listOf("올림픽공원"),
            shape = AiRouteShapeHint.Loop),
        GeminiIntentProbeCase("ambiguous_park", "중앙공원에서 3km 산책하고 싶어", places = listOf("중앙공원"), distance = 3000,
            clarification = true)
    )
}

internal fun validateIntentProbe(case: GeminiIntentProbeCase, raw: String) {
    val root = JsonParser.parseString(raw).asJsonObject
    assertEquals("Unexpected schema fields", setOf("intent", "needs_clarification", "clarifying_question",
        "route_request_text", "place_queries", "distance_meters", "duration_minutes", "activity",
        "route_shape", "use_current_location"), root.keySet())
    val decision = checkNotNull(AiRouteModelDecisionParser.parse(raw))
    assertEquals("Intent", AiRouteModelIntent.Route, decision.intent)
    // Allow a more specific search phrase only when it consists of names in the user's request.
    // In particular, 신대호수 must remain explicit and 원천호수 is never an acceptable replacement.
    assertTrue("Requested place must be retained", case.places.all { expected ->
        decision.placeQueries.firstOrNull()?.contains(expected) == true
    })
    assertTrue("No invented place alternatives", decision.placeQueries.all { query ->
        (case.message + " " + case.history).contains(query)
    })
    assertEquals("Distance", case.distance, decision.distanceMeters)
    assertEquals("Duration", case.minutes, decision.durationMinutes)
    assertEquals("Shape", case.shape, decision.routeShape)
    assertEquals("Clarification", case.clarification, decision.needsClarification)
    assertEquals("No current-location substitution", false, decision.useCurrentLocation)
    if (case.clarification) {
        val question = decision.clarifyingQuestion
        assertNotNull("Clarifying question", question)
        assertTrue("Ask region without guessing one", question!!.contains("지역") ||
            question.contains("어디") || question.contains("도시"))
    }
    if (case.parkOnly) {
        assertTrue("Park distance scope", decision.routeRequestText.contains("공원"))
        assertTrue("Exclude access distance", decision.routeRequestText.contains("제외") ||
            decision.routeRequestText.contains("안에서만") || decision.routeRequestText.contains("구간만") ||
            decision.routeRequestText.contains("내에서"))
    }
}
