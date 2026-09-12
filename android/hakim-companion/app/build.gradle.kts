plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "org.hakim.omega.companion"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.hakim.omega.companion"
        minSdk = 26
        targetSdk = 35
        versionCode = 7
        versionName = "0.4.2-native-local-adb-bootstrap"
    }
    buildTypes { release { isMinifyEnabled = false } }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("com.github.MuntashirAkon:libadb-android:3.1.1")
    implementation("org.conscrypt:conscrypt-android:2.5.3")
}
