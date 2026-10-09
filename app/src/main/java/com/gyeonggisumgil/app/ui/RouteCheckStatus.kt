package com.gyeonggisumgil.app.ui

/** Geometry status is separate from experimental scope and unobserved current access. */
internal fun routeCheckHeadline(status: String): String = when (status) {
    "PASS" -> "선형 조건 검사 통과"
    "FAIL" -> "선형 조건 검사 실패"
    "INCOMPLETE" -> "선형 조건 판정 보류"
    else -> "선형 조건 평가 못함"
}
