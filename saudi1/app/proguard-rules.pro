-dontwarn okhttp3.**
-dontwarn okio.**
-keep class com.saudi1.tv.** { *; }

# FFmpeg sound decoders are found by name at run time (DefaultRenderersFactory)
-keep class androidx.media3.decoder.ffmpeg.** { *; }

# WireGuard (native code calls back into these)
-keep class com.wireguard.** { *; }
