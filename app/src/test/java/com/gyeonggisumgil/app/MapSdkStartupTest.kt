package com.gyeonggisumgil.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
import org.junit.Test

class MapSdkStartupTest {
    @Test
    fun missingKeyDoesNotLoadNativeLibrary() {
        var initialized = false
        val result = initializeMapSdk(false) { initialized = true }
        assertSame(MapSdkStartup.MissingKey, result)
        assertFalse(initialized)
    }

    @Test
    fun successfulInitializationEnablesMap() {
        assertSame(MapSdkStartup.Ready, initializeMapSdk(true) {})
    }

    @Test
    fun missingNativeLibraryPreservesFailureWithoutStoppingStartup() {
        val error = UnsatisfiedLinkError("libK3fAndroid.so not found")
        val result = initializeMapSdk(true) { throw error }
        assertSame(error, (result as MapSdkStartup.Unavailable).cause)
    }

    @Test(expected = IllegalStateException::class)
    fun unrelatedProgrammingErrorsAreNotHidden() {
        initializeMapSdk(true) { throw IllegalStateException("Unexpected initialization failure") }
    }
}
