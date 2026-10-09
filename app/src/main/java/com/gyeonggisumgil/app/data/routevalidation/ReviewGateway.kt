package com.gyeonggisumgil.app.data.routevalidation

import org.json.JSONObject
import org.json.JSONArray
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

/** Temporary developer gateway; REST credentials and provider schema remain on the PC. */
interface ReviewGateway {
    fun profiles(): JSONObject
    fun riverCandidates(id: String, durationMinutes: Int, walkingSpeedKmh: Double): JSONObject
    fun route(id: String, mode: String): JSONObject
    fun selectedNetwork(placeId: String, shape: String): JSONObject
    fun selectedCandidates(placeId: String, targetId: String, distanceMeters: Int?): JSONObject
}

class LocalReviewGateway : ReviewGateway {
    override fun selectedNetwork(placeId: String, shape: String) = request("/place-network",
        JSONObject().put("place_id", placeId).put("shape", shape))
    override fun selectedCandidates(placeId: String, targetId: String, distanceMeters: Int?) = request("/place-candidates",
        JSONObject().put("place_id", placeId).put("target_id", targetId).put("distance_m", distanceMeters ?: JSONObject.NULL))
    override fun profiles() = request("/profiles", null)
    override fun riverCandidates(id: String, durationMinutes: Int, walkingSpeedKmh: Double) =
        request("/river-candidates", JSONObject().put("id", id)
            .put("duration_minutes", durationMinutes).put("walking_speed_kmh", walkingSpeedKmh)
            .put("distance_range_m", JSONArray(listOf(2000, 3000))))
    override fun route(id: String, mode: String) = request("/route",
        JSONObject().put("id", id).put("mode", mode))

    private fun request(path: String, body: JSONObject?): JSONObject {
        val connection = URL("http://127.0.0.1:8769$path").openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 5000
            connection.readTimeout = if (path == "/place-network") 75000 else 35000
            connection.useCaches = false
            connection.instanceFollowRedirects = false
            connection.setRequestProperty("X-Review-Client", "android-route-review")
            connection.setRequestProperty("Accept", "application/json")
            if (body != null) {
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            check(connection.responseCode == 200) { "Local bridge HTTP ${connection.responseCode}" }
            val bytes = connection.inputStream.use { input ->
                val output = ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    check(output.size() + count <= 8_000_000) { "Response too large" }
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            }
            return JSONObject(bytes.toString(Charsets.UTF_8))
        } finally {
            connection.disconnect()
        }
    }
}
