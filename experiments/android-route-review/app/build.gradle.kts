import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val sourceProperties = Properties().apply {
    rootProject.file("../../local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
}
val nativeKey = System.getenv("KAKAO_NATIVE_APP_KEY")
    ?: sourceProperties.getProperty("KAKAO_NATIVE_APP_KEY", "")
val escapedNativeKey = nativeKey.replace("\\", "\\\\").replace("\"", "\\\"")

android {
    namespace = "com.gyeonggisumgil.review"
    compileSdk = 34
    defaultConfig {
        applicationId = "com.gyeonggisumgil.review"
        minSdk = 28
        targetSdk = 34
        versionCode = 1
        versionName = "0.1-review"
        buildConfigField("String", "KAKAO_NATIVE_APP_KEY", "\"$escapedNativeKey\"")
    }
    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    // The harness has no production server and must not produce a release app.
    androidComponents.beforeVariants(androidComponents.selector().withBuildType("release")) { it.enable = false }
}
dependencies {
    implementation("com.kakao.maps.open:android:2.15.2")
}
