package com.gyeonggisumgil.app.data.places

import com.gyeonggisumgil.app.domain.model.GeoPoint
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** Temporary loopback transport. Provider credentials remain on the PC. */
class LocalPlaceSearchGateway : PlaceSearchGateway {
    override fun search(query: String, location: SearchLocation?): PlaceSearchResult {
        require(query.trim().length <= 100)
        val origin = searchLocationFor(query, location)
        val body = JSONObject().put("query", query.trim()).put("location", origin?.let {
            JSONObject().put("x", it.point.longitude).put("y", it.point.latitude)
                .put("accuracy_m", it.accuracyMeters.toDouble()).put("age_ms", it.ageMillis)
        } ?: JSONObject.NULL)
        val connection = URL("http://127.0.0.1:8769/places").openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 5000
            connection.readTimeout = 35_000
            connection.useCaches = false
            connection.instanceFollowRedirects = false
            connection.doOutput = true
            connection.setRequestProperty("X-Review-Client", "android-route-review")
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            check(connection.responseCode == 200) { "장소 검색 서버 HTTP ${connection.responseCode}" }
            val bytes = connection.inputStream.use { input ->
                val output = java.io.ByteArrayOutputStream()
                val buffer = ByteArray(4096)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    check(output.size() + count <= 200_000)
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            }
            val response = JSONObject(bytes.toString(Charsets.UTF_8))
            check(response.getInt("route_calls_sent") == 0 && response.getString("recommendation_quality") == "NOT_ACCEPTED")
            val list = response.getJSONArray("candidates")
            val candidates = (0 until list.length()).map { index ->
                val item = list.getJSONObject(index)
                PlaceCandidate(item.getString("id"), item.getString("name"), item.getString("address"),
                    item.getString("category"), GeoPoint(item.getDouble("y"), item.getDouble("x")),
                    if (item.isNull("distance_m")) null else item.getDouble("distance_m"))
            }
            return PlaceSearchResult(candidates, response.getBoolean("location_used"),
                response.getBoolean("truncated"), response.getString("requested_at"))
        } finally { connection.disconnect() }
    }
}
