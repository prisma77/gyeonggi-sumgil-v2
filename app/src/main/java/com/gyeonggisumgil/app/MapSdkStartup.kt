package com.gyeonggisumgil.app

internal sealed class MapSdkStartup {
    object Ready : MapSdkStartup()
    object MissingKey : MapSdkStartup()
    class Unavailable(val cause: LinkageError) : MapSdkStartup()
}

internal fun initializeMapSdk(hasKey: Boolean, initialize: () -> Unit): MapSdkStartup {
    if (!hasKey) return MapSdkStartup.MissingKey
    return try {
        initialize()
        MapSdkStartup.Ready
    } catch (error: LinkageError) {
        MapSdkStartup.Unavailable(error)
    }
}
