package com.gyeonggisumgil.app.data.gemini

import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.gyeonggisumgil.app.BuildConfig
import com.gyeonggisumgil.app.data.ai.AiPromptTemplates
import com.gyeonggisumgil.app.domain.model.GeoPoint
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

class GeminiApi(
    private val apiKey: String,
    private val model: String = GEMINI_MODEL,
    private val client: OkHttpClient = defaultClient()
) {
    fun generateWalkingAdvice(prompt: String): String {
        return generateText(
            prompt = prompt,
            systemInstruction = AiPromptTemplates.SYSTEM_INSTRUCTION,
            maxOutputTokens = 1_200
        )
    }

    fun generateRouteDecision(prompt: String): String {
        return generateText(
            prompt = prompt,
            systemInstruction = AiPromptTemplates.ROUTE_DECISION_SYSTEM_INSTRUCTION,
            maxOutputTokens = 900,
            jsonResponse = true
        )
    }

    fun generateGroundedRouteDecision(
        prompt: String,
        locationBias: GeoPoint?
    ): String {
        return generateText(
            prompt = prompt,
            systemInstruction = AiPromptTemplates.ROUTE_DECISION_SYSTEM_INSTRUCTION +
                "\n\n" +
                MAPS_GROUNDED_ROUTE_DECISION_RULES,
            maxOutputTokens = 1_000,
            enableGoogleMapsGrounding = true,
            mapsGroundingLocation = locationBias
        )
    }

    private fun generateText(
        prompt: String,
        systemInstruction: String,
        maxOutputTokens: Int,
        jsonResponse: Boolean = false,
        enableGoogleMapsGrounding: Boolean = false,
        mapsGroundingLocation: GeoPoint? = null
    ): String {
        require(apiKey.isNotBlank()) { "GEMINI_API_KEY is blank." }
        require(prompt.isNotBlank()) { "prompt is blank." }

        val bodyJson = JsonObject().apply {
            add(
                "systemInstruction",
                JsonObject().apply {
                    add(
                        "parts",
                        JsonArray().apply {
                            add(
                                JsonObject().apply {
                                    addProperty(
                                        "text",
                                        systemInstruction
                                    )
                                }
                            )
                        }
                    )
                }
            )
            add(
                "contents",
                JsonArray().apply {
                    add(
                        JsonObject().apply {
                            addProperty("role", "user")
                            add(
                                "parts",
                                JsonArray().apply {
                                    add(JsonObject().apply { addProperty("text", prompt) })
                                }
                            )
                        }
                    )
                }
            )
            add(
                "generationConfig",
                JsonObject().apply {
                    addProperty("maxOutputTokens", maxOutputTokens)
                    add("thinkingConfig", JsonObject().apply { addProperty("thinkingLevel", "low") })
                    if (jsonResponse) addProperty("responseMimeType", "application/json")
                }
            )
            if (enableGoogleMapsGrounding) {
                addGoogleMapsGrounding(mapsGroundingLocation)
            }
        }.toString()

        val request = Request.Builder()
            .url("https://generativelanguage.googleapis.com/v1beta/models/$model:generateContent")
            .addHeader("x-goog-api-key", apiKey)
            .addHeader("Accept", "application/json")
            .post(bodyJson.toRequestBody(JSON_MEDIA_TYPE))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                error("Gemini request failed: HTTP ${response.code}")
            }

            val root = JsonParser.parseString(body).asJsonObject
            val candidates = root.getAsJsonArray("candidates") ?: return ""
            return candidates
                .firstOrNull()
                ?.asJsonObject
                ?.getAsJsonObject("content")
                ?.getAsJsonArray("parts")
                ?.mapNotNull { part ->
                    part.asJsonObject.get("text")?.asString
                }
                ?.joinToString("\n")
                .orEmpty()
        }
    }

    companion object {
        val GEMINI_MODEL: String = BuildConfig.GEMINI_MODEL
        private const val MAPS_GROUNDED_ROUTE_DECISION_RULES = """
            Google Maps grounding is enabled for this route classification request.
            Use it only to identify real-world places and their most useful search names.
            Keep the response as a single JSON object matching the requested schema.
            For lakes, rivers, streams, parks, and waterfront paths, prefer the actual park,
            lake, trail, or riverside name over nearby stations, parking lots, stores, or cafes.
            Do not use a parking lot, station, shop, apartment, or random nearby POI as the
            main place unless the user explicitly requested that exact POI.
            If the user asks for a lap around a lake or park, set route_shape to "lake_loop"
            or "loop" and include the exact place name in place_queries.
            If the user asks for a riverside or stream course, set route_shape to
            "river_out_and_back" and include the exact river/stream/park name in place_queries.
            Include 2 to 4 place_queries when useful: exact grounded place title first,
            then a broader local variant with city/province. Do not invent coordinates.
        """
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()

        private fun defaultClient(): OkHttpClient {
            return OkHttpClient.Builder()
                .retryOnConnectionFailure(false)
                .connectTimeout(5, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .callTimeout(25, TimeUnit.SECONDS)
                .build()
        }
    }
}

private fun JsonObject.addGoogleMapsGrounding(locationBias: GeoPoint?) {
    add(
        "tools",
        JsonArray().apply {
            add(
                JsonObject().apply {
                    add("googleMaps", JsonObject())
                }
            )
        }
    )
    if (locationBias == null) return

    add(
        "toolConfig",
        JsonObject().apply {
            add(
                "retrievalConfig",
                JsonObject().apply {
                    add(
                        "latLng",
                        JsonObject().apply {
                            addProperty("latitude", locationBias.latitude)
                            addProperty("longitude", locationBias.longitude)
                        }
                    )
                }
            )
        }
    )
}
