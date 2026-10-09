package com.gyeonggisumgil.app.data.places

import com.gyeonggisumgil.app.domain.model.GeoPoint

data class SearchLocation(val point: GeoPoint, val accuracyMeters: Float, val ageMillis: Long) {
    fun usable(): Boolean = point.latitude.isFinite() && point.latitude in -90.0..90.0 &&
        point.longitude.isFinite() && point.longitude in -180.0..180.0 &&
        accuracyMeters.isFinite() && accuracyMeters in 0f..150f && ageMillis in 0L..120_000L
}

data class PlaceCandidate(val id: String, val name: String, val address: String,
                          val category: String, val point: GeoPoint, val distanceMeters: Double?)

data class PlaceSearchResult(val candidates: List<PlaceCandidate>, val locationUsed: Boolean,
                             val truncated: Boolean, val queriedAt: String)

interface PlaceSearchGateway {
    fun search(query: String, location: SearchLocation?): PlaceSearchResult
}

/** An unavailable location never becomes a station, trail centre or invented default. */
fun searchLocationFor(query: String, location: SearchLocation?): SearchLocation? {
    val usable = location?.takeIf { it.usable() }
    require(query.isNotBlank() || usable != null) { "현재 위치를 확인하거나 장소·지역을 입력해 주세요." }
    return usable
}
