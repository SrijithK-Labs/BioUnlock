import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val signingProperties = Properties()
val signingPropertiesFile = rootProject.file("key.properties")
if (signingPropertiesFile.isFile) {
    signingPropertiesFile.inputStream().use(signingProperties::load)
}

// WebAuthn relying-party host baked into the App Links filter and the Digital
// Asset Links statement. Provide the real domain locally, either with
// `-PrpHost=unlock.example.com` or with `rpHost=unlock.example.com` in the
// gitignored key.properties. The default is a reserved example domain so no
// real deployment is ever committed to the repository.
val rpHost: String = providers.gradleProperty("rpHost").orNull
    ?: signingProperties.getProperty("rpHost")
    ?: "biounlock.example.com"

val requiredSigningProperties = listOf("storeFile", "storePassword", "keyAlias", "keyPassword")
val missingSigningProperties = requiredSigningProperties.filter {
    signingProperties.getProperty(it).isNullOrBlank()
}
val releaseTaskRequested = gradle.startParameter.taskNames.any {
    it.substringAfterLast(":").contains("release", ignoreCase = true)
}
if (releaseTaskRequested && missingSigningProperties.isNotEmpty()) {
    throw GradleException(
        "Release signing is not configured. Add android/key.properties with: " +
            missingSigningProperties.joinToString(", ")
    )
}

android {
    namespace = "com.biounlock.biounlock_mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        resValues = true
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.biounlock.biounlock_mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = maxOf(flutter.minSdkVersion, 23)
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName

        manifestPlaceholders["rpHost"] = rpHost
        resValue(
            "string",
            "asset_statements",
            "[{\"include\": \"https://$rpHost/.well-known/assetlinks.json\"}]",
        )
    }

    signingConfigs {
        create("release") {
            if (missingSigningProperties.isEmpty()) {
                keyAlias = signingProperties.getProperty("keyAlias")
                keyPassword = signingProperties.getProperty("keyPassword")
                storeFile = rootProject.file(signingProperties.getProperty("storeFile"))
                storePassword = signingProperties.getProperty("storePassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
