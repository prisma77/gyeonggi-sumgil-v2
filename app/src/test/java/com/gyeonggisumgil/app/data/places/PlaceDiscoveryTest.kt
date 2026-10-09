package com.gyeonggisumgil.app.data.places

import com.gyeonggisumgil.app.domain.model.GeoPoint
import org.junit.Assert.*
import org.junit.Test

class PlaceDiscoveryTest {
    private fun location(age: Long = 1000, accuracy: Float = 20f) = SearchLocation(GeoPoint(37.0, 127.0), accuracy, age)

    @Test fun nearbyRequiresAnActualLocation() {
        try { searchLocationFor("", null); fail("Must not use a default location") } catch (_: IllegalArgumentException) { }
    }
    @Test fun staleLocationCannotDriveNearbySearch() {
        try { searchLocationFor("", location(age = 120001)); fail("Stale GPS accepted") } catch (_: IllegalArgumentException) { }
    }
    @Test fun inaccurateLocationCannotDriveNearbySearch() {
        try { searchLocationFor("", location(accuracy = 151f)); fail("Inaccurate GPS accepted") } catch (_: IllegalArgumentException) { }
    }
    @Test fun namedSearchCanProceedWithoutLocationWithoutReplacingItsName() {
        assertNull(searchLocationFor("부산 중앙공원", null))
        assertNull(searchLocationFor("부산 중앙공원", location(age = 120001)))
    }
    @Test fun nearbyUsesTheSuppliedLocationOnly() {
        val actual = location()
        assertSame(actual, searchLocationFor("", actual))
    }
    @Test fun invalidCoordinatesAndUnknownAccuracyAreRejected() {
        assertFalse(SearchLocation(GeoPoint(91.0, 127.0), 10f, 0).usable())
        assertFalse(location(accuracy = Float.NaN).usable())
        assertFalse(location(age = -1).usable())
    }
}
