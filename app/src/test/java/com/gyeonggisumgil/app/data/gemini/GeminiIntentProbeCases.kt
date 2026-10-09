package com.gyeonggisumgil.app.data.gemini

import com.gyeonggisumgil.app.data.ai.AiIntentProbeCase
import com.gyeonggisumgil.app.data.ai.AiIntentProbeCases
import com.gyeonggisumgil.app.data.ai.intentProbeFailures
import org.junit.Assert.assertTrue

internal typealias GeminiIntentProbeCase = AiIntentProbeCase

internal object GeminiIntentProbeCases {
    val expanded = AiIntentProbeCases.expanded
}

internal fun validateIntentProbe(case: GeminiIntentProbeCase, raw: String) {
    val failures = intentProbeFailures(case, raw)
    assertTrue(failures.joinToString("; "), failures.isEmpty())
}
