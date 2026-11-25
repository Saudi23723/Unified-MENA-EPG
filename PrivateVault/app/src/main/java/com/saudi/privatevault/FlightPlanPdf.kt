package com.saudi.privatevault

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import androidx.core.content.FileProvider
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * The flight plan as one page to carry or send: a summary box (height, corridor, the highest ground and
 * the clearance over it, distance, time, fuel), the ground along the route with the planned height
 * drawn across it, and the nav log as Jeppesen lays it out — leg, phase, MORA, distance, true and
 * magnetic course, wind correction, magnetic heading, ground speed, time and fuel. Written with the
 * phone's own PDF writer, so it needs no printer and can be shared straight away.
 */
object FlightPlanPdf {

    /** Builds the page and returns the file. The ground is sampled here, so call it off the main thread. */
    fun build(act: Activity, plan: FlightPlan, r: Navlog.Result, aircraftName: String, corridorNm: Int = 4): File {
        val pts = plan.points.toList()
        // The ground along the route, every mile, the highest within the corridor either side.
        val ground = ArrayList<Pair<Double, Float>>()
        var run = 0.0
        for (i in 1 until pts.size) {
            val a = pts[i - 1]; val b = pts[i]
            val len = Nav.distanceNm(a.lat, a.lon, b.lat, b.lon)
            val crs = Nav.bearingTrue(a.lat, a.lon, b.lat, b.lon)
            var s = 0.0
            while (s <= len) {
                val g = Nav.destination(a.lat, a.lon, crs, s)
                var hi = 0f
                for (off in doubleArrayOf(0.0, -corridorNm.toDouble(), corridorNm.toDouble())) {
                    val p = if (off == 0.0) g else Nav.destination(g.latitude, g.longitude, crs + 90.0, off)
                    val h = try { Srtm.best(p.latitude, p.longitude) } catch (e: Throwable) { 0f }
                    if (h > hi) hi = h
                }
                ground.add((run + s) to hi)
                s += 1.0
            }
            run += len
        }

        val pdf = PdfDocument()
        val page = pdf.startPage(PdfDocument.PageInfo.Builder(595, 842, 1).create())
        val c = page.canvas
        val title = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; textSize = 15f; typeface = Typeface.DEFAULT_BOLD }
        val sub = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.DKGRAY; textSize = 9.5f }
        val box = Paint().apply { color = Color.rgb(232, 238, 247) }
        val cell = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; textSize = 9f }
        val bold = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; textSize = 9f; typeface = Typeface.DEFAULT_BOLD }
        val rule = Paint().apply { color = Color.LTGRAY; strokeWidth = 0.8f }

        val dep = pts.firstOrNull()?.id ?: "DEP"
        val dest = pts.lastOrNull()?.id ?: "DEST"
        val utc = SimpleDateFormat("yyyy-MM-dd HH:mm 'UTC'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }.format(Date())
        c.drawText("FLIGHT PLAN & NAV LOG  $dep → $dest", 36f, 40f, title)
        c.drawText("Made $utc · $aircraftName · TAS ${plan.tas} kt · not an official flight plan", 36f, 55f, sub)

        val maxTrn = ground.maxOfOrNull { it.second }?.toInt() ?: 0
        val clr = plan.altitude - maxTrn
        c.drawRect(36f, 66f, 559f, 112f, box)
        c.drawText("Cruise ${"%,d".format(plan.altitude)} ft MSL", 46f, 84f, bold)
        c.drawText("Corridor ±$corridorNm nm", 205f, 84f, bold)
        c.drawText("Highest ground ${"%,d".format(maxTrn)} ft (clearance ${if (clr >= 0) "+" else ""}${"%,d".format(clr)} ft)", 330f, 84f, bold)
        c.drawText("Distance %.0f nm".format(r.distNm), 46f, 102f, cell)
        c.drawText("Time ${Navlog.hm(r.minutes)}", 205f, 102f, cell)
        c.drawText("Fuel %.1f gal · left at destination %.1f gal".format(r.fuelGal, r.fuelLeftGal), 330f, 102f, cell)

        // The ground and the planned height.
        val l = 46f; val t = 126f; val rr = 549f; val b = 262f
        c.drawRect(l, t, rr, b, Paint().apply { color = Color.DKGRAY; style = Paint.Style.STROKE; strokeWidth = 0.8f })
        if (ground.size > 1) {
            val maxD = ground.last().first.coerceAtLeast(1.0)
            val maxA = maxOf(plan.altitude.toFloat(), maxTrn.toFloat()) + 1500f
            fun x(d: Double) = l + ((d / maxD) * (rr - l)).toFloat()
            fun y(ft: Float) = b - (ft / maxA) * (b - t)
            val path = Path().apply {
                moveTo(l, b)
                for ((d, h) in ground) lineTo(x(d), y(h))
                lineTo(rr, b); close()
            }
            c.drawPath(path, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(141, 110, 99) })
            val cy = y(plan.altitude.toFloat())
            c.drawLine(l, cy, rr, cy, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(216, 27, 96); strokeWidth = 2f })
            c.drawText("${"%,d".format(plan.altitude)} ft", l + 4f, cy - 4f, sub)
            // The waypoints along the bottom.
            var acc = 0.0
            for (i in pts.indices) {
                if (i > 0) acc += Nav.distanceNm(pts[i - 1].lat, pts[i - 1].lon, pts[i].lat, pts[i].lon)
                val px = x(acc)
                c.drawLine(px, b, px, b + 4f, rule)
                c.drawText(pts[i].id, (px - 10f).coerceIn(l, rr - 30f), b + 13f, sub)
            }
        }

        // The log.
        var yy = 292f
        c.drawRect(36f, yy - 13f, 559f, yy + 5f, box)
        val cols = floatArrayOf(40f, 128f, 168f, 214f, 252f, 290f, 328f, 362f, 400f, 440f, 486f)
        val heads = listOf("LEG", "PHASE", "MORA", "DIST", "TC", "MC", "WCA", "MH", "GS", "ETE", "FUEL")
        for ((i, h) in heads.withIndex()) c.drawText(h, cols[i], yy, bold)
        yy += 18f
        for (x in r.rows) {
            if (yy > 810f) break
            val mc = (x.tc - x.variation + 360) % 360
            c.drawText("${x.from.id}→${x.to.id}".take(16), cols[0], yy, bold)
            c.drawText(when (x.phase) { Phase.CLIMB -> "CLB"; Phase.CRUISE -> "CRZ"; Phase.DESCENT -> "DSC" }, cols[1], yy, cell)
            c.drawText(x.moraFt?.let { "%,d".format(it) } ?: "—", cols[2], yy, cell)
            c.drawText("%.1f".format(x.distNm), cols[3], yy, cell)
            c.drawText("%03d°".format(Math.round(x.tc).toInt() % 360), cols[4], yy, cell)
            c.drawText("%03d°".format(Math.round(mc).toInt() % 360), cols[5], yy, cell)
            c.drawText("%+d°".format(Math.round(x.wca).toInt()), cols[6], yy, cell)
            c.drawText("%03d°".format(Math.round(x.mh).toInt() % 360), cols[7], yy, bold)
            c.drawText("${Math.round(x.gs).toInt()} kt", cols[8], yy, cell)
            c.drawText(Navlog.hm(x.minutes), cols[9], yy, cell)
            c.drawText("%.1f g".format(x.fuelGal), cols[10], yy, cell)
            c.drawLine(36f, yy + 5f, 559f, yy + 5f, rule)
            yy += 17f
        }
        yy += 8f
        if (yy < 820f) c.drawText("MORA: highest ground within 4 nm of the leg + 1,000 ft (2,000 ft where it is above 5,000 ft), " +
            "worked out from terrain data, not the charted figure.", 36f, yy, sub)

        pdf.finishPage(page)
        val dir = File(act.cacheDir, "exports").apply { mkdirs() }
        val f = File(dir, "FlightPlan_${dep}_$dest.pdf")
        f.outputStream().use { pdf.writeTo(it) }
        pdf.close()
        return f
    }

    fun share(act: Activity, f: File) {
        val uri = FileProvider.getUriForFile(act, act.packageName + ".files", f)
        act.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
            type = "application/pdf"; putExtra(Intent.EXTRA_STREAM, uri); addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }, "Flight plan PDF"))
    }
}
