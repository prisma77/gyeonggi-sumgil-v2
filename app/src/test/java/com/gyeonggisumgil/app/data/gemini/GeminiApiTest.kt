package com.gyeonggisumgil.app.data.gemini

import com.google.gson.JsonParser
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

class GeminiApiTest {
    @Test
    fun routeRequestUsesHeaderAuthenticationAndStructuredOutput() {
        val client = OkHttpClient.Builder().addInterceptor { chain ->
            val request = chain.request()
            assertNull(request.url.queryParameter("key"))
            assertEquals("test-key", request.header("x-goog-api-key"))
            assertEquals("/v1beta/models/gemini-3.8-flash:generateContent", request.url.encodedPath)
            val buffer = Buffer()
            request.body!!.writeTo(buffer)
            val config = JsonParser.parseString(buffer.readUtf8()).asJsonObject.getAsJsonObject("generationConfig")
            assertEquals("application/json", config.get("responseMimeType").asString)
            assertEquals("low", config.getAsJsonObject("thinkingConfig").get("thinkingLevel").asString)
            assertFalse(config.has("temperature"))
            assertFalse(config.has("topP"))
            Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(200).message("OK")
                .body("""{"candidates":[{"content":{"parts":[{"text":"{}"}]}}]}"""
                    .toResponseBody("application/json".toMediaType())).build()
        }.build()
        assertEquals("{}", GeminiApi("test-key", "gemini-3.8-flash", client).generateRouteDecision("공원 한 바퀴"))
    }

    @Test
    fun errorBodyDoesNotExposeCredentials() {
        val client = OkHttpClient.Builder().addInterceptor { chain ->
            Response.Builder().request(chain.request()).protocol(Protocol.HTTP_1_1).code(403).message("Forbidden")
                .body("sensitive-provider-response".toResponseBody()).build()
        }.build()
        val error = runCatching { GeminiApi("test-key", "gemini-3.8-flash", client).generateWalkingAdvice("날씨") }
            .exceptionOrNull()!!
        assertEquals("Gemini request failed: HTTP 403", error.message)
    }
}
