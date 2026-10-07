package com.gyeonggisumgil.review

import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

/** Temporary developer gateway; REST credentials and provider schema remain on the PC. */
interface ReviewGateway {
    fun profiles(): JSONObject
    fun route(id: String, mode: String): JSONObject
}

class LocalReviewGateway : ReviewGateway {
    override fun profiles() = request("/profiles", null)
    override fun route(id: String, mode: String) = request("/route",
        JSONObject().put("id", id).put("mode", mode))

    private fun request(path: String, body: JSONObject?): JSONObject {
        val connection = URL("http://127.0.0.1:8769$path").openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 5000
            connection.readTimeout = 35000
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
