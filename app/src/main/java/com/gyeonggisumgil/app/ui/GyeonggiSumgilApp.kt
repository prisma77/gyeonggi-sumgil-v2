package com.gyeonggisumgil.app.ui

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.CancellationSignal
import android.os.Looper
import android.util.Log
import android.view.MotionEvent
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Divider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.TextButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.gyeonggisumgil.app.BuildConfig
import com.gyeonggisumgil.app.data.RouteRepository
import com.gyeonggisumgil.app.data.SampleRouteRepository
import com.gyeonggisumgil.app.data.airkorea.AirKoreaApi
import com.gyeonggisumgil.app.data.airkorea.AirKoreaCurrentAirQualityRepository
import com.gyeonggisumgil.app.data.airkorea.CurrentAirQualityResult
import com.gyeonggisumgil.app.data.ai.AiCourseShape
import com.gyeonggisumgil.app.data.ai.AiPromptTemplates
import com.gyeonggisumgil.app.data.ai.AiRouteActivity
import com.gyeonggisumgil.app.data.ai.AiRouteClarificationType
import com.gyeonggisumgil.app.data.ai.AiRouteConversationAction
import com.gyeonggisumgil.app.data.ai.AiRouteConversationPlanner
import com.gyeonggisumgil.app.data.ai.AiRouteModelDecisionParser
import com.gyeonggisumgil.app.data.ai.AiRouteShapeHint
import com.gyeonggisumgil.app.data.ai.AiRequestIntentClassifier
import com.gyeonggisumgil.app.data.ai.AiRouteQueryParser
import com.gyeonggisumgil.app.data.ai.AiWalkingCourse
import com.gyeonggisumgil.app.data.ai.AiWalkingCourseCatalog
import com.gyeonggisumgil.app.data.ai.AiWalkingCourseSelection
import com.gyeonggisumgil.app.data.ai.PendingAiRouteRequest
import com.gyeonggisumgil.app.data.gemini.GeminiApi
import com.gyeonggisumgil.app.data.tmap.TmapPedestrianRouteApi
import com.gyeonggisumgil.app.data.tmap.TmapPedestrianRouteRepository
import com.gyeonggisumgil.app.data.tmap.TmapPlace
import com.gyeonggisumgil.app.data.tmap.TmapPlaceResolver
import com.gyeonggisumgil.app.data.weather.KmaCurrentWeather
import com.gyeonggisumgil.app.data.weather.KmaWeatherApi
import com.gyeonggisumgil.app.data.walking.GyeonggiWalkingTrail
import com.gyeonggisumgil.app.data.walking.GyeonggiWalkingTrailRepository
import com.gyeonggisumgil.app.data.walking.WalkingTrailRecommendation
import com.gyeonggisumgil.app.domain.model.AirQualityGrade
import com.gyeonggisumgil.app.domain.model.AirQualityReading
import com.gyeonggisumgil.app.domain.model.AirQualityStation
import com.gyeonggisumgil.app.domain.model.GeoPoint
import com.gyeonggisumgil.app.domain.model.RouteCandidate
import com.naver.maps.geometry.LatLng
import com.naver.maps.geometry.LatLngBounds
import com.naver.maps.map.CameraUpdate
import com.naver.maps.map.MapView
import com.naver.maps.map.NaverMap
import com.naver.maps.map.overlay.Marker
import com.naver.maps.map.overlay.Overlay
import com.naver.maps.map.overlay.PathOverlay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.withContext
import java.net.SocketTimeoutException
import java.util.Locale
import kotlin.coroutines.resume

@Composable
fun GyeonggiSumgilApp() {
    var selectedTab by remember { mutableStateOf(AppTab.Home) }
    var showExitDialog by remember { mutableStateOf(false) }
    var walkingTrailMapFocus by remember { mutableStateOf<GyeonggiWalkingTrail?>(null) }
    val walkingTrailRepository = remember { GyeonggiWalkingTrailRepository() }
    val context = LocalContext.current
    val appCoroutineScope = rememberCoroutineScope()
    val airKoreaRepository = remember {
        if (BuildConfig.AIRKOREA_SERVICE_KEY.isBlank()) {
            null
        } else {
            val placeResolver = BuildConfig.TMAP_APP_KEY
                .takeIf { it.isNotBlank() }
                ?.let { TmapPlaceResolver(it) }
            AirKoreaCurrentAirQualityRepository(
                api = AirKoreaApi(BuildConfig.AIRKOREA_SERVICE_KEY),
                placeResolver = placeResolver
            )
        }
    }
    val weatherApi = remember {
        BuildConfig.KMA_SERVICE_KEY
            .takeIf { it.isNotBlank() }
            ?.let { KmaWeatherApi(it) }
    }
    var currentAirQuality by remember { mutableStateOf(CurrentAirQualityState.empty()) }
    var currentWeather by remember { mutableStateOf(CurrentWeatherState.empty()) }
    var currentUserLocation by remember { mutableStateOf<GeoPoint?>(null) }
    val walkingTrailRecommendations = remember(currentUserLocation, currentAirQuality.station, currentAirQuality.reading) {
        walkingTrailRepository.recommendNearbyTrails(
            currentLocation = currentUserLocation ?: currentAirQuality.station?.let { station ->
                GeoPoint(station.latitude, station.longitude)
            },
            airScore = currentAirQuality.reading?.airQualityScore()
        )
    }

    fun refreshCurrentAirQuality(forceCurrentLocation: Boolean = false) {
        val repository = airKoreaRepository
        if (repository == null) {
            Log.w(APP_LOG_TAG, "AirKorea repository is null. keyBlank=${BuildConfig.AIRKOREA_SERVICE_KEY.isBlank()}")
            currentAirQuality = CurrentAirQualityState.empty("AirKorea 인증키가 설정되지 않았습니다.")
            return
        }

        currentAirQuality = CurrentAirQualityState.empty("현재 위치 대기질을 불러오는 중입니다.")
        appCoroutineScope.launch {
            val cachedResult = if (!forceCurrentLocation) {
                runCatching {
                    withContext(Dispatchers.IO) {
                        val cachedLocation = context.findBestLastKnownLocation(maxAgeMillis = null)
                            ?: return@withContext null
                        Log.d(APP_LOG_TAG, "cached air location=${cachedLocation.latitude},${cachedLocation.longitude}")
                        withTimeout(AIR_QUALITY_REQUEST_TIMEOUT_MILLIS) {
                            repository.getCurrentAirQuality(cachedLocation)
                        }
                    }
                }.onFailure { throwable ->
                    Log.e(APP_LOG_TAG, "AirKorea cached air failed", throwable)
                }.getOrNull()
            } else {
                null
            }

            if (cachedResult != null) {
                currentAirQuality = cachedResult.toState()
            }

            var resolvedAirLocation: GeoPoint? = null
            var freshFailure: Throwable? = null
            val freshResult = runCatching {
                withContext(Dispatchers.IO) {
                    val freshLocation = runCatching {
                        withTimeout(
                            if (forceCurrentLocation) FAST_CURRENT_LOCATION_TIMEOUT_MILLIS
                            else CURRENT_LOCATION_TIMEOUT_MILLIS
                        ) {
                            context.findCurrentLocationPoint(preferFastProvider = forceCurrentLocation)
                        }
                    }.getOrNull()
                    val fallbackLocation = if (forceCurrentLocation) {
                        context.findBestLastKnownLocatedLocation(maxAgeMillis = LOCATION_CACHE_MAX_AGE_MILLIS)
                    } else {
                        context.findBestLastKnownLocatedLocation(maxAgeMillis = null)
                    }
                    val currentLocation: LocatedGeoPoint = freshLocation ?: fallbackLocation ?: return@withContext null
                    Log.d(
                        APP_LOG_TAG,
                        "current air location=${currentLocation.point.latitude},${currentLocation.point.longitude}, provider=${currentLocation.provider}, accuracy=${currentLocation.accuracyMeters}, ageMs=${currentLocation.ageMillis}"
                    )
                    if (!currentLocation.isReliableForAirQuality()) {
                        error("현재 위치 정확도가 낮습니다. provider=${currentLocation.provider}, accuracy=${currentLocation.accuracyMeters}, ageMs=${currentLocation.ageMillis}")
                    }
                    resolvedAirLocation = currentLocation.point
                    withTimeout(AIR_QUALITY_REQUEST_TIMEOUT_MILLIS) {
                        repository.getCurrentAirQuality(currentLocation.point)
                    }
                }
            }.onFailure { throwable ->
                freshFailure = throwable
                Log.e(APP_LOG_TAG, "AirKorea current air failed", throwable)
            }.getOrNull()

            currentAirQuality = if (freshResult != null) {
                resolvedAirLocation?.let { currentUserLocation = it }
                Log.d(
                    APP_LOG_TAG,
                    "AirKorea matched station=${freshResult.station.name}, address=${freshResult.address}, count=${freshResult.measurementCount}, pm10=${freshResult.reading.pm10}, pm25=${freshResult.reading.pm25}"
                )
                freshResult.toState()
            } else {
                Log.w(APP_LOG_TAG, "AirKorea result is null")
                if (cachedResult != null) cachedResult.toState("최근 위치 기준 AirKorea 실시간 측정정보입니다.")
                else CurrentAirQualityState.empty(
                    freshFailure?.toAirQualityFailureMessage()
                        ?: "현재 위치와 매칭되는 경기·서울·인천 측정소를 찾지 못했습니다."
                )
            }
        }
    }

    fun refreshCurrentWeather(forceCurrentLocation: Boolean = false) {
        val api = weatherApi
        if (api == null) {
            currentWeather = CurrentWeatherState.empty("기상청 인증키가 설정되지 않았습니다.")
            return
        }

        currentWeather = CurrentWeatherState.empty("현재 위치 날씨를 불러오는 중입니다.")
        appCoroutineScope.launch {
            var resolvedWeatherLocation: GeoPoint? = null
            val result = runCatching {
                withContext(Dispatchers.IO) {
                    val freshLocation = runCatching {
                        withTimeout(
                            if (forceCurrentLocation) FAST_CURRENT_LOCATION_TIMEOUT_MILLIS
                            else CURRENT_LOCATION_TIMEOUT_MILLIS
                        ) {
                            context.findCurrentLocationPoint(preferFastProvider = forceCurrentLocation)
                        }
                    }.getOrNull()
                    val fallbackLocation = if (forceCurrentLocation) {
                        context.findBestLastKnownLocatedLocation(maxAgeMillis = LOCATION_CACHE_MAX_AGE_MILLIS)
                    } else {
                        context.findBestLastKnownLocatedLocation(maxAgeMillis = null)
                    }
                    val location = freshLocation ?: fallbackLocation ?: return@withContext null
                    resolvedWeatherLocation = location.point
                    withTimeout(WEATHER_REQUEST_TIMEOUT_MILLIS) {
                        api.getCurrentWeather(location.point)
                    }
                }
            }.onFailure { throwable ->
                Log.e(APP_LOG_TAG, "KMA current weather failed", throwable)
            }.getOrNull()

            resolvedWeatherLocation?.let { currentUserLocation = it }
            currentWeather = result?.toState()
                ?: CurrentWeatherState.empty("현재 위치 날씨를 불러오지 못했습니다.")
        }
    }

    val locationPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            refreshCurrentAirQuality(forceCurrentLocation = true)
            refreshCurrentWeather(forceCurrentLocation = true)
        } else {
            currentAirQuality = CurrentAirQualityState.empty("위치 권한이 없어 현재 위치 대기질을 표시할 수 없습니다.")
            currentWeather = CurrentWeatherState.empty("위치 권한이 없어 현재 위치 날씨를 표시할 수 없습니다.")
        }
    }

    LaunchedEffect(Unit) {
        if (context.hasFineLocationPermission()) {
            refreshCurrentAirQuality(forceCurrentLocation = true)
            refreshCurrentWeather(forceCurrentLocation = true)
        } else {
            currentAirQuality = CurrentAirQualityState.empty("위치 권한이 필요합니다.")
            currentWeather = CurrentWeatherState.empty("위치 권한이 필요합니다.")
            locationPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    BackHandler {
        if (selectedTab != AppTab.Home) {
            selectedTab = AppTab.Home
        } else {
            showExitDialog = true
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(AppColors.Background)
    ) {
        AppHeader(
            selectedTab = selectedTab,
            onTabSelected = { selectedTab = it }
        )

        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
        ) {
            when (selectedTab) {
                AppTab.Home -> HomeScreen(
                    currentAirQuality = currentAirQuality,
                    currentWeather = currentWeather,
                    walkingTrailRecommendations = walkingTrailRecommendations,
                    onWalkingTrailMapClick = { recommendation ->
                        walkingTrailMapFocus = recommendation.trail
                        selectedTab = AppTab.Route
                    },
                    onRefreshLocation = {
                        if (context.hasFineLocationPermission()) {
                            refreshCurrentAirQuality(forceCurrentLocation = true)
                        } else {
                            locationPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
                        }
                    },
                    onRefreshWeather = {
                        if (context.hasFineLocationPermission()) {
                            refreshCurrentWeather(forceCurrentLocation = true)
                        } else {
                            locationPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
                        }
                    },
                    onRouteClick = { selectedTab = AppTab.Route }
                )
                AppTab.Route -> VerifiedRouteScreen(
                    requestedPlaceLabel = walkingTrailMapFocus?.name,
                    onClearRequestedPlace = { walkingTrailMapFocus = null }
                )
                AppTab.Chat -> ChatScreen(
                    currentAirQuality = currentAirQuality,
                    currentWeather = currentWeather,
                    currentUserLocation = currentUserLocation,
                    walkingTrailRecommendations = walkingTrailRecommendations
                )
            }
        }
    }

    if (showExitDialog) {
        ExitConfirmDialog(
            onDismiss = { showExitDialog = false },
            onExit = {
                showExitDialog = false
                (context as? android.app.Activity)?.finish()
            }
        )
    }
}

@Composable
private fun ExitConfirmDialog(
    onDismiss: () -> Unit,
    onExit: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("앱을 종료할까요?") },
        text = { Text("경기 숨길을 종료합니다.") },
        confirmButton = {
            Button(
                onClick = onExit,
                colors = ButtonDefaults.buttonColors(containerColor = AppColors.Primary)
            ) {
                Text("앱 종료")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("취소", color = AppColors.Primary)
            }
        },
        containerColor = Color.White,
        titleContentColor = AppColors.Ink,
        textContentColor = AppColors.Muted
    )
}

@Composable
private fun AppHeader(
    selectedTab: AppTab,
    onTabSelected: (AppTab) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color.White)
            .padding(horizontal = 20.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        AppTab.values().forEach { tab ->
            TabButton(
                label = tab.label,
                selected = selectedTab == tab,
                onClick = { onTabSelected(tab) }
            )
        }
    }
}

@Composable
private fun HomeHero() {
    Column(
        modifier = Modifier.fillMaxWidth()
    ) {
        Text(
            text = "경기 숨길",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = AppColors.Ink
        )
        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = "경기도 공공데이터와 AI로 미세먼지를 피해 걷는 길",
            style = MaterialTheme.typography.bodyMedium,
            color = AppColors.Muted
        )
    }
}

@Composable
private fun HomeScreen(
    currentAirQuality: CurrentAirQualityState,
    currentWeather: CurrentWeatherState,
    walkingTrailRecommendations: List<WalkingTrailRecommendation>,
    onWalkingTrailMapClick: (WalkingTrailRecommendation) -> Unit,
    onRefreshLocation: () -> Unit,
    onRefreshWeather: () -> Unit,
    onRouteClick: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        HomeHero()

        AirQualitySummaryCard(
            state = currentAirQuality,
            onRefreshLocation = onRefreshLocation
        )

        WeatherSummaryCard(
            state = currentWeather,
            onRefreshWeather = onRefreshWeather
        )

        SectionTitle("경기 산책로 후보")
        Text(
            text = "산책로 위치 자료입니다. 실제 보행 경로와 현재 통행 상태는 검증 전입니다.",
            color = AppColors.Muted,
            style = MaterialTheme.typography.bodySmall
        )
        WalkingTrailRecommendationList(
            recommendations = walkingTrailRecommendations,
            onMapClick = onWalkingTrailMapClick
        )

        Button(
            onClick = onRouteClick,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = AppColors.Primary)
        ) {
            Text("산책 경로 직접 찾기")
        }
    }
}

@Composable
private fun RouteScreen(
    routeRepository: RouteRepository,
    walkingTrailMapFocus: GyeonggiWalkingTrail?
) {
    var start by remember { mutableStateOf("") }
    var waypoint by remember { mutableStateOf("") }
    var destination by remember { mutableStateOf("") }
    var selectedRouteId by remember { mutableStateOf<String?>(null) }
    var routes by remember { mutableStateOf<List<RouteCandidate>>(emptyList()) }
    var routeStatus by remember { mutableStateOf("출발지와 목적지를 입력하거나 지도에서 선택하세요.") }
    var isLoadingTmapRoute by remember { mutableStateOf(false) }
    var routeRequestId by remember { mutableStateOf(0) }
    var routeJob by remember { mutableStateOf<Job?>(null) }
    var pickedStart by remember { mutableStateOf<GeoPoint?>(null) }
    var pickedWaypoint by remember { mutableStateOf<GeoPoint?>(null) }
    var pickedDestination by remember { mutableStateOf<GeoPoint?>(null) }
    var mapPickTarget by remember { mutableStateOf<MapPickTarget?>(null) }
    var mapCenter by remember { mutableStateOf(DEFAULT_MAP_CENTER.toGeoPoint()) }
    var mapCameraTarget by remember { mutableStateOf<GeoPoint?>(null) }
    var mapCameraRequestId by remember { mutableStateOf(0) }
    var focusedTrail by remember { mutableStateOf<GyeonggiWalkingTrail?>(null) }
    val coroutineScope = rememberCoroutineScope()
    val routeScrollState = rememberScrollState()
    val context = LocalContext.current
    val focusManager = LocalFocusManager.current
    val tmapRouteRepository = remember {
        if (BuildConfig.TMAP_APP_KEY.isBlank()) {
            null
        } else {
            TmapPedestrianRouteRepository(TmapPedestrianRouteApi(BuildConfig.TMAP_APP_KEY))
        }
    }
    val tmapPlaceResolver = remember {
        if (BuildConfig.TMAP_APP_KEY.isBlank()) {
            null
        } else {
            TmapPlaceResolver(BuildConfig.TMAP_APP_KEY)
        }
    }
    fun moveMapCamera(point: GeoPoint) {
        mapCameraTarget = point
        mapCameraRequestId += 1
    }
    fun centerOnCurrentLocation() {
        val currentLocation = context.findBestLastKnownLocation()
        if (currentLocation == null) {
            routeStatus = "현재 위치를 확인할 수 없습니다. 휴대폰 위치 설정을 확인하세요."
        } else {
            moveMapCamera(currentLocation)
            routeStatus = if (mapPickTarget == null) {
                "현재 위치로 지도를 이동했습니다."
            } else {
                "현재 위치로 이동했습니다. 지도 중심을 선택하세요."
            }
        }
    }
    val locationPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            centerOnCurrentLocation()
        } else {
            routeStatus = "현재 위치 권한이 없어 지도를 이동할 수 없습니다."
        }
    }
    val selectedRoute = routes.firstOrNull { it.id == selectedRouteId } ?: routes.firstOrNull()

    LaunchedEffect(walkingTrailMapFocus?.id) {
        val trail = walkingTrailMapFocus ?: return@LaunchedEffect
        focusedTrail = trail
        start = ""
        waypoint = ""
        destination = ""
        pickedStart = null
        pickedWaypoint = null
        pickedDestination = null
        mapPickTarget = null
        selectedRouteId = null
        routes = emptyList()
        isLoadingTmapRoute = false
        routeStatus = "${trail.name} 중심 위치로 지도를 이동했습니다. 지도에서 출발·도착을 선택하세요."
        moveMapCamera(trail.center)
    }

    fun clearRouteState(message: String) {
        routeJob?.cancel()
        routeRequestId += 1
        selectedRouteId = null
        routes = emptyList()
        isLoadingTmapRoute = false
        routeStatus = message
    }

    fun scrollToRouteCards() {
        coroutineScope.launch {
            delay(250)
            routeScrollState.animateScrollTo(routeScrollState.maxValue)
        }
    }

    fun loadTmapRoutes(requestedStart: String, requestedWaypoint: String?, requestedDestination: String) {
        val trimmedStart = requestedStart.trim()
        val trimmedWaypoint = requestedWaypoint?.trim().orEmpty()
        val trimmedDestination = requestedDestination.trim()
        val hasWaypoint = trimmedWaypoint.isNotBlank()
        routeJob?.cancel()
        routeRequestId += 1
        val activeRequestId = routeRequestId

        start = trimmedStart
        waypoint = trimmedWaypoint
        destination = trimmedDestination
        focusedTrail = null
        mapPickTarget = null
        selectedRouteId = null
        routes = emptyList()

        if (trimmedStart.isBlank() || trimmedDestination.isBlank()) {
            isLoadingTmapRoute = false
            routeStatus = "출발지와 목적지를 모두 입력하세요."
            return
        }

        val repository = tmapRouteRepository
        if (repository == null) {
            routes = routeRepository.getRecommendedRoutes(trimmedStart, trimmedDestination)
            routeStatus = "Tmap appKey가 없어 샘플 경로를 표시합니다."
            return
        }

        routeJob = coroutineScope.launch {
            isLoadingTmapRoute = true
            routeStatus = "Tmap 보행자 경로를 불러오는 중입니다."
            runCatching {
                withContext(Dispatchers.IO) {
                    repository.getRecommendedRoutes(
                        start = trimmedStart,
                        waypoint = trimmedWaypoint.takeIf { hasWaypoint },
                        destination = trimmedDestination
                    )
                }
            }.onSuccess { tmapRoutes ->
                if (activeRequestId != routeRequestId) return@onSuccess

                val firstRoute = tmapRoutes.firstOrNull()
                if (tmapRoutes.isEmpty()) {
                    routeStatus = "장소 좌표를 찾지 못했습니다. 장소명 또는 도로명 주소를 더 구체적으로 입력하세요."
                } else if (!hasWaypoint && firstRoute != null && firstRoute.distanceMeters < MIN_ROUTE_DISTANCE_METERS) {
                    routeStatus = "출발지와 도착지가 100m보다 가깝습니다. 산책 경로를 보려면 더 먼 지점을 선택하세요."
                    routes = emptyList()
                    selectedRouteId = null
                } else {
                    routes = tmapRoutes
                    selectedRouteId = tmapRoutes.first().id
                    val selected = tmapRoutes.first()
                    routeStatus = "Tmap 도보 경로 반영: ${formatDistance(selected.distanceMeters)} · 약 ${selected.durationMinutes}분 · 좌표 ${selected.coordinates.size}개"
                    scrollToRouteCards()
                }
            }.onFailure { throwable ->
                if (activeRequestId != routeRequestId) return@onFailure

                routeStatus = "Tmap 경로 호출 실패: ${throwable.message ?: "오류 내용을 확인할 수 없습니다."}"
            }
            if (activeRequestId == routeRequestId) {
                isLoadingTmapRoute = false
            }
        }
    }

    fun loadTmapRoutes(requestedStart: String, requestedDestination: String) {
        loadTmapRoutes(requestedStart, waypoint, requestedDestination)
    }

    fun loadTmapRoutesFromMap(startPoint: GeoPoint, waypointPoint: GeoPoint?, destinationPoint: GeoPoint) {
        routeJob?.cancel()
        routeRequestId += 1
        val activeRequestId = routeRequestId
        focusedTrail = null
        mapPickTarget = null
        selectedRouteId = null
        routes = emptyList()
        val hasWaypoint = waypointPoint != null

        if (!hasWaypoint && startPoint.approximateDistanceTo(destinationPoint) < MIN_ROUTE_DISTANCE_METERS) {
            routeStatus = "출발지와 도착지가 100m보다 가깝습니다. 산책 경로를 보려면 더 먼 지점을 선택하세요."
            isLoadingTmapRoute = false
            return
        }

        val repository = tmapRouteRepository
        if (repository == null) {
            routeStatus = "Tmap appKey가 없어 지도 선택 경로를 계산할 수 없습니다."
            return
        }

        val startPlace = startPoint.toTmapPlace("지도 출발지")
        val waypointPlace = waypointPoint?.toTmapPlace("지도 경유지")
        val destinationPlace = destinationPoint.toTmapPlace("지도 목적지")
        routeJob = coroutineScope.launch {
            isLoadingTmapRoute = true
            routeStatus = if (waypointPoint == null) {
                "지도에서 선택한 두 지점의 도보 경로를 불러오는 중입니다."
            } else {
                "지도에서 선택한 경유 산책 경로를 불러오는 중입니다."
            }
            runCatching {
                withContext(Dispatchers.IO) {
                    repository.getRecommendedRoutes(startPlace, waypointPlace, destinationPlace)
                }
            }.onSuccess { tmapRoutes ->
                if (activeRequestId != routeRequestId) return@onSuccess

                val firstRoute = tmapRoutes.firstOrNull()
                if (tmapRoutes.isEmpty()) {
                    routeStatus = "선택한 지점 사이의 도보 경로를 찾지 못했습니다."
                } else if (!hasWaypoint && firstRoute != null && firstRoute.distanceMeters < MIN_ROUTE_DISTANCE_METERS) {
                    routeStatus = "출발지와 도착지가 100m보다 가깝습니다. 산책 경로를 보려면 더 먼 지점을 선택하세요."
                    routes = emptyList()
                    selectedRouteId = null
                } else {
                    routes = tmapRoutes
                    selectedRouteId = tmapRoutes.first().id
                    val selected = tmapRoutes.first()
                    routeStatus = "지도 선택 경로 반영: ${formatDistance(selected.distanceMeters)} · 약 ${selected.durationMinutes}분 · 좌표 ${selected.coordinates.size}개"
                    scrollToRouteCards()
                }
            }.onFailure { throwable ->
                if (activeRequestId != routeRequestId) return@onFailure

                routeStatus = "Tmap 경로 호출 실패: ${throwable.message ?: "오류 내용을 확인할 수 없습니다."}"
            }
            if (activeRequestId == routeRequestId) {
                isLoadingTmapRoute = false
            }
        }
    }

    fun clearRouteForManualInput() {
        focusedTrail = null
        pickedStart = null
        pickedWaypoint = null
        pickedDestination = null
        mapPickTarget = null
        clearRouteState("출발지와 목적지를 입력한 뒤 경로 찾기를 누르세요.")
    }

    fun resolvePickedAddress(target: MapPickTarget, point: GeoPoint) {
        val resolver = tmapPlaceResolver ?: return

        coroutineScope.launch {
            val address = runCatching {
                withContext(Dispatchers.IO) {
                    resolver.reverseGeocode(point)
                }
            }.getOrNull() ?: "지도에서 선택한 위치"

            when (target) {
                MapPickTarget.Start -> {
                    if (pickedStart == point) start = address
                }
                MapPickTarget.Waypoint -> {
                    if (pickedWaypoint == point) waypoint = address
                }
                MapPickTarget.Destination -> {
                    if (pickedDestination == point) destination = address
                }
            }
        }
    }

    fun selectMapCenter() {
        val point = mapCenter
        when (mapPickTarget) {
            MapPickTarget.Start -> {
                pickedStart = point
                start = "주소 확인 중..."
                selectedRouteId = null
                routes = emptyList()
                routeStatus = "경유지 또는 도착지를 지도 중심에 맞춘 뒤 선택하세요."
                resolvePickedAddress(MapPickTarget.Start, point)
            }
            MapPickTarget.Waypoint -> {
                pickedWaypoint = point
                waypoint = "주소 확인 중..."
                selectedRouteId = null
                routes = emptyList()
                mapPickTarget = MapPickTarget.Destination
                routeStatus = "도착지를 지도 중심에 맞춘 뒤 선택하세요."
                resolvePickedAddress(MapPickTarget.Waypoint, point)
            }
            MapPickTarget.Destination -> {
                pickedDestination = point
                destination = "주소 확인 중..."
                selectedRouteId = null
                routes = emptyList()
                mapPickTarget = null
                val selectedStart = pickedStart
                if (selectedStart == null && start.isBlank()) {
                    routeStatus = "출발지를 먼저 지도에서 선택하세요."
                    mapPickTarget = MapPickTarget.Start
                } else if (selectedStart != null) {
                    resolvePickedAddress(MapPickTarget.Destination, point)
                    loadTmapRoutesFromMap(selectedStart, pickedWaypoint, point)
                } else {
                    resolvePickedAddress(MapPickTarget.Destination, point)
                    routeStatus = "출발지를 확인한 뒤 경로 찾기를 누르세요."
                }
            }
            null -> Unit
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        MapPreviewCard(
            route = selectedRoute,
            interactive = true,
            isLoading = isLoadingTmapRoute,
            focusedTrail = focusedTrail,
            pickedStart = pickedStart,
            pickedWaypoint = pickedWaypoint,
            pickedDestination = pickedDestination,
            pickTarget = mapPickTarget,
            cameraTarget = mapCameraTarget,
            cameraRequestId = mapCameraRequestId,
            onMapCenterChanged = { center -> mapCenter = center }
        )

        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(routeScrollState),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            CardSurface(contentPadding = 14.dp) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        CompactRouteButton(
                            label = "출발",
                            selected = mapPickTarget == MapPickTarget.Start,
                            modifier = Modifier.weight(1f),
                            onClick = {
                                focusManager.clearFocus()
                                clearRouteState("출발지를 지도에서 선택하세요.")
                                pickedStart = null
                                pickedWaypoint = null
                                pickedDestination = null
                                start = ""
                                waypoint = ""
                                destination = ""
                                mapPickTarget = MapPickTarget.Start
                            }
                        )
                        CompactRouteButton(
                            label = "도착",
                            selected = mapPickTarget == MapPickTarget.Destination,
                            modifier = Modifier.weight(1f),
                            onClick = {
                                focusManager.clearFocus()
                                selectedRouteId = null
                                routes = emptyList()
                                if (pickedStart == null && start.isBlank()) {
                                    mapPickTarget = MapPickTarget.Start
                                    "출발지를 먼저 선택하거나 출발 선택을 누르세요."
                                } else {
                                    mapPickTarget = MapPickTarget.Destination
                                    "도착지를 지도에서 선택하세요."
                                }.also { routeStatus = it }
                            }
                        )
                        CompactRouteButton(
                            label = "선택",
                            selected = mapPickTarget != null,
                            selectedColor = AppColors.MapAction,
                            modifier = Modifier.weight(1f),
                            onClick = {
                                focusManager.clearFocus()
                                if (mapPickTarget != null) {
                                    selectMapCenter()
                                } else {
                                    routeStatus = "출발 또는 도착을 먼저 선택하세요."
                                }
                            }
                        )
                        CompactRouteButton(
                            label = "경유",
                            selected = mapPickTarget == MapPickTarget.Waypoint,
                            modifier = Modifier.weight(1f),
                            onClick = {
                                focusManager.clearFocus()
                                if (pickedStart == null && start.isBlank()) {
                                    mapPickTarget = MapPickTarget.Start
                                    routeStatus = "출발지를 먼저 입력하거나 지도에서 선택하세요."
                                } else {
                                    selectedRouteId = null
                                    routes = emptyList()
                                    mapPickTarget = MapPickTarget.Waypoint
                                    routeStatus = "경유지 또는 반환점을 지도 중심에 맞춘 뒤 선택하세요."
                                }
                            }
                        )
                        CompactRouteButton(
                            label = "현위치",
                            selected = false,
                            modifier = Modifier.weight(1f),
                            onClick = {
                                focusManager.clearFocus()
                                if (context.hasFineLocationPermission()) {
                                    centerOnCurrentLocation()
                                } else {
                                    locationPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
                                }
                            }
                        )
                    }
                    OutlinedTextField(
                        value = start,
                        onValueChange = {
                            start = it
                            clearRouteForManualInput()
                        },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("출발지") },
                        placeholder = { Text("장소명 또는 도로명 주소") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next)
                    )
                    OutlinedTextField(
                        value = waypoint,
                        onValueChange = {
                            waypoint = it
                            pickedWaypoint = null
                            clearRouteState("경유지 또는 반환점을 입력한 뒤 경로 찾기를 누르세요.")
                        },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("경유") },
                        placeholder = { Text("반환점 또는 들를 곳") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next)
                    )
                    OutlinedTextField(
                        value = destination,
                        onValueChange = {
                            destination = it
                            clearRouteForManualInput()
                        },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("도착지") },
                        placeholder = { Text("장소명 또는 도로명 주소") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                        keyboardActions = KeyboardActions(
                            onSearch = {
                                focusManager.clearFocus()
                                loadTmapRoutes(start, destination)
                            }
                        )
                    )
                    TabButton(
                        label = "도착=출발",
                        selected = destination.isNotBlank() && destination == start,
                        onClick = {
                            destination = start
                            pickedDestination = pickedStart
                            clearRouteState("반환점 또는 경유지를 입력한 뒤 경로 찾기를 누르세요.")
                        }
                    )
                    Text(
                        text = routeStatus,
                        color = AppColors.Muted,
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Button(
                        onClick = {
                            focusManager.clearFocus()
                            val mapStart = pickedStart
                            val mapWaypoint = pickedWaypoint
                            val mapDestination = pickedDestination
                            if (mapStart != null && mapDestination != null) {
                                loadTmapRoutesFromMap(mapStart, mapWaypoint, mapDestination)
                            } else {
                                loadTmapRoutes(start, waypoint, destination)
                            }
                        },
                        enabled = tmapRouteRepository != null && !isLoadingTmapRoute,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(44.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = AppColors.Primary),
                        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 6.dp)
                    ) {
                        Text(if (isLoadingTmapRoute) "불러오는 중" else "입력한 경로 찾기")
                    }
                }
            }

            routes.forEach { route ->
                RouteCard(
                    route = route,
                    highlighted = route.id == selectedRoute?.id,
                    onClick = { selectedRouteId = route.id },
                    modifier = Modifier
                        .fillMaxWidth(0.94f)
                        .align(Alignment.CenterHorizontally)
                )
            }
        }
    }
}

@Composable
private fun ChatScreen(
    currentAirQuality: CurrentAirQualityState,
    currentWeather: CurrentWeatherState,
    currentUserLocation: GeoPoint?,
    walkingTrailRecommendations: List<WalkingTrailRecommendation>
) {
    var message by remember { mutableStateOf("") }
    var aiAnswer by remember { mutableStateOf("현재 대기질과 날씨를 기준으로 질문해 주세요.") }
    var chatMessages by remember {
        mutableStateOf(
            listOf(
                AiChatMessage(
                    title = "경기 숨길 AI",
                    body = "현재 대기질과 날씨를 기준으로 질문해 주세요."
                )
            )
        )
    }
    var isLoading by remember { mutableStateOf(false) }
    var aiRoutes by remember { mutableStateOf<List<RouteCandidate>>(emptyList()) }
    var selectedAiRouteId by remember { mutableStateOf<String?>(null) }
    var aiRouteStatus by remember { mutableStateOf("대기질·날씨 상담은 유지합니다. 경로는 경로 탭에서 실제 API 응답을 검증합니다.") }
    var isLoadingAiRoute by remember { mutableStateOf(false) }
    var isMapGestureActive by remember { mutableStateOf(false) }
    var aiRequestedPlaceResolveFailed by remember { mutableStateOf(false) }
    var pendingAiRouteRequest by remember { mutableStateOf<PendingAiRouteRequest?>(null) }
    var selectedAiCourse by remember { mutableStateOf<AiWalkingCourseSelection?>(null) }
    val coroutineScope = rememberCoroutineScope()
    val context = LocalContext.current
    val chatScrollState = rememberScrollState()
    val focusedTrail = walkingTrailRecommendations.firstOrNull()?.trail
    val selectedAiRoute = aiRoutes.firstOrNull { it.id == selectedAiRouteId } ?: aiRoutes.firstOrNull()
    val courseCatalog = remember { AiWalkingCourseCatalog() }
    val aiFocusedTrail = selectedAiCourse
        ?.let { courseCatalog.matchingTrail(it.course) }
        ?: focusedTrail
    val geminiApi = remember {
        BuildConfig.GEMINI_API_KEY
            .takeIf { it.isNotBlank() }
            ?.let { GeminiApi(apiKey = it) }
    }
    val tmapRouteRepository = remember {
        if (BuildConfig.TMAP_APP_KEY.isBlank()) {
            null
        } else {
            TmapPedestrianRouteRepository(TmapPedestrianRouteApi(BuildConfig.TMAP_APP_KEY))
        }
    }
    val aiPlaceResolver = remember {
        BuildConfig.TMAP_APP_KEY
            .takeIf { it.isNotBlank() }
            ?.let { TmapPlaceResolver(it) }
    }

    fun addChatMessage(title: String, body: String) {
        chatMessages = chatMessages + AiChatMessage(title = title, body = body)
    }

    fun buildAiWalkingRoute(
        requestText: String = message,
        placeQueryOverride: String? = null,
        placeQueryCandidates: List<String> = emptyList(),
        targetDistanceOverride: Int? = null,
        forceCurrentLocationOnly: Boolean = false,
        routeShapeHint: AiRouteShapeHint = AiRouteShapeHint.Unknown
    ) {
        val repository = tmapRouteRepository
        if (repository == null) {
            aiRouteStatus = "Tmap appKey가 없어 산책 후보 경로를 만들 수 없습니다."
            addChatMessage("경기 숨길 AI", aiRouteStatus)
            return
        }

        val targetDistanceMeters = targetDistanceOverride ?: requestText.extractRequestedDistanceMeters()
        val routeSelectionText = listOf(
            requestText,
            placeQueryCandidates.joinToString(" "),
            routeShapeHint.toRouteSearchText()
        )
            .filter { it.isNotBlank() }
            .joinToString(" ")
        Log.d(
            APP_LOG_TAG,
            "AI route build request=$requestText, placeOverride=$placeQueryOverride, placeCandidates=$placeQueryCandidates, target=$targetDistanceMeters, forceCurrent=$forceCurrentLocationOnly, shape=$routeShapeHint"
        )

        coroutineScope.launch {
            isLoadingAiRoute = true
            aiRequestedPlaceResolveFailed = false
            aiRouteStatus = "현재 위치를 확인해 출발·도착점으로 잡는 중입니다."
            runCatching {
                withContext(Dispatchers.IO) {
                    val startPoint = resolveAiRouteStartPoint(
                        context = context,
                        currentUserLocation = currentUserLocation,
                        currentAirQuality = currentAirQuality,
                        focusedTrail = focusedTrail
                    )
                    val resolvedPlaceQueries = if (forceCurrentLocationOnly) {
                        emptyList()
                    } else {
                        (
                            placeQueryCandidates +
                                listOfNotNull(placeQueryOverride) +
                                listOfNotNull(AiRouteQueryParser.extractPlaceQuery(routeSelectionText))
                            )
                            .map { it.trim() }
                            .filter { it.isNotBlank() }
                            .distinct()
                    }
                    Log.d(APP_LOG_TAG, "AI route resolvedPlaceQueries=$resolvedPlaceQueries, routeSelectionText=$routeSelectionText")
                    val explicitCourseSelection = if (forceCurrentLocationOnly) {
                        null
                    } else {
                        courseCatalog.selectCourse(
                            query = routeSelectionText,
                            currentLocation = null,
                            nearbyRecommendations = emptyList()
                        )
                    }
                    Log.d(APP_LOG_TAG, "AI route explicitCourse=${explicitCourseSelection?.course?.id}, explicit=${explicitCourseSelection?.explicitPlaceRequested}")
                    val requestedPlaceQuery = if (explicitCourseSelection == null) {
                        resolvedPlaceQueries.firstOrNull()
                    } else {
                        null
                    }
                    val requestedPlaceResolution = if (requestedPlaceQuery != null) {
                        resolvedPlaceQueries.firstNotNullOfOrNull { placeQuery ->
                            runCatching {
                                aiPlaceResolver?.resolve(placeQuery)?.let { place -> placeQuery to place }
                            }.getOrNull()
                        }
                    } else {
                        null
                    }
                    val requestedPlace = requestedPlaceResolution?.second
                    Log.d(
                        APP_LOG_TAG,
                        "AI route requestedPlaceQuery=$requestedPlaceQuery, resolvedQuery=${requestedPlaceResolution?.first}, resolvedPlace=${requestedPlace?.name}, lat=${requestedPlace?.latitude}, lon=${requestedPlace?.longitude}"
                    )

                    if (requestedPlaceQuery != null && requestedPlace == null) {
                        return@withContext AiRouteBuildResult(
                            courseSelection = null,
                            requestedPlaceName = resolvedPlaceQueries.joinToString(", "),
                            requestedPlaceResolveFailed = true,
                            routes = emptyList()
                        )
                    }

                    val courseSelection = explicitCourseSelection ?: if (requestedPlace == null) {
                        courseCatalog.selectCourse(
                            query = routeSelectionText,
                            currentLocation = startPoint,
                            nearbyRecommendations = walkingTrailRecommendations
                        )
                    } else {
                        null
                    }
                    val routeStartPoint = requestedPlace?.toGeoPoint() ?: startPoint
                    Log.d(APP_LOG_TAG, "AI route finalCourse=${courseSelection?.course?.id}, start=${routeStartPoint.latitude},${routeStartPoint.longitude}")
                    val routes = if (courseSelection != null) {
                        buildCourseAwareRoutes(
                            repository = repository,
                            courseSelection = courseSelection,
                            currentLocation = routeStartPoint,
                            targetDistanceMeters = targetDistanceMeters,
                            requestText = routeSelectionText
                        )
                    } else {
                        buildDistanceAwareLoopRoutes(
                            repository = repository,
                            startPoint = routeStartPoint,
                            center = routeStartPoint,
                            targetDistanceMeters = targetDistanceMeters
                        )
                    }
                    AiRouteBuildResult(
                        courseSelection = courseSelection,
                        requestedPlaceName = requestedPlace?.name ?: requestedPlaceResolution?.first,
                        requestedPlaceResolveFailed = false,
                        routes = routes
                    )
                }
            }.onSuccess { result ->
                val courseSelection = result.courseSelection
                val requestedPlaceName = result.requestedPlaceName
                val routes = result.routes
                selectedAiCourse = courseSelection
                aiRequestedPlaceResolveFailed = result.requestedPlaceResolveFailed
                aiRouteStatus = courseSelection?.let { selection ->
                    val basis = if (selection.explicitPlaceRequested) "질문에서 찾은 장소" else "현재 위치 주변 후보"
                    "$basis: ${selection.course.name} 기준으로 참고용 산책 후보를 구성했습니다."
                } ?: requestedPlaceName?.let { placeName ->
                    "질문에서 찾은 장소: $placeName 기준으로 참고용 산책 후보를 구성했습니다."
                } ?: "현재 위치를 출발·도착점으로 참고용 산책 후보를 구성했습니다."
                aiRoutes = routes
                selectedAiRouteId = routes.firstOrNull()?.id
                val selected = routes.firstOrNull()
                aiRouteStatus = if (selected == null) {
                    if (result.requestedPlaceResolveFailed && requestedPlaceName != null) {
                        "질문에서 찾은 장소($requestedPlaceName)를 좌표로 찾지 못했습니다. 도로명에 건물번호나 가까운 지점을 함께 입력해 주세요."
                    } else {
                        "산책 후보 경로를 찾지 못했습니다. 산책 후보가 더 많은 지역에서 다시 시도해 보세요."
                    }
                } else if (selected.coordinates.size < 2) {
                    val courseText = courseSelection?.course?.name ?: selected.title
                    "추천 장소: $courseText · 예상 ${formatDistance(selected.distanceMeters)} · 정확한 경로선은 표시하지 않습니다."
                } else {
                    val targetText = targetDistanceMeters?.let { "목표 ${formatDistance(it)} · " }.orEmpty()
                    val courseText = courseSelection?.course?.name?.let { "$it · " }
                        ?: requestedPlaceName?.let { "$it · " }
                        ?: ""
                    "AI 산책 후보: $courseText${targetText}${formatDistance(selected.distanceMeters)} · 약 ${selected.durationMinutes}분"
                }
                if (selected == null) {
                    aiAnswer = aiRouteStatus
                    addChatMessage("경기 숨길 AI", aiRouteStatus)
                } else {
                    val fallbackAnswer = buildAiRouteAnswer(
                        courseSelection = courseSelection,
                        targetDistanceMeters = targetDistanceMeters,
                        selected = selected,
                        currentAirQuality = currentAirQuality
                    )
                    val api = geminiApi
                    val finalAnswer = if (api != null) {
                        runCatching {
                            withContext(Dispatchers.IO) {
                                api.generateWalkingAdvice(
                                    buildGeminiRoutePrompt(
                                        userRequest = requestText,
                                        currentAirQuality = currentAirQuality,
                                        currentWeather = currentWeather,
                                        walkingTrailRecommendations = walkingTrailRecommendations,
                                        courseSelection = courseSelection,
                                        targetDistanceMeters = targetDistanceMeters,
                                        selected = selected
                                    )
                                )
                            }
                        }.getOrElse {
                            fallbackAnswer
                        }.ifBlank {
                            fallbackAnswer
                        }.ensureCompleteRouteAnswer(fallbackAnswer)
                    } else {
                        fallbackAnswer
                    }
                    aiAnswer = finalAnswer
                    addChatMessage("경기 숨길 AI", finalAnswer)
                }
            }.onFailure { throwable ->
                aiRequestedPlaceResolveFailed = false
                aiRouteStatus = "산책 후보 경로 호출 실패: ${throwable.message ?: "오류 내용을 확인할 수 없습니다."}"
                aiAnswer = aiRouteStatus
                addChatMessage("경기 숨길 AI", aiRouteStatus)
            }
            isLoadingAiRoute = false
        }
    }

    fun handleRouteAction(routeAction: AiRouteConversationAction): Boolean {
        if (routeAction !is AiRouteConversationAction.AdviceOnly) {
            pendingAiRouteRequest = null
            aiRoutes = emptyList()
            selectedAiRouteId = null
            selectedAiCourse = null
            aiAnswer = "경로 탭에서 실제 도보 경로를 검증하고 있습니다. 장소 확인과 검증을 마친 후보를 연결하기 전까지 AI가 산책 코스를 만들지 않습니다."
            aiRouteStatus = aiAnswer
            addChatMessage("경기 숨길 AI", aiAnswer)
            return true
        }
        return when (routeAction) {
            AiRouteConversationAction.AdviceOnly -> {
                pendingAiRouteRequest = null
                false
            }
            is AiRouteConversationAction.AskClarifyingQuestion -> {
                pendingAiRouteRequest = routeAction.pendingRequest
                aiRoutes = emptyList()
                selectedAiRouteId = null
                selectedAiCourse = null
                aiRequestedPlaceResolveFailed = false
                aiRouteStatus = "추가 정보가 필요합니다."
                aiAnswer = routeAction.question
                addChatMessage("경기 숨길 AI", routeAction.question)
                true
            }
            is AiRouteConversationAction.ReadyToRoute -> {
                pendingAiRouteRequest = null
                val targetDistance = routeAction.distanceMeters
                    ?: routeAction.durationMinutes?.let { duration -> duration * 67 }
                buildAiWalkingRoute(
                    requestText = routeAction.requestText,
                    placeQueryOverride = routeAction.placeQuery,
                    placeQueryCandidates = routeAction.placeQueries,
                    targetDistanceOverride = targetDistance,
                    forceCurrentLocationOnly = routeAction.useCurrentLocationOnly,
                    routeShapeHint = routeAction.routeShapeHint
                )
                true
            }
        }
    }

    fun requestAdvice(userMessage: String) {
        val api = geminiApi
        if (api == null) {
            aiAnswer = "AI API 키가 설정되지 않았습니다. local.properties의 GEMINI_API_KEY를 확인하세요."
            addChatMessage("경기 숨길 AI", aiAnswer)
            return
        }

        coroutineScope.launch {
            isLoading = true
            val answer = runCatching {
                withContext(Dispatchers.IO) {
                    api.generateWalkingAdvice(
                        buildGeminiWalkingPrompt(
                            userQuestion = userMessage,
                            currentAirQuality = currentAirQuality,
                            currentWeather = currentWeather,
                            walkingTrailRecommendations = walkingTrailRecommendations
                        )
                    )
                }
            }.getOrElse { throwable ->
                "AI 응답을 불러오지 못했습니다: ${throwable.message ?: "알 수 없는 오류"}"
            }.ifBlank {
                "AI 응답이 비어 있습니다. 질문을 조금 더 구체적으로 입력해 주세요."
            }.ensureCompleteAdviceAnswer(
                userQuestion = userMessage,
                currentAirQuality = currentAirQuality,
                currentWeather = currentWeather,
                walkingTrailRecommendations = walkingTrailRecommendations
            )
            aiAnswer = answer
            addChatMessage("경기 숨길 AI", answer)
            isLoading = false
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(chatScrollState, enabled = !isMapGestureActive)
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        SectionTitle("AI 대기질 상담")
        Text(
            text = aiRouteStatus,
            color = AppColors.Muted,
            style = MaterialTheme.typography.bodyMedium
        )
        Text(
            text = "측정·예보 위치와 시각, 정보 부족을 함께 확인하세요. 대기질·날씨 상담만으로 경로의 통행 가능성을 판단하지 않습니다.",
            color = AppColors.Muted,
            style = MaterialTheme.typography.bodySmall
        )
        aiRoutes.forEach { route ->
            RouteCard(
                route = route,
                highlighted = route.id == selectedAiRoute?.id,
                onClick = { selectedAiRouteId = route.id },
                modifier = Modifier.fillMaxWidth(0.96f)
            )
        }
        chatMessages.forEach { chatMessage ->
            ChatBubble(
                title = chatMessage.title,
                body = chatMessage.body
            )
        }
        if (isLoading) {
            ChatBubble(
                title = "경기 숨길 AI",
                body = "현재 대기질과 날씨를 분석하는 중입니다."
            )
        }
        CardSurface {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = message,
                    onValueChange = { message = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("질문 입력") },
                    placeholder = { Text("예: 30분 정도 산책해도 괜찮아?") }
                )
                Button(
                    onClick = {
                        val userMessage = message.trim()
                        if (userMessage.isBlank()) {
                            aiAnswer = "질문을 입력해 주세요."
                            addChatMessage("경기 숨길 AI", aiAnswer)
                            return@Button
                        }
                        addChatMessage("사용자", userMessage)
                        message = ""

                        if (AiRequestIntentClassifier.isRouteGenerationRequest(userMessage)) {
                            aiAnswer = "경로 탭에서 실제 도보 경로를 검증하고 있습니다. 장소 확인과 경로 검증을 연결하기 전까지 AI가 코스를 생성하지 않습니다."
                            aiRouteStatus = aiAnswer
                            addChatMessage("경기 숨길 AI", aiAnswer)
                            return@Button
                        }
                        requestAdvice(userMessage)
                    },
                    enabled = !isLoading && !isLoadingAiRoute,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = AppColors.Primary)
                ) {
                    Text(if (isLoading || isLoadingAiRoute) "분석 중" else "AI에게 물어보기")
                }
            }
        }
    }
}

private fun buildGeminiWalkingPrompt(
    userQuestion: String,
    currentAirQuality: CurrentAirQualityState,
    currentWeather: CurrentWeatherState,
    walkingTrailRecommendations: List<WalkingTrailRecommendation>
): String {
    val requestedDistance = userQuestion.extractRequestedDistanceMeters()
    return AiPromptTemplates.buildWalkingAdvicePrompt(
        userQuestion = userQuestion,
        airSummary = buildAirPromptSummary(currentAirQuality),
        weatherSummary = buildWeatherPromptSummary(currentWeather),
        trailSummary = buildWalkingTrailPromptSummary(walkingTrailRecommendations),
        requestedDistanceText = requestedDistance?.let { "${formatDistance(it)} 내외" } ?: "명시되지 않음"
    )
}

private fun chooseRouteConversationAction(
    userMessage: String,
    modelRouteAction: AiRouteConversationAction?,
    fallbackRouteAction: AiRouteConversationAction
): AiRouteConversationAction {
    val fallbackReady = fallbackRouteAction as? AiRouteConversationAction.ReadyToRoute
    if (!fallbackReady?.placeQuery.isNullOrBlank()) {
        return fallbackRouteAction
    }

    val modelReady = modelRouteAction as? AiRouteConversationAction.ReadyToRoute
    if (
        modelReady != null &&
        modelReady.useCurrentLocationOnly &&
        modelReady.placeQueries.isEmpty() &&
        !userMessage.allowsCurrentLocationFallbackForRoute()
    ) {
        return buildRoutePlaceClarificationAction(userMessage, modelReady)
    }

    if (
        fallbackReady != null &&
        fallbackReady.useCurrentLocationOnly &&
        fallbackReady.placeQueries.isEmpty() &&
        !userMessage.allowsCurrentLocationFallbackForRoute()
    ) {
        return buildRoutePlaceClarificationAction(userMessage, fallbackReady)
    }

    return if (
        modelRouteAction == null ||
        (modelRouteAction is AiRouteConversationAction.AdviceOnly &&
            fallbackRouteAction !is AiRouteConversationAction.AdviceOnly)
    ) {
        fallbackRouteAction
    } else {
        modelRouteAction
    }
}

private fun buildRoutePlaceClarificationAction(
    userMessage: String,
    routeAction: AiRouteConversationAction.ReadyToRoute
): AiRouteConversationAction.AskClarifyingQuestion {
    return AiRouteConversationAction.AskClarifyingQuestion(
        question = "장소를 정확히 찾지 못했어요. 현재 위치 주변으로 찾을까요, 아니면 장소명을 더 구체적으로 입력할까요? 예: 분당저수지, 중대물빛공원",
        pendingRequest = PendingAiRouteRequest(
            originalRequest = userMessage,
            placeQuery = null,
            distanceMeters = routeAction.distanceMeters ?: userMessage.extractRequestedDistanceMeters(),
            durationMinutes = routeAction.durationMinutes,
            activity = AiRouteActivity.Walk,
            clarificationType = AiRouteClarificationType.NeedStartPoint
        )
    )
}

private fun String.allowsCurrentLocationFallbackForRoute(): Boolean {
    val normalized = replace(" ", "")
    return listOf(
        "현재위치",
        "현위치",
        "내위치",
        "지금위치",
        "근처",
        "주변",
        "가까운",
        "인근",
        "아무",
        "주변",
        "근방",
        "추천",
        "후보",
        "산책길",
        "산책코스",
        "걸을만한"
    ).any { normalized.contains(it) }
}

private fun String.ensureCompleteAdviceAnswer(
    userQuestion: String,
    currentAirQuality: CurrentAirQualityState,
    currentWeather: CurrentWeatherState,
    walkingTrailRecommendations: List<WalkingTrailRecommendation>
): String {
    val trimmed = trim()
    val incompleteEndings = listOf("날씨는", "날씨는,", "날씨는.", "날씨는 ", "대기질은", "현재", "다만")
    val looksIncomplete = trimmed.length < 80 ||
        incompleteEndings.any { ending -> trimmed.endsWith(ending) } ||
        trimmed.count { it == '。' || it == '.' || it == '!' || it == '?' } == 0

    return if (looksIncomplete) {
        buildDeterministicAdviceAnswer(userQuestion, currentAirQuality, currentWeather, walkingTrailRecommendations)
    } else {
        trimmed
    }
}

private fun String.ensureCompleteRouteAnswer(fallbackAnswer: String): String {
    val trimmed = trim()
    val incompleteEndings = listOf(
        "을",
        "를",
        "은",
        "는",
        "이",
        "가",
        "로",
        "으로",
        "와",
        "과",
        "및",
        "현재",
        "다만",
        "보여",
        "기준으로",
        "중심으로"
    )
    val hasSentenceEnd = listOf(".", "!", "?", "다.", "요.", "다", "요").any { ending ->
        trimmed.endsWith(ending)
    }
    val looksIncomplete = trimmed.length < 40 ||
        !hasSentenceEnd ||
        incompleteEndings.any { ending -> trimmed.endsWith(ending) } ||
        trimmed.looksLikePromptChecklistLeak()

    return if (looksIncomplete) fallbackAnswer else trimmed
}

private fun String.looksLikePromptChecklistLeak(): Boolean {
    val lower = lowercase(Locale.ROOT)
    val leakPatterns = listOf(
        "detour disclaimer",
        "only input names",
        "no exaggeration",
        "checklist",
        "included? yes",
        "yes (",
        "* "
    )
    val hasEnglishChecklist = leakPatterns.any { lower.contains(it) }
    val koreanAnswerSignal = listOf("추천", "주의", "비추천", "산책", "대기질", "날씨", "pm10", "pm2.5")
        .any { lower.contains(it) }
    return hasEnglishChecklist && !koreanAnswerSignal
}

private fun buildDeterministicAdviceAnswer(
    userQuestion: String,
    currentAirQuality: CurrentAirQualityState,
    currentWeather: CurrentWeatherState,
    walkingTrailRecommendations: List<WalkingTrailRecommendation>
): String {
    val station = currentAirQuality.station
    val reading = currentAirQuality.reading
    val locationText = station?.let { "${it.city} ${it.name}" } ?: "현재 위치"
    val airText = if (reading != null) {
        val pm10 = reading.pm10?.toString() ?: "--"
        val pm25 = reading.pm25?.toString() ?: "--"
        "$locationText 대기질은 PM10 $pm10㎍/㎥, PM2.5 $pm25㎍/㎥로 '${reading.grade.displayName()}' 수준입니다."
    } else {
        "$locationText 대기질은 아직 확인되지 않았습니다."
    }
    val weather = currentWeather.weather
    val weatherText = if (weather != null) {
        val condition = weather.weatherConditionText()
        val temp = weather.temperatureCelsius?.let { ", 기온 ${formatDecimal(it)}도" }.orEmpty()
        val rain = weather.precipitationMm?.let { ", 강수 ${formatDecimal(it)}mm" }.orEmpty()
        val wind = weather.windSpeedMetersPerSecond?.let { ", 풍속 ${formatDecimal(it)}m/s" }.orEmpty()
        "날씨는 $condition$temp$rain$wind 기준입니다."
    } else {
        "날씨는 현재 불러오지 못했으니 비나 강풍 여부는 출발 전에 한 번 더 확인하세요."
    }
    val trailText = walkingTrailRecommendations.firstOrNull()?.let { recommendation ->
        "근처 후보로는 ${recommendation.trail.name}을 참고할 수 있고, 산책 전 지도에서 실제 보행로를 확인하는 편이 좋습니다."
    } ?: "근처 산책로 후보는 아직 확인되지 않았습니다."
    val conclusion = if (userQuestion.contains("후보") || userQuestion.contains("보여")) {
        "앱의 지도 후보를 함께 확인하면서 큰 도로보다 강변·공원 쪽을 우선해 보세요."
    } else {
        "무리하지 않는 짧은 산책은 가능하지만, 민감군은 마스크와 휴식을 고려하세요."
    }

    return listOf(airText, weatherText, trailText, conclusion).joinToString(" ")
}

private fun buildGeminiRouteDecisionPrompt(
    userMessage: String,
    recentMessages: List<AiChatMessage>,
    hasCurrentLocation: Boolean,
    currentAirQuality: CurrentAirQualityState,
    currentWeather: CurrentWeatherState,
    walkingTrailRecommendations: List<WalkingTrailRecommendation>
): String {
    return AiPromptTemplates.buildRouteDecisionPrompt(
        userMessage = userMessage,
        recentConversation = buildRecentChatPromptSummary(recentMessages),
        hasCurrentLocation = hasCurrentLocation,
        airSummary = buildAirPromptSummary(currentAirQuality),
        weatherSummary = buildWeatherPromptSummary(currentWeather),
        trailSummary = buildWalkingTrailPromptSummary(walkingTrailRecommendations)
    )
}

private fun buildGeminiRoutePrompt(
    userRequest: String,
    currentAirQuality: CurrentAirQualityState,
    currentWeather: CurrentWeatherState,
    walkingTrailRecommendations: List<WalkingTrailRecommendation>,
    courseSelection: AiWalkingCourseSelection?,
    targetDistanceMeters: Int?,
    selected: RouteCandidate
): String {
    return AiPromptTemplates.buildWalkingRoutePrompt(
        userRequest = userRequest.ifBlank { "현재 위치 기준으로 무리 없는 산책길 추천" },
        routeSummary = buildRoutePromptSummary(
            courseSelection = courseSelection,
            targetDistanceMeters = targetDistanceMeters,
            selected = selected
        ),
        airSummary = buildAirPromptSummary(currentAirQuality),
        weatherSummary = buildWeatherPromptSummary(currentWeather),
        trailSummary = buildWalkingTrailPromptSummary(walkingTrailRecommendations)
    )
}

private fun buildRecentChatPromptSummary(messages: List<AiChatMessage>): String {
    return messages
        .takeLast(6)
        .joinToString("\n") { message -> "- ${message.title}: ${message.body}" }
        .ifBlank { "- 최근 대화 없음" }
}

private fun buildAirPromptSummary(currentAirQuality: CurrentAirQualityState): String {
    val station = currentAirQuality.station
    val reading = currentAirQuality.reading
    return if (station != null && reading != null) {
        """
        - 위치/측정소: ${station.city} ${station.name}
        - 측정 시각: ${reading.measuredAt}
        - PM10: ${reading.pm10 ?: "확인 불가"} ug/m3
        - PM2.5: ${reading.pm25 ?: "확인 불가"} ug/m3
        - 앱 산출 산책 점수: ${reading.airQualityScore()}점
        - 등급: ${reading.grade.displayName()}
        - 상태 문구: ${currentAirQuality.status}
        """.trimIndent()
    } else {
        """
        - 위치/측정소: 확인 불가
        - 상태 문구: ${currentAirQuality.status}
        """.trimIndent()
    }
}

private fun buildWeatherPromptSummary(currentWeather: CurrentWeatherState): String {
    val weather = currentWeather.weather
    return if (weather != null) {
        """
        - 기준 시각: ${weather.measuredAt}
        - 하늘상태: ${weather.skyState?.label ?: "확인 불가"}
        - 강수형태: ${weather.precipitationType?.label ?: "확인 불가"}
        - 기온: ${weather.temperatureCelsius?.let { "${formatDecimal(it)}도" } ?: "확인 불가"}
        - 1시간 강수량: ${weather.precipitationMm?.let { "${formatDecimal(it)}mm" } ?: "확인 불가"}
        - 습도: ${weather.humidityPercent?.let { "$it%" } ?: "확인 불가"}
        - 풍속: ${weather.windSpeedMetersPerSecond?.let { "${formatDecimal(it)}m/s" } ?: "확인 불가"}
        """.trimIndent()
    } else {
        """
        - 상태 문구: ${currentWeather.status}
        """.trimIndent()
    }
}

private fun buildWalkingTrailPromptSummary(
    walkingTrailRecommendations: List<WalkingTrailRecommendation>
): String {
    return walkingTrailRecommendations.take(3).joinToString("\n") { recommendation ->
        val distance = recommendation.distanceFromUserMeters?.let(::formatDistance) ?: "현재 위치 확인 후 계산"
        "- ${recommendation.trail.name} (${recommendation.trail.sigunName}, ${recommendation.typeLabel}, 산책로 ${formatDistance(recommendation.trail.lengthMeters)}, 현재 기준 $distance)"
    }.ifBlank {
        "- 산책로 후보 없음"
    }
}

private fun buildRoutePromptSummary(
    courseSelection: AiWalkingCourseSelection?,
    targetDistanceMeters: Int?,
    selected: RouteCandidate
): String {
    val courseName = courseSelection?.course?.name ?: "현재 위치 주변"
    val routeBasis = if (selected.id.startsWith("ai-catalog-")) "공공 산책로 후보 기반 코스" else "Tmap 보행 경로 기반 코스"
    val targetText = targetDistanceMeters?.let { "- 사용자 요청 거리: ${formatDistance(it)}" } ?: "- 사용자 요청 거리: 명시되지 않음"
    return """
        - 기준 장소: $courseName
        - 경로 산출 방식: $routeBasis
        $targetText
        - 실제 계산 거리: ${formatDistance(selected.distanceMeters)}
        - 예상 시간: 약 ${selected.durationMinutes}분
        - 지도 좌표 수: ${selected.coordinates.size}개
        - 경로 카드 제목: ${selected.title}
        - 경로 강조 태그: ${selected.highlightLabel}
        - 경로 설명: ${selected.exposureSummary}
    """.trimIndent()
}

@Composable
private fun AirQualitySummaryCard(
    state: CurrentAirQualityState,
    onRefreshLocation: () -> Unit
) {
    val station = state.station
    val reading = state.reading
    val airScore = reading?.airQualityScore()

    CardSurface {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("현재 위치 대기질", color = AppColors.Muted)
                    Text(
                        text = station?.let { "${it.city} ${it.name}" } ?: "--",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                }
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    StatusBadge(reading?.grade?.displayName() ?: "--")
                    RefreshIconButton(onClick = onRefreshLocation)
                }
            }

            Divider(color = AppColors.Border)

            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                MetricBlock(
                    label = "PM10",
                    value = reading?.pm10?.toString() ?: "-",
                    unit = "ug/m3",
                    modifier = Modifier.weight(1f)
                )
                MetricBlock(
                    label = "PM2.5",
                    value = reading?.pm25?.toString() ?: "-",
                    unit = "ug/m3",
                    modifier = Modifier.weight(1f)
                )
                MetricBlock(
                    label = "추천",
                    value = airScore?.toString() ?: "-",
                    unit = "점",
                    modifier = Modifier.weight(1f)
                )
            }

            Text(
                text = reading?.let { "${it.measuredAt} 기준 ${state.status}" } ?: state.status,
                color = AppColors.Muted,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}

@Composable
private fun WeatherSummaryCard(
    state: CurrentWeatherState,
    onRefreshWeather: () -> Unit
) {
    val weather = state.weather

    CardSurface {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("현재 위치 날씨", color = AppColors.Muted)
                    Text(
                        text = weather?.temperatureCelsius?.let { "${formatDecimal(it)}도" } ?: "--",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                }
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    StatusBadge(weather?.weatherConditionText() ?: "--")
                    RefreshIconButton(onClick = onRefreshWeather)
                }
            }

            Divider(color = AppColors.Border)

            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                MetricBlock(
                    label = "강수",
                    value = weather?.precipitationMm?.let(::formatDecimal) ?: "-",
                    unit = "mm",
                    modifier = Modifier.weight(1f)
                )
                MetricBlock(
                    label = "습도",
                    value = weather?.humidityPercent?.toString() ?: "-",
                    unit = "%",
                    modifier = Modifier.weight(1f)
                )
                MetricBlock(
                    label = "풍속",
                    value = weather?.windSpeedMetersPerSecond?.let(::formatDecimal) ?: "-",
                    unit = "m/s",
                    modifier = Modifier.weight(1f)
                )
            }

            Text(
                text = weather?.let { "${it.measuredAt} 기준 기상청 초단기실황입니다." } ?: state.status,
                color = AppColors.Muted,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}

@Composable
private fun RefreshIconButton(onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .size(36.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(Color(0xFFF2F4F3))
            .border(1.dp, AppColors.Border, RoundedCornerShape(12.dp))
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = "↻",
            color = AppColors.Ink,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold
        )
    }
}

@Composable
private fun MapPreviewCard(
    route: RouteCandidate?,
    interactive: Boolean,
    isLoading: Boolean,
    focusedTrail: GyeonggiWalkingTrail?,
    pickedStart: GeoPoint?,
    pickedWaypoint: GeoPoint?,
    pickedDestination: GeoPoint?,
    pickTarget: MapPickTarget?,
    cameraTarget: GeoPoint?,
    cameraRequestId: Int,
    onMapCenterChanged: (GeoPoint) -> Unit,
    onMapGestureActiveChanged: (Boolean) -> Unit = {}
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(240.dp)
            .background(Color.White, RoundedCornerShape(22.dp))
            .border(1.dp, AppColors.Border, RoundedCornerShape(22.dp))
            .padding(1.dp)
    ) {
        when {
            isLoading -> {
                MapStatusCard(
                    message = "Tmap 보행자 경로를 불러오는 중입니다.",
                    modifier = Modifier.align(Alignment.Center)
                )
            }
            BuildConfig.NAVER_CLIENT_ID.isNotBlank() -> {
                NaverRouteMapPreview(
                    route = route,
                    focusedTrail = focusedTrail,
                    pickedStart = pickedStart,
                    pickedWaypoint = pickedWaypoint,
                    pickedDestination = pickedDestination,
                    pickTarget = pickTarget,
                    cameraTarget = cameraTarget,
                    cameraRequestId = cameraRequestId,
                    onMapCenterChanged = onMapCenterChanged,
                    onMapGestureActiveChanged = onMapGestureActiveChanged,
                    modifier = Modifier.fillMaxSize()
                )
                if (interactive && pickTarget != null) {
                    CenterPickMarker(
                        modifier = Modifier.align(Alignment.Center)
                    )
                }
            }
            else -> {
                MapStatusCard(
                    message = "네이버 지도 키가 설정되면 경로 지도를 표시합니다.",
                    modifier = Modifier.align(Alignment.Center)
                )
            }
        }
    }
}

@Composable
private fun NaverRouteMapPreview(
    route: RouteCandidate?,
    focusedTrail: GyeonggiWalkingTrail?,
    pickedStart: GeoPoint?,
    pickedWaypoint: GeoPoint?,
    pickedDestination: GeoPoint?,
    pickTarget: MapPickTarget?,
    cameraTarget: GeoPoint?,
    cameraRequestId: Int,
    onMapCenterChanged: (GeoPoint) -> Unit,
    onMapGestureActiveChanged: (Boolean) -> Unit,
    modifier: Modifier = Modifier
) {
    var mapView by remember { mutableStateOf<MapView?>(null) }

    DisposableEffect(Unit) {
        onDispose {
            onMapGestureActiveChanged(false)
            mapView?.onPause()
            mapView?.onStop()
            mapView?.onDestroy()
        }
    }

    Box(modifier = modifier.background(AppColors.Background)) {
        AndroidView(
            factory = { context ->
                MapView(context).apply {
                    mapView = this
                    installMapGestureTouchListener(onMapGestureActiveChanged)
                    onCreate(null)
                    onStart()
                    onResume()
                    renderMapState(route, focusedTrail, pickedStart, pickedWaypoint, pickedDestination, pickTarget, cameraTarget, cameraRequestId, onMapCenterChanged)
                }
            },
            update = { view ->
                view.installMapGestureTouchListener(onMapGestureActiveChanged)
                view.renderMapState(route, focusedTrail, pickedStart, pickedWaypoint, pickedDestination, pickTarget, cameraTarget, cameraRequestId, onMapCenterChanged)
            },
            modifier = Modifier.fillMaxSize()
        )
        if (route != null && route.coordinates.size < 2) {
            MapStatusCard(
                message = "정확한 산책로 선형 데이터가 없어 경로선 대신 추천 장소만 표시합니다.",
                modifier = Modifier.align(Alignment.Center)
            )
        }
    }
}

private fun MapView.installMapGestureTouchListener(onMapGestureActiveChanged: (Boolean) -> Unit) {
    setOnTouchListener { view, event ->
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN,
            MotionEvent.ACTION_MOVE,
            MotionEvent.ACTION_POINTER_DOWN -> {
                view.parent?.requestDisallowInterceptTouchEvent(true)
                onMapGestureActiveChanged(true)
            }
            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_CANCEL -> {
                view.parent?.requestDisallowInterceptTouchEvent(false)
                onMapGestureActiveChanged(false)
            }
        }
        false
    }
}

private fun MapView.renderMapState(
    route: RouteCandidate?,
    focusedTrail: GyeonggiWalkingTrail?,
    pickedStart: GeoPoint?,
    pickedWaypoint: GeoPoint?,
    pickedDestination: GeoPoint?,
    pickTarget: MapPickTarget?,
    cameraTarget: GeoPoint?,
    cameraRequestId: Int,
    onMapCenterChanged: (GeoPoint) -> Unit
) {
    val routeKey = buildMapRenderKey(route, focusedTrail, pickedStart, pickedWaypoint, pickedDestination, pickTarget, cameraTarget, cameraRequestId)
    val currentState = tag as? NaverRouteOverlayState
    if (currentState?.routeKey == routeKey) return

    tag = NaverRouteOverlayState(
        routeKey = routeKey,
        overlays = currentState?.overlays.orEmpty()
    )

    getMapAsync { naverMap ->
        val latestState = tag as? NaverRouteOverlayState
        if (latestState?.routeKey != routeKey) {
            return@getMapAsync
        }

        naverMap.setOnMapClickListener(null)
        naverMap.addOnCameraIdleListener {
            val target = naverMap.cameraPosition.target
            onMapCenterChanged(GeoPoint(target.latitude, target.longitude))
        }
        latestState.overlays.forEach { overlay -> overlay.map = null }
        val overlays = naverMap.drawMapState(route, focusedTrail, pickedStart, pickedWaypoint, pickedDestination)
        if (cameraTarget != null) {
            naverMap.moveCamera(CameraUpdate.scrollTo(cameraTarget.toLatLng()))
        }
        tag = NaverRouteOverlayState(routeKey, overlays)
    }
}

private fun NaverMap.drawMapState(
    route: RouteCandidate?,
    focusedTrail: GyeonggiWalkingTrail?,
    pickedStart: GeoPoint?,
    pickedWaypoint: GeoPoint?,
    pickedDestination: GeoPoint?
): List<Overlay> {
    uiSettings.isZoomControlEnabled = true
    uiSettings.isCompassEnabled = true
    uiSettings.isScaleBarEnabled = true

    val points = route?.coordinates.orEmpty().map { point ->
        LatLng(point.latitude, point.longitude)
    }
    val overlays = mutableListOf<Overlay>()
    if (points.size >= 2) {
        overlays += PathOverlay().apply {
            coords = points
            color = route?.routeColorArgb?.toInt() ?: 0xFF2E7D5B.toInt()
            outlineColor = android.graphics.Color.WHITE
            width = 12
            outlineWidth = 4
            map = this@drawMapState
        }
    }

    val singleRoutePosition = if (route != null && points.size == 1 && pickedStart == null && pickedDestination == null) {
        points.first()
    } else {
        null
    }
    val startPosition = if (singleRoutePosition == null) {
        pickedStart?.toLatLng() ?: points.firstOrNull()
    } else {
        null
    }
    val destinationPosition = pickedDestination?.toLatLng() ?: if (points.size >= 2) points.lastOrNull() else null
    val focusedTrailPosition = focusedTrail?.center?.toLatLng()

    if (focusedTrailPosition != null) {
        overlays += Marker().apply {
            position = focusedTrailPosition
            captionText = focusedTrail.name
            subCaptionText = focusedTrail.sigunName
            map = this@drawMapState
        }
    }

    if (singleRoutePosition != null) {
        overlays += Marker().apply {
            position = singleRoutePosition
            captionText = route?.title.orEmpty()
            subCaptionText = "후보 위치"
            map = this@drawMapState
        }
    }

    if (startPosition != null) {
        overlays += Marker().apply {
            position = startPosition
            captionText = "출발"
            map = this@drawMapState
        }
    }
    if (pickedWaypoint != null) {
        overlays += Marker().apply {
            position = pickedWaypoint.toLatLng()
            captionText = "경유"
            map = this@drawMapState
        }
    }
    if (destinationPosition != null) {
        overlays += Marker().apply {
            position = destinationPosition
            captionText = "도착"
            map = this@drawMapState
        }
    }

    if (points.size >= 2) {
        val boundsBuilder = LatLngBounds.Builder()
        points.forEach { point -> boundsBuilder.include(point) }
        moveCamera(CameraUpdate.fitBounds(boundsBuilder.build(), 64))
    } else if (startPosition != null && destinationPosition != null) {
        val boundsBuilder = LatLngBounds.Builder()
        boundsBuilder.include(startPosition)
        boundsBuilder.include(destinationPosition)
        moveCamera(CameraUpdate.fitBounds(boundsBuilder.build(), 64))
    } else if (focusedTrailPosition != null) {
        moveCamera(CameraUpdate.scrollTo(focusedTrailPosition))
    } else if (startPosition != null) {
        moveCamera(CameraUpdate.scrollTo(startPosition))
    } else {
        moveCamera(CameraUpdate.scrollTo(DEFAULT_MAP_CENTER))
    }

    return overlays
}

private data class NaverRouteOverlayState(
    val routeKey: String,
    val overlays: List<Overlay>
)

@Composable
private fun CenterPickMarker(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.offset(y = (-16).dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            modifier = Modifier
                .size(28.dp)
                .clip(RoundedCornerShape(999.dp))
                .background(AppColors.Primary)
                .border(3.dp, Color.White, RoundedCornerShape(999.dp))
        )
        Box(
            modifier = Modifier
                .size(width = 3.dp, height = 18.dp)
                .background(AppColors.Primary)
        )
    }
}

@Composable
private fun MapStatusCard(
    message: String,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .padding(horizontal = 18.dp)
            .background(Color.White.copy(alpha = 0.94f), RoundedCornerShape(18.dp))
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text("지도 상태", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Text(message, color = AppColors.Muted)
    }
}

@Composable
private fun RouteCard(
    route: RouteCandidate,
    highlighted: Boolean,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null
) {
    CardSurface(
        modifier = modifier,
        borderColor = if (highlighted) AppColors.Primary else AppColors.Border,
        contentPadding = 16.dp,
        onClick = onClick
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(route.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    StatusBadge(route.highlightLabel)
                    StatusBadge("${route.airScore}점")
                }
            }
            Text("${formatDistance(route.distanceMeters)} · 약 ${route.durationMinutes}분", color = AppColors.Muted)
            Text(route.exposureSummary, color = AppColors.Ink)
        }
    }
}

@Composable
private fun WalkingTrailRecommendationList(
    recommendations: List<WalkingTrailRecommendation>,
    onMapClick: (WalkingTrailRecommendation) -> Unit
) {
    CardSurface(contentPadding = 14.dp) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(
                        text = "경기데이터드림 산책로 현황",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = AppColors.Ink
                    )
                }
                StatusBadge("${recommendations.size}개")
            }

            recommendations.forEachIndexed { index, recommendation ->
                WalkingTrailRecommendationRow(
                    recommendation = recommendation,
                    onMapClick = { onMapClick(recommendation) }
                )
                if (index < recommendations.lastIndex) {
                    Divider(color = AppColors.Border)
                }
            }
        }
    }
}

@Composable
private fun WalkingTrailRecommendationRow(
    recommendation: WalkingTrailRecommendation,
    onMapClick: () -> Unit
) {
    val trail = recommendation.trail

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .clickable(onClick = onMapClick)
            .padding(vertical = 4.dp),
        verticalArrangement = Arrangement.spacedBy(7.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = trail.name,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = AppColors.Ink
            )
            StatusBadge(recommendation.typeLabel)
        }
        Text(
            text = "${trail.sigunName} · ${formatDistance(trail.lengthMeters)} · 약 ${trail.durationMinutes}분",
            style = MaterialTheme.typography.bodyMedium,
            color = AppColors.Muted
        )
        Text(
            text = recommendation.distanceFromUserMeters?.let { distance ->
                "현재 기준 약 ${formatDistance(distance)} · ${recommendation.reason}"
            } ?: "현재 위치를 확인하면 가까운 순서로 다시 정렬됩니다. ${recommendation.reason}",
            style = MaterialTheme.typography.bodySmall,
            color = AppColors.Muted
        )
    }
}

@Composable
private fun ChatBubble(
    title: String,
    body: String
) {
    CardSurface {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, color = AppColors.Primary, fontWeight = FontWeight.Bold)
            Text(body, color = AppColors.Ink)
        }
    }
}

@Composable
private fun MetricBlock(
    label: String,
    value: String,
    unit: String,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .background(AppColors.Background, RoundedCornerShape(16.dp))
            .padding(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(label, color = AppColors.Muted)
        Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = AppColors.Ink)
        Text(unit, color = AppColors.Muted, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleLarge,
        fontWeight = FontWeight.Bold,
        color = AppColors.Ink
    )
}

@Composable
private fun StatusBadge(text: String) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(Color(0xFFEAF7F0))
            .padding(horizontal = 14.dp, vertical = 7.dp)
    ) {
        Text(text, color = AppColors.Primary, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun CompactRouteButton(
    label: String,
    selected: Boolean,
    modifier: Modifier = Modifier,
    selectedColor: Color = AppColors.Primary,
    onClick: () -> Unit
) {
    val background = if (selected) selectedColor else Color.White
    val foreground = if (selected) Color.White else AppColors.Ink
    val borderColor = if (selected) selectedColor else AppColors.Border

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(999.dp))
            .background(background)
            .border(1.dp, borderColor, RoundedCornerShape(999.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 8.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = label,
            color = foreground,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.bodySmall
        )
    }
}

@Composable
private fun TabButton(
    label: String,
    selected: Boolean,
    onClick: () -> Unit
) {
    val background = if (selected) AppColors.Primary else Color.White
    val foreground = if (selected) Color.White else AppColors.Ink
    val borderColor = if (selected) AppColors.Primary else AppColors.Border

    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(background)
            .border(1.dp, borderColor, RoundedCornerShape(999.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 9.dp)
    ) {
        Text(label, color = foreground, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun ActionPillButton(
    label: String,
    background: Color,
    onClick: () -> Unit
) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(background)
            .border(1.dp, background, RoundedCornerShape(999.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 9.dp)
    ) {
        Text(label, color = Color.White, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun CardSurface(
    modifier: Modifier = Modifier,
    borderColor: Color = AppColors.Border,
    contentPadding: androidx.compose.ui.unit.Dp = 18.dp,
    onClick: (() -> Unit)? = null,
    content: @Composable () -> Unit
) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(24.dp))
            .background(Color.White)
            .border(1.dp, borderColor, RoundedCornerShape(24.dp))
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(contentPadding)
    ) {
        content()
    }
}

private enum class AppTab(val label: String) {
    Home("홈"),
    Route("경로"),
    Chat("AI 상담")
}

private enum class MapPickTarget {
    Start,
    Waypoint,
    Destination
}

private data class CurrentAirQualityState(
    val station: AirQualityStation?,
    val reading: AirQualityReading?,
    val status: String
) {
    companion object {
        fun empty(status: String = "위치 권한이 없으면 현재 위치 대기질은 표시되지 않습니다."): CurrentAirQualityState {
            return CurrentAirQualityState(
                station = null,
                reading = null,
                status = status
            )
        }
    }
}

private data class CurrentWeatherState(
    val weather: KmaCurrentWeather?,
    val status: String
) {
    companion object {
        fun empty(status: String = "위치 권한이 없으면 현재 위치 날씨는 표시되지 않습니다."): CurrentWeatherState {
            return CurrentWeatherState(
                weather = null,
                status = status
            )
        }
    }
}

private fun CurrentAirQualityResult.toState(
    status: String = "AirKorea 실시간 측정정보 기준입니다."
): CurrentAirQualityState {
    return CurrentAirQualityState(
        station = station,
        reading = reading,
        status = status
    )
}

private fun KmaCurrentWeather.toState(
    status: String = "기상청 초단기실황 기준입니다."
): CurrentWeatherState {
    return CurrentWeatherState(
        weather = this,
        status = status
    )
}

private object AppColors {
    val Primary = Color(0xFF2E7D5B)
    val MapAction = Color(0xFF2F6FED)
    val Ink = Color(0xFF16231D)
    val Muted = Color(0xFF53655C)
    val Border = Color(0xFFDCE8E1)
    val Background = Color(0xFFF3FAF6)
}

private const val DEFAULT_START = "수원시청"
private const val DEFAULT_DESTINATION = "광교호수공원"
private const val MIN_ROUTE_DISTANCE_METERS = 100
private const val KOREA_PM10_HIGH_REFERENCE = 151.0
private const val KOREA_PM25_HIGH_REFERENCE = 76.0
private const val LOCATION_CACHE_MAX_AGE_MILLIS = 10 * 60 * 1000L
private const val FAST_CURRENT_LOCATION_TIMEOUT_MILLIS = 12_000L
private const val CURRENT_LOCATION_TIMEOUT_MILLIS = 12_000L
private const val AIR_QUALITY_REQUEST_TIMEOUT_MILLIS = 12_000L
private const val WEATHER_REQUEST_TIMEOUT_MILLIS = 5_000L
private const val MAX_CURRENT_LOCATION_AGE_MILLIS = 10 * 60 * 1000L
private const val MAX_CURRENT_LOCATION_ACCURACY_METERS = 1_000f
private const val GPS_LOCATION_ATTEMPT_TIMEOUT_MILLIS = 6_000L
private const val NETWORK_LOCATION_ATTEMPT_TIMEOUT_MILLIS = 5_000L
private const val LOOP_ROUTE_DISTANCE_EXPANSION_FACTOR = 1.45
private const val DEFAULT_AI_WALK_DISTANCE_METERS = 2_500
private const val AI_COURSE_LOCAL_START_MAX_METERS = 1_800.0
private const val APP_LOG_TAG = "GyeonggiSumgil"
private val DEFAULT_MAP_CENTER = LatLng(37.2636, 127.0286)

private data class LocatedGeoPoint(
    val point: GeoPoint,
    val provider: String?,
    val accuracyMeters: Float?,
    val ageMillis: Long?
)

private data class AiRouteBuildResult(
    val courseSelection: AiWalkingCourseSelection?,
    val requestedPlaceName: String?,
    val requestedPlaceResolveFailed: Boolean,
    val routes: List<RouteCandidate>
)

private data class AiChatMessage(
    val title: String,
    val body: String
)

private fun Throwable.toAirQualityFailureMessage(): String {
    return when (this) {
        is SocketTimeoutException,
        is TimeoutCancellationException -> "AirKorea 응답이 지연되고 있습니다. 잠시 후 대기질 갱신을 다시 눌러주세요."
        else -> "대기질 정보를 불러오지 못했습니다: ${message ?: "알 수 없는 오류"}"
    }
}

private fun formatDistance(distanceMeters: Int): String {
    return String.format(Locale.KOREA, "%.1f km", distanceMeters / 1000.0)
}

private fun formatDecimal(value: Double): String {
    return if (value % 1.0 == 0.0) {
        value.toInt().toString()
    } else {
        String.format(Locale.KOREA, "%.1f", value)
    }
}

private fun KmaCurrentWeather.weatherConditionText(): String {
    return when (precipitationType) {
        com.gyeonggisumgil.app.data.weather.KmaPrecipitationType.Rain -> "비"
        com.gyeonggisumgil.app.data.weather.KmaPrecipitationType.RainSnow -> "비/눈"
        com.gyeonggisumgil.app.data.weather.KmaPrecipitationType.Snow -> "눈"
        com.gyeonggisumgil.app.data.weather.KmaPrecipitationType.Shower -> "소나기"
        com.gyeonggisumgil.app.data.weather.KmaPrecipitationType.Raindrop -> "빗방울"
        com.gyeonggisumgil.app.data.weather.KmaPrecipitationType.RaindropSnow -> "빗방울/눈"
        com.gyeonggisumgil.app.data.weather.KmaPrecipitationType.SnowFlurry -> "눈날림"
        com.gyeonggisumgil.app.data.weather.KmaPrecipitationType.None,
        null -> skyState?.label ?: "맑음"
    }
}

private fun AirQualityGrade.displayName(): String {
    return when (this) {
        AirQualityGrade.GOOD -> "좋음"
        AirQualityGrade.NORMAL -> "보통"
        AirQualityGrade.BAD -> "나쁨"
        AirQualityGrade.VERY_BAD -> "매우 나쁨"
        AirQualityGrade.UNKNOWN -> "확인 중"
    }
}

private fun AirQualityReading.airQualityScore(): Int {
    val scores = listOfNotNull(
        pm10?.annualParticleScore(highReference = KOREA_PM10_HIGH_REFERENCE),
        pm25?.annualParticleScore(highReference = KOREA_PM25_HIGH_REFERENCE)
    )
    return if (scores.isEmpty()) 0 else scores.average().toInt().coerceIn(0, 100)
}

private fun Int.annualParticleScore(highReference: Double): Int {
    val normalized = (this.toDouble() / highReference).coerceIn(0.0, 1.0)
    val annualBurden = Math.pow(normalized, 1.45)
    return Math.round(100.0 - (annualBurden * 100.0)).toInt().coerceIn(0, 100)
}

private fun RouteCandidate.renderKey(): String {
    return buildString {
        append(id)
        append(':')
        append(coordinates.size)
        coordinates.forEach { point ->
            append(':')
            append(point.latitude)
            append(',')
            append(point.longitude)
        }
    }
}

private fun buildMapRenderKey(
    route: RouteCandidate?,
    focusedTrail: GyeonggiWalkingTrail?,
    pickedStart: GeoPoint?,
    pickedWaypoint: GeoPoint?,
    pickedDestination: GeoPoint?,
    pickTarget: MapPickTarget?,
    cameraTarget: GeoPoint?,
    cameraRequestId: Int
): String {
    return buildString {
        append(route?.renderKey() ?: "empty")
        append(':')
        append(focusedTrail?.id)
        append(',')
        append(focusedTrail?.center?.latitude)
        append(',')
        append(focusedTrail?.center?.longitude)
        append(':')
        append(pickedStart?.latitude)
        append(',')
        append(pickedStart?.longitude)
        append(':')
        append(pickedWaypoint?.latitude)
        append(',')
        append(pickedWaypoint?.longitude)
        append(':')
        append(pickedDestination?.latitude)
        append(',')
        append(pickedDestination?.longitude)
        append(':')
        append(pickTarget?.name)
        append(':')
        append(cameraTarget?.latitude)
        append(',')
        append(cameraTarget?.longitude)
        append(':')
        append(cameraRequestId)
    }
}

private fun GeoPoint.toTmapPlace(name: String): TmapPlace {
    return TmapPlace(
        name = name,
        longitude = longitude,
        latitude = latitude
    )
}

private fun TmapPlace.toGeoPoint(): GeoPoint {
    return GeoPoint(latitude = latitude, longitude = longitude)
}

private fun GeoPoint.toLatLng(): LatLng {
    return LatLng(latitude, longitude)
}

private fun LatLng.toGeoPoint(): GeoPoint {
    return GeoPoint(latitude, longitude)
}

private suspend fun resolveAiRouteStartPoint(
    context: Context,
    currentUserLocation: GeoPoint?,
    currentAirQuality: CurrentAirQualityState,
    focusedTrail: GyeonggiWalkingTrail?
): GeoPoint {
    val liveLocation = runCatching {
        withTimeoutOrNull(FAST_CURRENT_LOCATION_TIMEOUT_MILLIS) {
            context.findCurrentLocationPoint(preferFastProvider = true)
        }
    }.getOrNull()

    val recentLocation = liveLocation ?: context.findBestLastKnownLocatedLocation(
        maxAgeMillis = LOCATION_CACHE_MAX_AGE_MILLIS
    )

    return recentLocation?.point
        ?: currentUserLocation
        ?: currentAirQuality.station?.let { station -> GeoPoint(station.latitude, station.longitude) }
        ?: focusedTrail?.center
        ?: DEFAULT_MAP_CENTER.toGeoPoint()
}

private fun Context.hasFineLocationPermission(): Boolean {
    return ContextCompat.checkSelfPermission(
        this,
        Manifest.permission.ACCESS_FINE_LOCATION
    ) == PackageManager.PERMISSION_GRANTED
}

private suspend fun Context.findCurrentLocationPoint(preferFastProvider: Boolean = false): LocatedGeoPoint? {
    if (!hasFineLocationPermission()) return null

    val locationManager = getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return null
    val providerCandidates = if (preferFastProvider) {
        listOf(LocationManager.NETWORK_PROVIDER, LocationManager.GPS_PROVIDER, LocationManager.PASSIVE_PROVIDER)
    } else {
        listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER, LocationManager.PASSIVE_PROVIDER)
    }
    val providers = providerCandidates.filter { provider ->
        runCatching { locationManager.isProviderEnabled(provider) }.getOrDefault(false)
    }
    if (providers.isEmpty()) return null

    providers.forEach { provider ->
        val timeoutMillis = when (provider) {
            LocationManager.GPS_PROVIDER -> GPS_LOCATION_ATTEMPT_TIMEOUT_MILLIS
            LocationManager.NETWORK_PROVIDER -> NETWORK_LOCATION_ATTEMPT_TIMEOUT_MILLIS
            else -> NETWORK_LOCATION_ATTEMPT_TIMEOUT_MILLIS
        }
        val location = withTimeoutOrNull(timeoutMillis) {
            awaitCurrentLocation(locationManager, provider)
        }
        if (location != null) return location
        Log.w(APP_LOG_TAG, "current location provider timed out. provider=$provider, timeoutMs=$timeoutMillis")
    }

    return null
}

private suspend fun Context.awaitCurrentLocation(
    locationManager: LocationManager,
    provider: String
): LocatedGeoPoint? {
    return suspendCancellableCoroutine { continuation ->
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val cancellationSignal = CancellationSignal()
            locationManager.getCurrentLocation(
                provider,
                cancellationSignal,
                mainExecutor
            ) { location ->
                if (continuation.isActive) {
                    continuation.resume(location?.toLocatedGeoPoint())
                }
            }
            continuation.invokeOnCancellation { cancellationSignal.cancel() }
        } else {
            val listener = object : LocationListener {
                override fun onLocationChanged(location: Location) {
                    if (continuation.isActive) {
                        continuation.resume(location.toLocatedGeoPoint())
                    }
                    locationManager.removeUpdates(this)
                }
            }
            locationManager.requestSingleUpdate(provider, listener, Looper.getMainLooper())
            continuation.invokeOnCancellation { locationManager.removeUpdates(listener) }
        }
    }
}

private fun Location.toLocatedGeoPoint(): LocatedGeoPoint {
    return LocatedGeoPoint(
        point = GeoPoint(latitude, longitude),
        provider = provider,
        accuracyMeters = if (hasAccuracy()) accuracy else null,
        ageMillis = (System.currentTimeMillis() - time).coerceAtLeast(0L)
    )
}

private fun LocatedGeoPoint.isReliableForAirQuality(): Boolean {
    val age = ageMillis ?: return false
    val accuracy = accuracyMeters
    val isFresh = age <= MAX_CURRENT_LOCATION_AGE_MILLIS
    val isAccurateEnough = accuracy == null || accuracy <= MAX_CURRENT_LOCATION_ACCURACY_METERS
    return isFresh && isAccurateEnough
}

private fun Context.findBestLastKnownLocation(maxAgeMillis: Long? = null): GeoPoint? {
    return findBestLastKnownLocatedLocation(maxAgeMillis)?.point
}

private fun Context.findBestLastKnownLocatedLocation(maxAgeMillis: Long? = null): LocatedGeoPoint? {
    if (!hasFineLocationPermission()) return null

    val locationManager = getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return null
    val providers = listOf(
        LocationManager.GPS_PROVIDER,
        LocationManager.NETWORK_PROVIDER,
        LocationManager.PASSIVE_PROVIDER
    )
    return providers
        .mapNotNull { provider ->
            runCatching {
                locationManager.getLastKnownLocation(provider)
            }.getOrNull()
        }
        .filter { location ->
            maxAgeMillis == null || System.currentTimeMillis() - location.time <= maxAgeMillis
        }
        .maxByOrNull(Location::getTime)
        ?.toLocatedGeoPoint()
        ?.also { location ->
            Log.d(
                APP_LOG_TAG,
                "last known location=${location.point.latitude},${location.point.longitude}, provider=${location.provider}, accuracy=${location.accuracyMeters}, ageMs=${location.ageMillis}"
            )
        }
}

private fun List<AirQualityStation>.nearestStationTo(point: GeoPoint): AirQualityStation? {
    return minByOrNull { station ->
        point.approximateDistanceTo(GeoPoint(station.latitude, station.longitude))
    }
}

private fun buildLoopWaypoints(
    center: GeoPoint,
    start: GeoPoint,
    targetDistanceMeters: Int? = null,
    radiusScale: Double = 1.0,
    waypointCount: Int = 1
): List<GeoPoint> {
    val latitudeScale = 111_000.0
    val longitudeScale = latitudeScale * kotlin.math.cos(Math.toRadians(center.latitude))
    val startNorthMeters = (start.latitude - center.latitude) * latitudeScale
    val startEastMeters = (start.longitude - center.longitude) * longitudeScale
    val startDistance = kotlin.math.sqrt(
        startNorthMeters * startNorthMeters + startEastMeters * startEastMeters
    )
    val requestedRadius = targetDistanceMeters
        ?.takeIf { it >= 500 }
        ?.let { it / LOOP_ROUTE_DISTANCE_EXPANSION_FACTOR / (2.0 * Math.PI) }
    val radiusMeters = ((requestedRadius ?: startDistance) * radiusScale).coerceIn(180.0, 850.0)

    val unitNorth = if (startDistance >= 50.0) startNorthMeters / startDistance else -1.0
    val unitEast = if (startDistance >= 50.0) startEastMeters / startDistance else 0.0
    val sideNorth = -unitEast
    val sideEast = unitNorth

    val candidates = listOf(
        center.offsetByMeters(sideNorth * radiusMeters, sideEast * radiusMeters),
        center.offsetByMeters(-unitNorth * radiusMeters, -unitEast * radiusMeters),
        center.offsetByMeters(-sideNorth * radiusMeters, -sideEast * radiusMeters)
    )
    return candidates.take(waypointCount.coerceIn(1, candidates.size))
}

private fun buildDistanceAwareLoopRoutes(
    repository: TmapPedestrianRouteRepository,
    startPoint: GeoPoint,
    center: GeoPoint,
    targetDistanceMeters: Int?
): List<RouteCandidate> {
    val waypointCounts = when {
        targetDistanceMeters == null -> listOf(1)
        targetDistanceMeters <= 1_800 -> listOf(1, 2)
        targetDistanceMeters <= 4_000 -> listOf(2, 1, 3)
        else -> listOf(3, 2)
    }
    val scales = if (targetDistanceMeters == null) {
        listOf(0.55, 0.7)
    } else {
        listOf(0.58, 0.72, 0.46, 0.88)
    }
    val attempts = scales.flatMap { scale ->
        waypointCounts.map { waypointCount ->
            val loopWaypoints = buildLoopWaypoints(
                center = center,
                start = startPoint,
                targetDistanceMeters = targetDistanceMeters,
                radiusScale = scale,
                waypointCount = waypointCount
            )
            repository.getRecommendedRoutes(
                startPlace = startPoint.toTmapPlace("출발"),
                waypointPlaces = loopWaypoints.mapIndexed { index, point ->
                    point.toTmapPlace(generatedWaypointName(index, loopWaypoints.size))
                },
                destinationPlace = startPoint.toTmapPlace("도착")
            )
        }
    }.filter { it.isNotEmpty() }

    if (attempts.isEmpty()) return emptyList()
    if (targetDistanceMeters == null) return attempts.first()

    return attempts.minBy { routes ->
        kotlin.math.abs(routes.first().distanceMeters - targetDistanceMeters)
    }
}

private fun buildCourseAwareRoutes(
    repository: TmapPedestrianRouteRepository,
    courseSelection: AiWalkingCourseSelection,
    currentLocation: GeoPoint,
    targetDistanceMeters: Int?,
    requestText: String
): List<RouteCandidate> {
    val course = courseSelection.course
    val startPoint = if (courseSelection.explicitPlaceRequested) {
        course.entryPoint
    } else {
        currentLocation
    }
    val catalogRoutes = buildCatalogCourseRoutes(
        course = course,
        startPoint = startPoint,
        targetDistanceMeters = targetDistanceMeters,
        preferFullLoop = requestText.prefersFullLoopCourse()
    )

    val waypointCandidates = buildCourseWaypointCandidates(
        course = course,
        startPoint = startPoint,
        targetDistanceMeters = targetDistanceMeters,
        requestText = requestText
    )
    val attempts = waypointCandidates.map { waypoints ->
        repository.getRecommendedRoutes(
            startPlace = startPoint.toTmapPlace("출발"),
            waypointPlaces = waypoints.mapIndexed { index, point ->
                point.toTmapPlace(generatedWaypointName(index, waypoints.size))
            },
            destinationPlace = startPoint.toTmapPlace("도착")
        )
    }.filter { it.isNotEmpty() }

    if (attempts.isEmpty()) return catalogRoutes
    val selected = if (targetDistanceMeters == null) {
        if (requestText.prefersFullLoopCourse()) {
            attempts.minBy { routes -> routes.first().distanceMeters }
        } else {
            attempts.first()
        }
    } else {
        attempts.minBy { routes ->
            val distance = routes.first().distanceMeters
            val overshootPenalty = if (distance > targetDistanceMeters * 1.35) {
                (distance - targetDistanceMeters * 1.35).toInt() * 2
            } else {
                0
            }
            kotlin.math.abs(distance - targetDistanceMeters) + overshootPenalty
        }
    }

    val routeWithLine = selected.firstOrNull { route -> route.coordinates.size >= 2 }
        ?: selected.firstOrNull()

    if (routeWithLine?.coordinates?.size ?: 0 >= 2) {
        return selected
    }

    return catalogRoutes.ifEmpty { selected }
}

private fun buildCourseWaypointCandidates(
    course: AiWalkingCourse,
    startPoint: GeoPoint,
    targetDistanceMeters: Int?,
    requestText: String
): List<List<GeoPoint>> {
    val full = course.waypoints
    if (full.isEmpty()) {
        val waypointCounts = if (targetDistanceMeters != null || requestText.prefersMultipleWaypoints()) {
            listOf(1, 2, 3)
        } else {
            listOf(1)
        }
        return waypointCounts.map { waypointCount ->
            buildLoopWaypoints(course.center, startPoint, targetDistanceMeters, waypointCount = waypointCount)
        }.filter { it.isNotEmpty() }.distinct()
    }

    return when (course.shape) {
        AiCourseShape.LakeLoop,
        AiCourseShape.ParkLoop -> {
            val clockwise = full.rotatedFromClosestTo(startPoint)
            val counterClockwise = full.asReversed().rotatedFromClosestTo(startPoint)

            if (requestText.prefersFullLoopCourse() || targetDistanceMeters == null) {
                (
                    clockwise.minimalLoopWaypointCandidates() +
                        counterClockwise.minimalLoopWaypointCandidates() +
                        listOf(clockwise, counterClockwise)
                    )
                    .filter { it.isNotEmpty() }
                    .distinct()
            } else if (targetDistanceMeters <= 3_500) {
                (
                    clockwise.progressiveWaypointCandidates(maxCount = 4) +
                        counterClockwise.progressiveWaypointCandidates(maxCount = 4)
                    ).filter { it.isNotEmpty() }.distinct()
            } else {
                (
                    clockwise.progressiveWaypointCandidates(maxCount = full.size) +
                        counterClockwise.progressiveWaypointCandidates(maxCount = full.size)
                    ).filter { it.isNotEmpty() }.distinct()
            }
        }
        AiCourseShape.RiverOutAndBack -> {
            val ordered = full.rotatedFromClosestTo(startPoint)
            val reversed = full.asReversed().rotatedFromClosestTo(startPoint)
            val first = ordered.take(1)
            val medium = ordered.take(2)
            val all = ordered

            if (targetDistanceMeters != null && targetDistanceMeters <= 3_500) {
                listOf(first, reversed.take(1), medium, reversed.take(2), all)
                    .filter { it.isNotEmpty() }
                    .distinct()
            } else if (targetDistanceMeters != null || requestText.prefersMultipleWaypoints()) {
                listOf(all, reversed.take(3), medium, reversed.take(2), first, reversed.take(1))
                    .filter { it.isNotEmpty() }
                    .distinct()
            } else {
                listOf(first, reversed.take(1)).filter { it.isNotEmpty() }.distinct()
            }
        }
    }
}

private fun List<GeoPoint>.progressiveWaypointCandidates(maxCount: Int): List<List<GeoPoint>> {
    val cappedCount = maxCount.coerceIn(1, size)
    return (1..cappedCount).map { count -> take(count) }
}

private fun List<GeoPoint>.minimalLoopWaypointCandidates(): List<List<GeoPoint>> {
    if (isEmpty()) return emptyList()
    return listOf(2, 3, 4)
        .map { count -> sampleLoopWaypoints(count) }
        .filter { it.isNotEmpty() }
}

private fun List<GeoPoint>.sampleLoopWaypoints(count: Int): List<GeoPoint> {
    if (size <= count) return this
    return (1..count).map { step ->
        val index = (step * size / (count + 1)).coerceIn(0, lastIndex)
        this[index]
    }.distinct()
}

private fun buildCatalogCourseRoutes(
    course: AiWalkingCourse,
    startPoint: GeoPoint?,
    targetDistanceMeters: Int?,
    preferFullLoop: Boolean
): List<RouteCandidate> {
    val routeCoordinates = buildCatalogCourseCoordinateCandidates(course, startPoint)
        .filter { it.size >= 3 }
        .let { candidates ->
            if (preferFullLoop) {
                candidates.firstOrNull()
            } else if (targetDistanceMeters == null) {
                candidates.minByOrNull { points ->
                    kotlin.math.abs(points.totalDistanceMeters() - DEFAULT_AI_WALK_DISTANCE_METERS)
                }
            } else {
                candidates.minByOrNull { points ->
                    kotlin.math.abs(points.totalDistanceMeters() - targetDistanceMeters)
                }
            }
        } ?: return emptyList()
    val distanceMeters = routeCoordinates.totalDistanceMeters()

    return listOf(
        RouteCandidate(
            id = "ai-catalog-${course.id}",
            title = course.name,
            distanceMeters = distanceMeters,
            durationMinutes = (distanceMeters / 67.0).toInt().coerceAtLeast(1),
            airScore = 84,
            exposureSummary = "${course.name} 주변 산책 지형을 우선 반영한 코스입니다.",
            highlightLabel = "장소 우선",
            routeColorArgb = 0xFF2E7D5B,
            coordinates = listOf(course.center)
        )
    )
}

private fun buildCatalogCourseCoordinateCandidates(
    course: AiWalkingCourse,
    startPoint: GeoPoint?
): List<List<GeoPoint>> {
    val fullLoop = listOf(course.entryPoint) + course.waypoints + course.entryPoint
    if (course.waypoints.isEmpty()) return emptyList()

    val candidates = when (course.shape) {
        AiCourseShape.LakeLoop,
        AiCourseShape.ParkLoop -> {
            val outAndBacks = course.waypoints.indices.map { index ->
                val outbound = course.waypoints.take(index + 1)
                listOf(course.entryPoint) + outbound + outbound.dropLast(1).asReversed() + course.entryPoint
            }
            listOf(fullLoop) + outAndBacks
        }
        AiCourseShape.RiverOutAndBack -> {
            val firstTurn = listOf(course.entryPoint, course.waypoints.first(), course.entryPoint)
            val mediumTurn = listOf(course.entryPoint) + course.waypoints.take(2) + course.entryPoint
            val fullTurn = fullLoop
            listOf(fullTurn, mediumTurn, firstTurn)
        }
    }
    return candidates.map { route -> route.anchoredAt(startPoint) }
}

private fun List<GeoPoint>.totalDistanceMeters(): Int {
    return zipWithNext()
        .sumOf { (from, to) -> from.approximateDistanceTo(to).toInt() }
}

private fun List<GeoPoint>.rotatedFromClosestTo(point: GeoPoint): List<GeoPoint> {
    if (isEmpty()) return this
    val closestIndex = indices.minBy { index -> this[index].approximateDistanceTo(point) }
    return drop(closestIndex) + take(closestIndex)
}

private fun List<GeoPoint>.anchoredAt(startPoint: GeoPoint?): List<GeoPoint> {
    if (startPoint == null || size < 2) return this

    val openRoute = if (first().approximateDistanceTo(last()) < 10.0) dropLast(1) else this
    if (openRoute.isEmpty()) return listOf(startPoint)

    val closestIndex = openRoute.indices.minBy { index ->
        openRoute[index].approximateDistanceTo(startPoint)
    }
    val rotatedLoop = openRoute.drop(closestIndex) + openRoute.take(closestIndex) + openRoute[closestIndex]

    return (listOf(startPoint) + rotatedLoop + startPoint)
        .withoutConsecutiveDuplicates()
}

private fun List<GeoPoint>.withoutConsecutiveDuplicates(): List<GeoPoint> {
    return fold(emptyList()) { points, point ->
        if (points.lastOrNull()?.approximateDistanceTo(point) != null &&
            points.last().approximateDistanceTo(point) < 3.0
        ) {
            points
        } else {
            points + point
        }
    }
}

private fun String.extractRequestedDistanceMeters(): Int? {
    val kmMatch = Regex("""(\d+(?:\.\d+)?)\s*(?:km|킬로|키로|킬로미터)""", RegexOption.IGNORE_CASE)
        .find(this)
    if (kmMatch != null) {
        return (kmMatch.groupValues[1].toDoubleOrNull()?.times(1000))?.toInt()
    }

    val meterMatch = Regex("""(\d+(?:\.\d+)?)\s*(?:m|미터)""", RegexOption.IGNORE_CASE)
        .find(this)
    return meterMatch?.groupValues?.getOrNull(1)?.toDoubleOrNull()?.toInt()
}

private fun String.isRouteGenerationRequest(): Boolean {
    return AiRequestIntentClassifier.isRouteGenerationRequest(this)
}

private fun String.prefersFullLoopCourse(): Boolean {
    val normalized = lowercase().replace(" ", "")
    return listOf("한바퀴", "일주", "둘레", "돈", "돌아", "도는").any { normalized.contains(it) }
}

private fun String.prefersMultipleWaypoints(): Boolean {
    val normalized = lowercase().replace(" ", "")
    return prefersFullLoopCourse() || listOf("경유", "왕복", "반환", "찍고", "들렀").any { normalized.contains(it) }
}

private fun AiRouteShapeHint.toRouteSearchText(): String {
    return when (this) {
        AiRouteShapeHint.LakeLoop -> "호수 한바퀴 일주"
        AiRouteShapeHint.RiverOutAndBack -> "하천 강변 따라 왕복"
        AiRouteShapeHint.Loop -> "한바퀴 순환"
        AiRouteShapeHint.PointToPoint,
        AiRouteShapeHint.Unknown -> ""
    }
}

private fun generatedWaypointName(index: Int, totalCount: Int): String {
    return if (totalCount <= 1) {
        "산책 반환점"
    } else {
        "산책 지점 ${index + 1}"
    }
}

private fun buildAiRouteAnswer(
    courseSelection: AiWalkingCourseSelection?,
    targetDistanceMeters: Int?,
    selected: RouteCandidate,
    currentAirQuality: CurrentAirQualityState
): String {
    val place = courseSelection?.course?.name ?: "현재 위치 주변"
    val targetText = targetDistanceMeters?.let { "요청 ${formatDistance(it)}, " }.orEmpty()
    val airText = currentAirQuality.reading?.let { reading ->
        val pm10 = reading.pm10?.toString() ?: "--"
        val pm25 = reading.pm25?.toString() ?: "--"
        " 현재 PM10 $pm10, PM2.5 $pm25 기준입니다."
    }.orEmpty()
    val gapNotice = buildDistanceGapNotice(targetDistanceMeters, selected.distanceMeters)
    if (selected.coordinates.size < 2) {
        return "$place 기준으로 ${targetText}약 ${formatDistance(selected.distanceMeters)} 산책 후보를 찾았습니다. 정확한 보행 선형 데이터가 없어 지도에는 장소만 표시합니다.$airText"
    }

    val routeBasis = if (selected.id.startsWith("ai-catalog-")) "산책 코스" else "실제 보행 경로"
    return "$place 기준으로 ${targetText}$routeBasis 후보 ${formatDistance(selected.distanceMeters)}를 찾았습니다.$gapNotice$airText"
}

private fun buildDistanceGapNotice(targetDistanceMeters: Int?, actualDistanceMeters: Int): String {
    val target = targetDistanceMeters ?: return " 지도에서 선형을 확인해 주세요."
    val gap = kotlin.math.abs(actualDistanceMeters - target)
    return when {
        actualDistanceMeters > target * 1.35 -> {
            " 요청보다 길게 계산됐습니다. 주변 보행로 데이터 한계로 실제 산책 전 지도를 확인해 주세요."
        }
        actualDistanceMeters < target * 0.65 -> {
            " 요청보다 짧게 계산됐습니다. 같은 코스를 한 번 더 돌거나 경유지를 추가하면 목표 거리에 가까워집니다."
        }
        gap > target * 0.25 -> {
            " 요청 거리와 조금 차이가 있으니 실제 산책 전 지도를 확인해 주세요."
        }
        else -> {
            " 요청 거리와 가까운 후보입니다."
        }
    }
}

private fun GeoPoint.offsetByMeters(
    northMeters: Double,
    eastMeters: Double
): GeoPoint {
    val latitudeScale = 111_000.0
    val longitudeScale = latitudeScale * kotlin.math.cos(Math.toRadians(latitude))
    return GeoPoint(
        latitude = latitude + northMeters / latitudeScale,
        longitude = longitude + eastMeters / longitudeScale
    )
}

private fun GeoPoint.approximateDistanceTo(other: GeoPoint): Double {
    val latitudeScale = 111_000.0
    val longitudeScale = latitudeScale * kotlin.math.cos(Math.toRadians((latitude + other.latitude) / 2.0))
    val latitudeDistance = (latitude - other.latitude) * latitudeScale
    val longitudeDistance = (longitude - other.longitude) * longitudeScale

    return kotlin.math.sqrt(latitudeDistance * latitudeDistance + longitudeDistance * longitudeDistance)
}
