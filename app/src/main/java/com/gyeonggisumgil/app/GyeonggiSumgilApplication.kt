package com.gyeonggisumgil.app

import android.app.Application
import android.util.Log
import com.kakao.vectormap.KakaoMapSdk

class GyeonggiSumgilApplication : Application() {
    internal var mapSdkStartup: MapSdkStartup = MapSdkStartup.MissingKey
        private set

    override fun onCreate() {
        super.onCreate()
        mapSdkStartup = initializeMapSdk(BuildConfig.KAKAO_NATIVE_APP_KEY.isNotBlank()) {
            KakaoMapSdk.init(this, BuildConfig.KAKAO_NATIVE_APP_KEY)
        }
        (mapSdkStartup as? MapSdkStartup.Unavailable)?.let {
            Log.w(TAG, "Kakao map SDK could not be loaded", it.cause)
        }
        Log.d(TAG, "Gyeonggi Sumgil app started")
    }

    private companion object {
        const val TAG = "GyeonggiSumgil"
    }
}
