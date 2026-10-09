package com.gyeonggisumgil.app.data.gemini

import org.junit.Test

class GeminiIntentProbeValidationTest {
    private val misa = GeminiIntentProbeCases.expanded.first()
    private fun misaResponse(shape: String = "unknown", extra: String = "") = """
        {"intent":"route","needs_clarification":false,"clarifying_question":null,
        "route_request_text":"미사호수공원 내부에서만 3km (접근 거리 제외)",
        "place_queries":["미사호수공원"],"distance_meters":3000,"duration_minutes":null,
        "activity":"walk","route_shape":"$shape","use_current_location":false$extra}
    """.trimIndent()

    @Test
    fun acceptsParkDistanceWithoutInventedShape() {
        validateIntentProbe(misa, misaResponse())
    }

    @Test(expected = AssertionError::class)
    fun rejectsPreviouslyObservedInventedLakeLoop() {
        validateIntentProbe(misa, misaResponse(shape = "lake_loop"))
    }

    @Test(expected = AssertionError::class)
    fun rejectsCoordinatesAddedToDecision() {
        validateIntentProbe(misa, misaResponse(extra = ",\"latitude\":37.5"))
    }

    @Test(expected = AssertionError::class)
    fun rejectsSubstitutionOfCurrentLocation() {
        validateIntentProbe(misa, misaResponse().replace("\"use_current_location\":false", "\"use_current_location\":true"))
    }

    @Test(expected = AssertionError::class)
    fun rejectsDefaultDistanceForOneLap() {
        validateIntentProbe(GeminiIntentProbeCases.expanded[1], """
            {"intent":"route","needs_clarification":false,"clarifying_question":null,
            "route_request_text":"왕송호수 한바퀴","place_queries":["왕송호수"],
            "distance_meters":2500,"duration_minutes":null,"activity":"walk",
            "route_shape":"lake_loop","use_current_location":false}
        """.trimIndent())
    }
}
