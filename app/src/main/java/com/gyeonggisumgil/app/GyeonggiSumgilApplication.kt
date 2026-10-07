package com.gyeonggisumgil.app

import android.app.Application
import android.util.Log
import com.kakao.vectormap.KakaoMapSdk

class GyeonggiSumgilApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        if (BuildConfig.KAKAO_NATIVE_APP_KEY.isNotBlank()) {
            KakaoMapSdk.init(this, BuildConfig.KAKAO_NATIVE_APP_KEY)
        }
        Log.d(TAG, "Gyeonggi Sumgil app started")
    }

    private companion object {
        const val TAG = "GyeonggiSumgil"
    }
}
