package com.gyeonggisumgil.app.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class RouteCheckStatusTest {
    @Test fun passDescribesGeometryOnly() {
        assertEquals("선형 조건 검사 통과", routeCheckHeadline("PASS"))
    }
    @Test fun failedAndHeldAreDifferent() {
        assertEquals("선형 조건 검사 실패", routeCheckHeadline("FAIL"))
        assertEquals("선형 조건 판정 보류", routeCheckHeadline("INCOMPLETE"))
    }
    @Test fun missingOrUnknownStatusIsNotSuccess() {
        assertEquals("선형 조건 평가 못함", routeCheckHeadline(""))
        assertEquals("선형 조건 평가 못함", routeCheckHeadline("unexpected"))
    }
}
