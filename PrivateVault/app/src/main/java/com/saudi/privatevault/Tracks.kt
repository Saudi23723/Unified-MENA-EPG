package com.saudi.privatevault

import android.content.Context
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** A recorded flight track, exported for Google Earth (3D, KML) or any flight app (GPX). */
object Tracks {
    class Point(val time: Long, val lat: Double, val lon: Double, val altFt: Double)

    fun read(ctx: Context, path: String): List<Point> = try {
        File(ctx.filesDir, path).readLines().drop(1).mapNotNull { l ->
            val c = l.split(',')
            if (c.size < 4) null else Point(c[0].toLong(), c[1].toDouble(), c[2].toDouble(), c[3].toDouble())
        }
    } catch (e: Exception) {
        emptyList()
    }

    private val iso = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }

    fun gpx(name: String, pts: List<Point>): String = buildString {
        append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<gpx version=\"1.1\" creator=\"SSEFB\" xmlns=\"http://www.topografix.com/GPX/1/1\">\n")
        append("<trk><name>").append(name).append("</name><trkseg>\n")
        for (p in pts) append("<trkpt lat=\"%.6f\" lon=\"%.6f\"><ele>%.1f</ele><time>%s</time></trkpt>\n".format(Locale.US, p.lat, p.lon, p.altFt / 3.28084, iso.format(Date(p.time))))
        append("</trkseg></trk>\n</gpx>\n")
    }

    /** The flight as a 3D line hanging from the sky to the ground, to fly again in Google Earth. */
    fun kml(name: String, pts: List<Point>): String = buildString {
        append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<kml xmlns=\"http://www.opengis.net/kml/2.2\" xmlns:gx=\"http://www.google.com/kml/ext/2.2\"><Document><name>").append(name).append("</name>\n")
        append("<Style id=\"f\"><LineStyle><color>ffff40e0</color><width>4</width></LineStyle><PolyStyle><color>40ff40e0</color></PolyStyle></Style>\n")
        append("<Placemark><name>").append(name).append("</name><styleUrl>#f</styleUrl><gx:Track><altitudeMode>absolute</altitudeMode><extrude>1</extrude>\n")
        for (p in pts) append("<when>").append(iso.format(Date(p.time))).append("</when>\n")
        for (p in pts) append("<gx:coord>%.6f %.6f %.1f</gx:coord>\n".format(Locale.US, p.lon, p.lat, p.altFt / 3.28084))
        append("</gx:Track></Placemark></Document></kml>\n")
    }
}
