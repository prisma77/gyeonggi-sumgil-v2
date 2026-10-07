import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) {
        file.inputStream().use(::load)
    }
}

fun String.asBuildConfigString(): String {
    return replace("\\", "\\\\").replace("\"", "\\\"")
}

fun Properties.unnamedPublicDataKey(): String? {
    val knownKeys = setOf(
        "sdk.dir",
        "KAKAO_NATIVE_APP_KEY",
        "KAKAO_REST_API_KEY",
        "NAVER_CLIENT_ID",
        "TMAP_APP_KEY",
        "AIRKOREA_SERVICE_KEY",
        "GEMINI_API_KEY",
        "KMA_SERVICE_KEY",
        "WEATHER_SERVICE_KEY",
        "VILAGE_FCST_SERVICE_KEY"
    )
    return stringPropertyNames()
        .firstOrNull { key -> key !in knownKeys && key.length > 40 && !key.contains(".") }
        ?.let { key ->
            val value = getProperty(key).orEmpty()
            if (value.isBlank()) key else "$key=$value"
        }
}

android {
    namespace = "com.gyeonggisumgil.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.gyeonggisumgil.app"
        minSdk = 28
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"

        val tmapAppKey =
            (project.findProperty("TMAP_APP_KEY") as? String)
                ?: localProperties.getProperty("TMAP_APP_KEY")
                ?: ""
        val naverClientId =
            (project.findProperty("NAVER_CLIENT_ID") as? String)
                ?: localProperties.getProperty("NAVER_CLIENT_ID")
                ?: ""
        val kakaoNativeKey =
            (project.findProperty("KAKAO_NATIVE_APP_KEY") as? String)
                ?: localProperties.getProperty("KAKAO_NATIVE_APP_KEY")
                ?: ""
        val airKoreaServiceKey =
            (project.findProperty("AIRKOREA_SERVICE_KEY") as? String)
                ?: localProperties.getProperty("AIRKOREA_SERVICE_KEY")
                ?: ""
        val geminiApiKey =
            (project.findProperty("GEMINI_API_KEY") as? String)
                ?: localProperties.getProperty("GEMINI_API_KEY")
                ?: ""
        val kmaServiceKey =
            (project.findProperty("KMA_SERVICE_KEY") as? String)
                ?: localProperties.getProperty("KMA_SERVICE_KEY")
                ?: localProperties.getProperty("WEATHER_SERVICE_KEY")
                ?: localProperties.getProperty("VILAGE_FCST_SERVICE_KEY")
                ?: localProperties.unnamedPublicDataKey()
                ?: ""
        buildConfigField("String", "TMAP_APP_KEY", "\"${tmapAppKey.asBuildConfigString()}\"")
        buildConfigField("String", "NAVER_CLIENT_ID", "\"${naverClientId.asBuildConfigString()}\"")
        buildConfigField("String", "KAKAO_NATIVE_APP_KEY", "\"${kakaoNativeKey.asBuildConfigString()}\"")
        buildConfigField("String", "AIRKOREA_SERVICE_KEY", "\"${airKoreaServiceKey.asBuildConfigString()}\"")
        buildConfigField("String", "GEMINI_API_KEY", "\"${geminiApiKey.asBuildConfigString()}\"")
        buildConfigField("String", "KMA_SERVICE_KEY", "\"${kmaServiceKey.asBuildConfigString()}\"")
        manifestPlaceholders["NAVER_CLIENT_ID"] = naverClientId
    }

    buildFeatures {
        buildConfig = true
        compose = true
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.3"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.activity:activity-compose:1.8.1")
    implementation("androidx.compose.ui:ui:1.5.4")
    implementation("androidx.compose.ui:ui-tooling-preview:1.5.4")
    implementation("androidx.compose.material3:material3:1.1.2")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.code.gson:gson:2.10.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    implementation("com.naver.maps:map-sdk:3.23.2")
    implementation("com.kakao.maps.open:android:2.15.2")

    testImplementation("junit:junit:4.13.2")
    debugImplementation("androidx.compose.ui:ui-tooling:1.5.4")
}
