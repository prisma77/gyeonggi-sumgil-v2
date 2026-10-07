package com.gyeonggisumgil.review

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import com.kakao.vectormap.KakaoMap
import com.kakao.vectormap.KakaoMapReadyCallback
import com.kakao.vectormap.LatLng
import com.kakao.vectormap.MapLifeCycleCallback
import com.kakao.vectormap.MapAuthException
import com.kakao.vectormap.MapView
import com.kakao.vectormap.camera.CameraUpdateFactory
import com.kakao.vectormap.label.LabelOptions
import com.kakao.vectormap.label.LabelStyle
import com.kakao.vectormap.label.LabelStyles
import com.kakao.vectormap.route.RouteLineOptions
import com.kakao.vectormap.route.RouteLineSegment
import com.kakao.vectormap.route.RouteLineStyle
import com.kakao.vectormap.route.RouteLineStyles
import com.kakao.vectormap.route.RouteLineStylesSet
import org.json.JSONArray
import org.json.JSONObject

/** Draws supplied coordinates only; each API step remains a separate line. */
class ReviewMap(context: Context) {
    val view = MapView(context)
    private var map: KakaoMap? = null
    private var started = false
    private var result: JSONObject? = null

    private fun position(point: JSONArray): LatLng {
        require(point.length() == 2)
        val longitude = point.getDouble(0)
        val latitude = point.getDouble(1)
        require(longitude.isFinite() && latitude.isFinite() && longitude in -180.0..180.0 && latitude in -90.0..90.0)
        return LatLng.from(latitude, longitude)
    }

    fun start(sourceStart: JSONArray, ready: () -> Unit, error: (Int?) -> Unit) {
        if (started) return
        started = true
        view.start(object : MapLifeCycleCallback() {
            override fun onMapDestroy() { map = null }
            override fun onMapError(exception: Exception) {
                map = null
                error((exception as? MapAuthException)?.errorCode)
            }
        }, object : KakaoMapReadyCallback() {
            override fun getPosition(): LatLng = this@ReviewMap.position(sourceStart)
            override fun getZoomLevel() = 16
            override fun onMapReady(kakaoMap: KakaoMap) {
                map = kakaoMap
                result?.let { draw(it) }
                ready()
            }
        })
        view.resume()
    }

    fun clear() {
        result = null
        map?.routeLineManager?.layer?.removeAll()
        map?.labelManager?.layer?.removeAll()
    }

    fun center(sourceStart: JSONArray) {
        map?.moveCamera(CameraUpdateFactory.newCenterPosition(position(sourceStart), 16))
    }

    fun draw(response: JSONObject) {
        clear()
        result = response
        val kakaoMap = map ?: return
        val routeLayer = requireNotNull(kakaoMap.routeLineManager).layer
        val labelLayer = requireNotNull(requireNotNull(kakaoMap.labelManager).layer)
        val failed = response.getJSONObject("inspection").optJSONArray("failures")?.length() ?: 0
        val styles = RouteLineStylesSet.from("api-response",
            RouteLineStyles.from(RouteLineStyle.from(8f, if (failed > 0) Color.rgb(190, 58, 40) else Color.rgb(25, 92, 202))))
        val paths = response.getJSONArray("paths")
        val fitPoints = mutableListOf<LatLng>()
        for (index in 0 until paths.length()) {
            val path = paths.getJSONArray(index)
            val points = (0 until path.length()).map { position(path.getJSONArray(it)) }
            require(points.size >= 2)
            fitPoints.addAll(points)
            val segment = RouteLineSegment.from(points).setStyles(styles.getStyles(0))
            routeLayer.addRouteLine(RouteLineOptions.from(segment).setStylesSet(styles))
        }
        val targets = listOf(response.getJSONArray("start")) +
            response.getJSONArray("via").let { via -> (0 until via.length()).map { via.getJSONArray(it) } }
        targets.forEachIndexed { index, target ->
            val point = position(target)
            fitPoints.add(point)
            val marker = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(marker)
            val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE }
            canvas.drawCircle(32f, 32f, 29f, paint)
            paint.color = Color.rgb(27, 75, 73)
            canvas.drawCircle(32f, 32f, 25f, paint)
            paint.color = Color.WHITE
            paint.textSize = 28f
            paint.textAlign = Paint.Align.CENTER
            canvas.drawText(if (index == 0) "S" else "$index", 32f, 42f, paint)
            val markerStyle = LabelStyles.from(LabelStyle.from(marker))
            labelLayer.addLabel(LabelOptions.from(point).setStyles(markerStyle))
        }
        if (fitPoints.isNotEmpty()) {
            kakaoMap.moveCamera(CameraUpdateFactory.fitMapPoints(fitPoints.toTypedArray(), 70, 18))
        }
    }

    fun resume() { if (started) view.resume() }
    fun pause() { if (started) view.pause() }
    fun finish() { result = null; if (started) view.finish(); map = null }
}
