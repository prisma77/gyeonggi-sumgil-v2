package com.gyeonggisumgil.app.data.routevalidation

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.MotionEvent
import android.widget.FrameLayout
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
    private val mapView = MapView(context)
    val view = object : FrameLayout(context) {
        init {
            addView(mapView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        }

        override fun dispatchTouchEvent(event: MotionEvent): Boolean {
            // Keep map gestures ahead of the surrounding Compose verticalScroll.
            if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                parent?.requestDisallowInterceptTouchEvent(true)
            }
            val handled = super.dispatchTouchEvent(event)
            if (!handled || event.actionMasked == MotionEvent.ACTION_UP || event.actionMasked == MotionEvent.ACTION_CANCEL) {
                parent?.requestDisallowInterceptTouchEvent(false)
            }
            return handled
        }

        override fun onDetachedFromWindow() {
            parent?.requestDisallowInterceptTouchEvent(false)
            super.onDetachedFromWindow()
        }
    }
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
        mapView.start(object : MapLifeCycleCallback() {
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
        mapView.resume()
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
        // The SDK reuses registered style IDs even after the layer's lines are removed.
        val styleId = if (failed > 0) "api-response-failed" else "api-response-unapproved"
        val styles = RouteLineStylesSet.from(styleId,
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
        val river = response.optString("shape") == "river_out_and_back"
        val turnIndex = response.optJSONObject("river_candidate")?.optInt("turnpoint_via_index", targets.lastIndex - 1)
            ?.plus(1) ?: targets.lastIndex
        // Revisited anchors retain their exact coordinates and share one label.
        val groupedTargets = targets.withIndex().groupBy { it.value.getDouble(0) to it.value.getDouble(1) }
        groupedTargets.values.forEach { group ->
            val target = group.first().value
            val point = position(target)
            fitPoints.add(point)
            val marker = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(marker)
            val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE }
            canvas.drawCircle(32f, 32f, 29f, paint)
            val turnpoint = river && group.any { it.index == turnIndex }
            paint.color = if (turnpoint) Color.rgb(165, 76, 19) else Color.rgb(27, 75, 73)
            canvas.drawCircle(32f, 32f, 25f, paint)
            paint.color = Color.WHITE
            val markerText = if (group.any { it.index == 0 }) "S" else if (turnpoint) "R"
                else group.joinToString("·") { it.index.toString() }
            paint.textSize = if (markerText.length > 1) 22f else 28f
            paint.textAlign = Paint.Align.CENTER
            canvas.drawText(markerText, 32f, 42f, paint)
            val markerStyle = LabelStyles.from(LabelStyle.from(marker).setAnchorPoint(0.5f, 0.5f))
            labelLayer.addLabel(LabelOptions.from(point).setStyles(markerStyle))
        }
        if (fitPoints.isNotEmpty()) {
            kakaoMap.moveCamera(CameraUpdateFactory.fitMapPoints(fitPoints.toTypedArray(), 70, 18))
        }
    }

    fun resume() { if (started) mapView.resume() }
    fun pause() { if (started) mapView.pause() }
    fun finish() { result = null; if (started) mapView.finish(); map = null }
}
