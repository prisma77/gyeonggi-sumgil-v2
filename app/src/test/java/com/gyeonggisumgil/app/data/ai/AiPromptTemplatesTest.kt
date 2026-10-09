package com.gyeonggisumgil.app.data.ai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AiPromptTemplatesTest {
    @Test
    fun routePromptKeepsModelFromInventingMapData() {
        val prompt = AiPromptTemplates.buildWalkingRoutePrompt(
            userRequest = "광교 산책 3km 추천",
            routeSummary = """
                - 기준 장소: 광교호수공원 원천호수 한바퀴
                - 실제 계산 거리: 3.1 km
                - 예상 시간: 약 46분
            """.trimIndent(),
            airSummary = "- PM10: 19 ug/m3\n- PM2.5: 15 ug/m3",
            weatherSummary = "- 하늘상태: 맑음\n- 기온: 21도",
            trailSummary = "- 광교호수공원 산책로"
        )

        assertTrue(prompt.contains("새 좌표·새 경유지·새 장소를 만들지 않는다"))
        assertTrue(prompt.contains("실제 계산 거리와 예상 시간을 반드시 그대로 언급"))
        assertTrue(prompt.contains("경유지를 억지로 정당화하지 않는다"))
        assertFalse(prompt.contains("Gemini"))
    }

    @Test
    fun advicePromptSeparatesWeatherQuestionFromRouteCreation() {
        val prompt = AiPromptTemplates.buildWalkingAdvicePrompt(
            userQuestion = "지금 밖에 나가도 돼?",
            airSummary = "- PM10: 30 ug/m3\n- PM2.5: 16 ug/m3",
            weatherSummary = "- 하늘상태: 흐림\n- 강수형태: 없음",
            trailSummary = "- 산책로 후보 없음",
            requestedDistanceText = "명시되지 않음"
        )

        assertTrue(prompt.contains("날씨나 대기질만 물으면 현재 상태와 주의점만 답하고 코스나 경유지를 만들지 않는다"))
        assertTrue(prompt.contains("지도 경로 생성은 앱의 별도 경로 엔진이 처리"))
    }

    @Test
    fun routeDecisionPromptKeepsPlaceParsingSimple() {
        val prompt = AiPromptTemplates.buildRouteDecisionPrompt(
            userMessage = "경기도의 아무 호수나 공원의 산책 코스 짜줘",
            recentConversation = "",
            hasCurrentLocation = true,
            airSummary = "- PM10: 29 ug/m3\n- PM2.5: 21 ug/m3",
            weatherSummary = "- 하늘상태: 맑음",
            trailSummary = "- 중대물빛공원"
        )

        assertTrue(prompt.contains("사용자가 말한 장소명이 있으면 place_queries에는 그 장소명만 넣는다"))
        assertFalse(prompt.contains("\"distance_meters\":2500"))
        assertTrue(prompt.contains("기본 거리나 시간을 만들지 않는다"))
        assertTrue(prompt.contains("현재 위치 주변 호수나 공원 산책 코스"))
        assertFalse(prompt.contains("미사IC 근처 한강따라"))
    }
}
