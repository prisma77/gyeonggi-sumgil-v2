package com.gyeonggisumgil.app.data.gemini

import com.google.gson.JsonParser
import com.gyeonggisumgil.app.BuildConfig
import com.gyeonggisumgil.app.data.ai.AiPromptTemplates
import com.gyeonggisumgil.app.data.ai.AiRouteModelDecisionParser
import com.gyeonggisumgil.app.data.ai.AiRouteModelIntent
import com.gyeonggisumgil.app.data.ai.AiRouteShapeHint
import okhttp3.OkHttpClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.util.concurrent.TimeUnit

/** Explicitly opted-in paid probe. Uses public place names only; no location or residential address. */
class GeminiLiveProbeTest {
    @Test
    fun expandedPublicPlaceIntentProbe() {
        assumeTrue("Expanded live probe disabled", System.getenv("SUMGIL_RUN_GEMINI_PROBE") == "expanded")
        check(BuildConfig.GEMINI_API_KEY.isNotBlank()) { "GEMINI_API_KEY is missing" }
        val cases = GeminiIntentProbeCases.expanded
        val failures = mutableListOf<String>()
        var calls = 0
        var promptTokens = 0
        var outputTokens = 0
        var thoughtTokens = 0
        var finishReason: String? = null
        val client = OkHttpClient.Builder().retryOnConnectionFailure(false).followRedirects(false)
            .connectTimeout(5, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS).callTimeout(25, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                check(calls < 8) { "Paid expanded probe call limit reached" }
                calls++
                val response = chain.proceed(chain.request())
                if (response.isSuccessful) {
                    val root = JsonParser.parseString(response.peekBody(128_000).string()).asJsonObject
                    finishReason = root.getAsJsonArray("candidates")?.firstOrNull()?.asJsonObject?.get("finishReason")?.asString
                    root.getAsJsonObject("usageMetadata")?.let { usage ->
                        promptTokens += usage.get("promptTokenCount")?.asInt ?: 0
                        outputTokens += usage.get("candidatesTokenCount")?.asInt ?: 0
                        thoughtTokens += usage.get("thoughtsTokenCount")?.asInt ?: 0
                    }
                }
                response
            }.build()
        val api = GeminiApi(BuildConfig.GEMINI_API_KEY, BuildConfig.GEMINI_MODEL, client)
        try {
            cases.forEach { case ->
                val raw = api.generateRouteDecision(AiPromptTemplates.buildRouteDecisionPrompt(
                    userMessage = case.message, recentConversation = case.history, hasCurrentLocation = false,
                    airSummary = "관측 자료 없음", weatherSummary = "관측 자료 없음", trailSummary = "검색 도구 실행 전"
                ))
                println("expanded_case=${case.id}, finish=$finishReason, response=$raw")
                try {
                    assertEquals("Complete response required", "STOP", finishReason)
                    validateIntentProbe(case, raw)
                    println("expanded_case=${case.id}, status=PASS")
                } catch (error: AssertionError) {
                    failures += "${case.id}: ${error.message}"
                    println("expanded_case=${case.id}, status=FAIL, reason=${error.message}")
                }
            }
            assertTrue(failures.joinToString("\n"), failures.isEmpty())
        } finally {
            println("expanded_model=${BuildConfig.GEMINI_MODEL}, calls=$calls, failures=${failures.size}, prompt_tokens=$promptTokens, output_tokens=$outputTokens, thought_tokens=$thoughtTokens")
        }
    }

    @Test
    fun publicPlaceIntentProbe() {
        assumeTrue("Live probe disabled", System.getenv("SUMGIL_RUN_GEMINI_PROBE") == "1")
        check(BuildConfig.GEMINI_API_KEY.isNotBlank()) { "GEMINI_API_KEY is missing" }
        var calls = 0
        var promptTokens = 0
        var outputTokens = 0
        var thoughtTokens = 0
        val client = OkHttpClient.Builder().retryOnConnectionFailure(false)
            .connectTimeout(5, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS).callTimeout(25, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                check(calls < 3) { "Paid probe call limit reached" }
                calls++
                val response = chain.proceed(chain.request())
                if (response.isSuccessful) {
                    val root = JsonParser.parseString(response.peekBody(128_000).string()).asJsonObject
                    println("probe_http=${response.code}, finish=${root.getAsJsonArray("candidates")?.firstOrNull()?.asJsonObject?.get("finishReason")}")
                    root.getAsJsonObject("usageMetadata")?.let { usage ->
                        promptTokens += usage.get("promptTokenCount")?.asInt ?: 0
                        outputTokens += usage.get("candidatesTokenCount")?.asInt ?: 0
                        thoughtTokens += usage.get("thoughtsTokenCount")?.asInt ?: 0
                    }
                }
                response
            }.build()
        val api = GeminiApi(BuildConfig.GEMINI_API_KEY, BuildConfig.GEMINI_MODEL, client)
        val cases = listOf(
            "미사호수공원 안에서만 3km 걷고 싶어. 공원까지 이동하는 거리는 제외해." to "",
            "광교호수 한바퀴 산책 코스" to "",
            "같은 곳에서 3km로 바꿔줘" to "사용자: 탄천 왕복 2km 산책 코스."
        )
        try {
            cases.forEachIndexed { index, (message, history) ->
                val raw = api.generateRouteDecision(AiPromptTemplates.buildRouteDecisionPrompt(
                    userMessage = message, recentConversation = history, hasCurrentLocation = false,
                    airSummary = "관측 자료 없음", weatherSummary = "관측 자료 없음", trailSummary = "검색 도구 실행 전"
                ))
                println("case=${index + 1}, response=$raw")
                val root = JsonParser.parseString(raw).asJsonObject
                assertEquals("Unexpected schema fields", setOf("intent", "needs_clarification", "clarifying_question",
                    "route_request_text", "place_queries", "distance_meters", "duration_minutes", "activity",
                    "route_shape", "use_current_location"), root.keySet())
                val decision = checkNotNull(AiRouteModelDecisionParser.parse(raw))
                assertEquals(AiRouteModelIntent.Route, decision.intent)
                assertFalse(decision.needsClarification)
                assertFalse(decision.useCurrentLocation)
                assertNull(decision.durationMinutes)
                when (index) {
                    0 -> {
                        assertEquals(listOf("미사호수공원"), decision.placeQueries)
                        assertEquals(3_000, decision.distanceMeters)
                        assertEquals(AiRouteShapeHint.Unknown, decision.routeShape)
                        assertTrue(decision.routeRequestText.contains("공원"))
                        assertTrue(decision.routeRequestText.contains("제외") || decision.routeRequestText.contains("안에서만") ||
                            decision.routeRequestText.contains("구간만") || decision.routeRequestText.contains("내에서"))
                    }
                    1 -> {
                        assertEquals(listOf("광교호수"), decision.placeQueries)
                        assertNull(decision.distanceMeters)
                        assertEquals(AiRouteShapeHint.LakeLoop, decision.routeShape)
                    }
                    2 -> {
                        assertEquals(listOf("탄천"), decision.placeQueries)
                        assertEquals(3_000, decision.distanceMeters)
                        assertEquals(AiRouteShapeHint.RiverOutAndBack, decision.routeShape)
                    }
                }
                println("case=${index + 1}, status=PASS")
            }
        } finally {
            println("probe_model=${BuildConfig.GEMINI_MODEL}, calls=$calls, prompt_tokens=$promptTokens, output_tokens=$outputTokens, thought_tokens=$thoughtTokens")
        }
    }
}
