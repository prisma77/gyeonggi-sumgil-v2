package com.gyeonggisumgil.review

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import com.kakao.vectormap.KakaoMapSdk
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors
import kotlin.math.ceil

class MainActivity : Activity() {
    private val gateway: ReviewGateway = LocalReviewGateway()
    private val worker = Executors.newSingleThreadExecutor()
    private lateinit var reviewMap: ReviewMap
    private lateinit var profilePicker: Spinner
    private lateinit var modePicker: Spinner
    private lateinit var action: Button
    private lateinit var details: TextView
    private lateinit var mapStatus: TextView
    private var profiles = emptyList<JSONObject>()
    private val modes = listOf("SHORTEST", "BROAD_FIRST", "ACCESSIBLE")
    private var busy = false
    private var mapReady = false
    private var disposed = false

    private fun dp(value: Int) = (resources.displayMetrics.density * value).toInt()
    private fun text(value: String, size: Float = 14f) = TextView(this).apply {
        text = value; textSize = size; setTextColor(Color.rgb(30, 48, 48))
        setPadding(dp(12), dp(6), dp(12), dp(6))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.rgb(27, 75, 73)
        reviewMap = ReviewMap(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(247, 249, 247))
        }
        root.addView(text("숨길 · 도보 경로 검증", 21f))
        root.addView(text("추천 승인 전 시험 화면 · 현재 통행 여부 미확인"))
        profilePicker = Spinner(this)
        root.addView(profilePicker)
        modePicker = Spinner(this).apply {
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item,
                listOf("최단 거리 · SHORTEST", "큰길 우선 · BROAD_FIRST", "편안한 길 · ACCESSIBLE"))
        }
        root.addView(modePicker)
        action = Button(this).apply { text = "이 시험 입력으로 실제 경로 조회 (1회)"; isEnabled = false }
        root.addView(action)
        mapStatus = text("지도 준비 전 · 로컬 서버 연결 중")
        root.addView(mapStatus)
        root.addView(reviewMap.view, LinearLayout.LayoutParams(-1, 0, 1f))
        root.addView(text("S: 동일 출발·도착 / 1–5: 요청 경유점 / 선: API 반환 구간", 12f))
        details = text("PC 서버 시작 및 adb reverse 연결이 필요합니다.")
        root.addView(ScrollView(this).apply { addView(details) }, LinearLayout.LayoutParams(-1, dp(185)))
        setContentView(root)

        profilePicker.onItemSelectedListener = selection { selectedChanged() }
        modePicker.onItemSelectedListener = selection { selectedChanged() }
        action.setOnClickListener { queryRoute() }
        loadProfiles()
    }

    private fun selection(callback: () -> Unit) = object : AdapterView.OnItemSelectedListener {
        override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) = callback()
        override fun onNothingSelected(parent: AdapterView<*>?) = callback()
    }

    private fun selected() = profiles.getOrNull(profilePicker.selectedItemPosition - 1)
    private fun updateControls() {
        action.isEnabled = !busy && mapReady && selected() != null
        profilePicker.isEnabled = !busy
        modePicker.isEnabled = !busy
    }

    private fun selectedChanged() {
        reviewMap.clear()
        val profile = selected()
        if (profile == null) {
            details.text = "시험 입력을 직접 선택하세요. 자동 경로 조회는 하지 않습니다."
        } else {
            reviewMap.center(profile.getJSONArray("start"))
            details.text = sourceText(profile.getJSONObject("source")) +
                "\n${profile.getString("name")}\n경유점 5개 · 동일 출발·도착 · 시험 입력만 검토 완료" +
                "\n현장 통행·호수 한 바퀴·하천 전체 품질은 미승인." +
                if (!profile.isNull("input_change")) "\n한 점을 바꾼 비교 입력입니다. 원래 요청의 자동 대체가 아닙니다." else ""
        }
        updateControls()
    }

    private fun sourceText(source: JSONObject) =
        "입력: ${source.optString("attribution")} · ${source.optString("license")}" +
            "\n수집: ${source.optString("retrieved_at")} (현장 관측 시각 아님)" +
            "\n출처: ${source.optString("url")}\n이용 조건: ${source.optString("license_url")}"

    private fun loadProfiles() {
        busy = true; updateControls()
        worker.execute {
            val outcome = runCatching { gateway.profiles() }
            runOnUiThread {
                if (disposed) return@runOnUiThread
                busy = false
                outcome.onSuccess { response ->
                    val list = response.getJSONArray("profiles")
                    profiles = (0 until list.length()).map { list.getJSONObject(it) }
                    profilePicker.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
                        listOf("시험 입력을 선택하세요") + profiles.map { it.getString("label") })
                    details.text = "서버 연결 완료 · API 사용 ${response.getInt("calls_sent")}/${response.getInt("call_limit")}. 입력을 선택하세요."
                    if (BuildConfig.KAKAO_NATIVE_APP_KEY.isBlank()) {
                        mapStatus.text = "지도 네이티브 키가 없습니다. 경로 조회를 중단했습니다."
                    } else {
                        KakaoMapSdk.init(this, BuildConfig.KAKAO_NATIVE_APP_KEY)
                        reviewMap.start(profiles.first().getJSONArray("start"), ready = {
                            runOnUiThread { if (!disposed) { mapReady = true; mapStatus.text = "카카오 지도 준비 완료"; updateControls() } }
                        }, error = { code ->
                            runOnUiThread { if (!disposed) {
                                mapReady = false
                                mapStatus.text = "지도 연결 실패 (${code ?: "분류 불가"}) · 네트워크/활성화/패키지·키 해시 확인 필요"
                                updateControls()
                            } }
                        })
                    }
                }.onFailure {
                    details.text = "로컬 검증 서버에 연결하지 못했습니다. PC 서버와 USB 연결을 확인한 뒤 앱을 다시 여세요. 자동 재시도 없음."
                    mapStatus.text = "서버 연결 실패 · 경로 미조회"
                }
                updateControls()
            }
        }
    }

    private fun queryRoute() {
        val profile = selected() ?: return
        if (busy || !mapReady) return
        val id = profile.getString("id")
        val mode = modes[modePicker.selectedItemPosition]
        reviewMap.clear()
        busy = true; updateControls()
        details.text = "선택한 시험 입력으로 1회 조회 중…\n자동 재시도 없음 · 다른 장소로 대체하지 않음"
        worker.execute {
            val outcome = runCatching { gateway.route(id, mode) }
            runOnUiThread {
                if (disposed) return@runOnUiThread
                busy = false
                outcome.onSuccess { response ->
                    runCatching {
                        check(response.getString("id") == id && response.getString("mode") == mode)
                        check(response.getString("recommendation_quality") == "NOT_ACCEPTED")
                        details.text = describe(response)
                        reviewMap.draw(response)
                    }.onFailure {
                        reviewMap.clear()
                        details.text = "응답 구조 또는 지도 표시를 확인하지 못했습니다. 추천 미승인. 자동 재시도 없음."
                    }
                }.onFailure {
                    reviewMap.clear()
                    details.text = "조회 실패 · 서버 호출 한도 또는 네트워크 확인 필요. 이전 경로는 지웠습니다. 자동 재시도 없음."
                }
                updateControls()
            }
        }
    }

    private fun codes(array: JSONArray?): String = if (array == null || array.length() == 0) "없음" else
        (0 until array.length()).joinToString("\n") { array.getString(it) }

    private fun describe(response: JSONObject): String {
        val result = response.getJSONObject("inspection")
        val paths = response.getJSONArray("paths")
        val distance = result.optDouble("distance_m")
        val time = result.optDouble("time_s")
        return "추천 미승인 · HTTP ${response.getInt("http_status")} / ${result.optString("api_status")}" +
            (if (distance.isFinite() && time.isFinite()) "\nAPI 거리 ${distance.toInt()}m · 예상 ${ceil(time / 60).toInt()}분 (${time.toInt()}초)" else "\n유효한 거리·시간 없음") +
            "\n표시 구간 ${paths.length()}개 · 조회 ${response.getInt("calls_sent")}/${response.getInt("call_limit")}" +
            "\n경유점 차이(m): ${result.optJSONArray("waypoint_min_distance_m") ?: "평가 못함"}" +
            "\n순서: ${result.optString("waypoint_order_check", "평가 못함")}" +
            "\n실패: ${codes(result.optJSONArray("failures"))}" +
            "\n추가 검토: ${codes(result.optJSONArray("unresolved"))}" +
            "\n현재 통행·출입 제한 미확인. ACCESSIBLE은 무장애 보장이 아닙니다." +
            "\n경로: 카카오 도보 API · 조회 ${response.getString("requested_at")}" +
            "\n실제 요금·쿼터는 콘솔 확인 필요.\n" + sourceText(response.getJSONObject("source")) +
            response.optJSONObject("water_source")?.takeIf { it.length() > 0 }?.let {
                "\n수역 경계 자료:\n${sourceText(it)}"
            }.orEmpty()
    }

    override fun onResume() { super.onResume(); if (::reviewMap.isInitialized) reviewMap.resume() }
    override fun onPause() { if (::reviewMap.isInitialized) reviewMap.pause(); super.onPause() }
    override fun onDestroy() {
        disposed = true; profiles = emptyList(); worker.shutdownNow(); reviewMap.finish(); super.onDestroy()
    }
}
