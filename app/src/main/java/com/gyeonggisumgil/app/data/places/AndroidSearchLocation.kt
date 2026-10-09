package com.gyeonggisumgil.app.data.places

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.CancellationSignal
import android.os.Looper
import android.os.SystemClock
import androidx.core.content.ContextCompat
import com.gyeonggisumgil.app.domain.model.GeoPoint
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

fun Context.hasSearchLocationPermission(): Boolean = listOf(Manifest.permission.ACCESS_FINE_LOCATION,
    Manifest.permission.ACCESS_COARSE_LOCATION).any {
    ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
}

private fun Location.searchSample(): SearchLocation = SearchLocation(GeoPoint(latitude, longitude),
    if (hasAccuracy()) accuracy else Float.POSITIVE_INFINITY,
    (SystemClock.elapsedRealtimeNanos() - elapsedRealtimeNanos) / 1_000_000)

/** Bounded foreground lookup, never reads unrelated weather/station positions. */
suspend fun Context.findSearchLocation(): SearchLocation? {
    if (!hasSearchLocationPermission()) return null
    val manager = getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return null
    val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        .filter { runCatching { manager.isProviderEnabled(it) }.getOrDefault(false) }
    val cached = providers.mapNotNull {
        try { manager.getLastKnownLocation(it)?.searchSample() } catch (_: SecurityException) { null }
    }
        .filter { it.usable() }.minByOrNull { it.accuracyMeters }
    if (cached != null) return cached
    for (provider in providers) {
        val sample = withTimeoutOrNull(6000) {
            suspendCancellableCoroutine<SearchLocation?> { continuation ->
                try {
                    if (Build.VERSION.SDK_INT >= 30) {
                        val cancellation = CancellationSignal()
                        manager.getCurrentLocation(provider, cancellation, mainExecutor) { location ->
                            if (continuation.isActive) continuation.resume(location?.searchSample())
                        }
                        continuation.invokeOnCancellation { cancellation.cancel() }
                    } else {
                        val listener = object : LocationListener {
                            override fun onLocationChanged(location: Location) {
                                manager.removeUpdates(this)
                                if (continuation.isActive) continuation.resume(location.searchSample())
                            }
                            @Deprecated("Required on Android 28–29")
                            override fun onStatusChanged(provider: String?, status: Int, extras: android.os.Bundle?) = Unit
                            override fun onProviderEnabled(provider: String) = Unit
                            override fun onProviderDisabled(provider: String) = Unit
                        }
                        manager.requestSingleUpdate(provider, listener, Looper.getMainLooper())
                        continuation.invokeOnCancellation { manager.removeUpdates(listener) }
                    }
                } catch (_: SecurityException) {
                    if (continuation.isActive) continuation.resume(null)
                }
            }
        }
        if (sample?.usable() == true) return sample
    }
    return null
}
