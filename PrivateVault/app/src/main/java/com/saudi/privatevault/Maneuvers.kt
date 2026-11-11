package com.saudi.privatevault

import android.graphics.RectF

/**
 * The private pilot's flight maneuvers, written for this app: what each is for, how to fly it in
 * the SportStar MAX (speeds from its POH, Doc. SSM2008AOIUS), what the Private Pilot ACS
 * (FAA-S-ACS-6C) holds you to, the usual mistakes, and a short animation of the maneuver.
 * The procedures follow the FAA Airplane Flying Handbook (FAA-H-8083-3C); your instructor's and
 * your school's procedures come first.
 */
object Maneuvers {
    class M(
        val id: String,
        val group: String,
        val title: String,
        val acs: String,
        val line: String,
        val objective: String,
        val numbers: List<Pair<String, String>>,
        val steps: List<String>,
        val standards: List<Pair<String, String>>,
        val errors: List<String>,
        val tip: String,
        val anim: () -> ManeuverAnim,
    )

    const val G_TKO = "Takeoffs, landings & go-arounds"
    const val G_PERF = "Performance maneuvers"
    const val G_GND = "Ground reference maneuvers"
    const val G_SLOW = "Slow flight & stalls"
    const val G_EMER = "Emergency operations"
    const val G_APT = "Airport operations"
    val GROUPS = listOf(G_APT, G_TKO, G_PERF, G_GND, G_SLOW, G_EMER)

    private fun pk(sec: Float, vararg k: ProfileKeys.Key, setup: ManeuverScene.() -> Unit = {}): ManeuverAnim =
        ProfileKeys(sec, k.toList()).apply {
            scene.setup()
            phases = k.mapNotNull { key -> labels[key]?.let { key.t to it } }
            labels.clear()
        }

    // Labels for profile keys, set by K(…, "label") while a list is built.
    private val labels = HashMap<ProfileKeys.Key, String>()
    private fun K(t: Float, x: Float, y: Float, pitch: Float, ias: Float, flaps: Int = 0, label: String? = null, warn: String? = null, bank: Float = 0f) =
        ProfileKeys.Key(t, x, y, pitch, ias, flaps, warn, bank).also { if (label != null) labels[it] = label }

    val ALL: List<M> by lazy { listOf(
        // ---------------------------------------------------------------- airport operations
        M("pattern", G_APT, "Traffic pattern", "PA.III.B",
            "Takeoff to landing around a left-hand pattern",
            "Fly a standard traffic pattern: enter and leave correctly, keep the right spacing from the runway and from other traffic, hold pattern altitude and speeds, and correct for wind on every leg so the ground track stays a clean rectangle.",
            listOf("Takeoff" to "Flaps 15° · climb 57 KIAS", "Flaps up" to "150 ft AGL", "Climb" to "Vy 65 KIAS", "Downwind" to "TPA (usually 1,000 ft AGL)", "Final" to "60 KIAS · flaps 30–50°", "Crosswind demo" to "16 kt"),
            listOf(
                "Before departure: brief the runway, wind, pattern direction and traffic pattern altitude (TPA) for the field (Chart Supplement).",
                "Upwind: climb straight out on the extended centerline. Flaps up at 150 ft, then Vy 65 KIAS.",
                "Crosswind: start the turn within 300 ft of TPA (and beyond the departure end), crab to keep the leg square.",
                "Downwind: level at TPA about ½–1 NM from the runway. Before-landing checklist. Abeam the touchdown point: power back, flaps 15°.",
                "Base: turn when the touchdown point is about 45° behind the wing. Descend, flaps 30°, crab against the drift.",
                "Final: roll out on the centerline, full flaps as needed, 60 KIAS, stabilized by about 300 ft AGL.",
                "Land, or go around if anything is not right. Announce every leg on the CTAF at a non-towered field.",
            ),
            listOf("Altitude" to "±100 ft", "Airspeed" to "±10 kt", "Ground track" to "Correct for wind; proper spacing", "Communication" to "Correct radio and light-gun procedures"),
            listOf("Downwind too close or too far from the runway", "Not correcting for wind: drifting toward or away on downwind, overshooting final", "Skidding base-to-final turn with rudder (stall-spin risk)", "Losing or gaining altitude on downwind", "Late or rushed checklist"),
            "Pick a ground reference for the abeam point and the base turn at your home field and use the same ones every lap: consistency is what makes landings repeatable.",
        ) {
            GroundTrack(9.5f, 360f, 8f)
                .start(0f, 0f, 0f, 0f, 20f)
                .straight(380f, 0f, 57f, 15, label = "Takeoff roll · flaps 15°")
                .straight(700f, 400f, 65f, label = "Upwind: flaps up at 150 ft · Vy 65")
                .turn(-90f, 320f, 650f, 70f, label = "Crosswind: crab into the wind")
                .straight(300f, 850f, 75f)
                .turn(-90f, 320f, 1000f, 80f)
                .straight(1400f, 1000f, 78f, label = "Downwind at TPA · checklist")
                .turn(-90f, 320f, 650f, 68f, 15, label = "Base: descend · flaps")
                .straight(300f, 450f, 63f, 30)
                .turn(-90f, 320f, 300f, 60f, 50, label = "Final: 60 KIAS · full flaps")
                .straight(360f, 0f, 50f, 50)
                .straight(260f, 0f, 20f, 50, label = "Touchdown · rollout")
                .apply { scene.runway = floatArrayOf(0f, 0f, 0f, 900f); scene.runwayNames = "36" to "18" }
        },

        // ---------------------------------------------------------------- takeoffs & landings
        M("normal_to", G_TKO, "Normal takeoff & climb", "PA.IV.A",
            "Flaps 15°, lift off, climb at Vy",
            "Take off into the wind from a runway of adequate length and climb at the best rate (Vy), keeping the airplane on the centerline and the climb steady.",
            listOf("Flaps" to "15° (takeoff)", "Lift-off" to "≈ 57 KIAS", "Initial climb" to "57 KIAS to 150 ft", "Flaps up" to "150 ft AGL", "Vy" to "65 KIAS (flaps 0°)", "Ground run (POH)" to "620 ft paved · 720 ft grass", "Over 50 ft (POH)" to "1,440 ft paved"),
            listOf(
                "Before-takeoff check complete; flaps 15°; trim set for takeoff; runway and final clear.",
                "Line up on the centerline; full power smoothly; feet on the rudder, not the brakes.",
                "Check engine instruments in the green and the airspeed alive.",
                "Lighten the nosewheel with light back pressure as the speed builds.",
                "Let it fly off at about 57 KIAS; hold that attitude for the initial climb.",
                "At 150 ft AGL retract the flaps, accelerate to Vy 65 KIAS and trim.",
                "Keep the centerline extended: crab as needed. Engine instruments; electric fuel pump off (if installed).",
            ),
            listOf("Lift-off" to "At the recommended airspeed", "Climb" to "Vy +10/−5 kt", "Direction" to "Centerline; correct for wind", "Flaps" to "Retract at a safe altitude"),
            listOf("Forgetting the before-takeoff check or the flaps setting", "Not enough right rudder: drifting left of the centerline", "Pulling the airplane off too early or too steeply", "Chasing the airspeed instead of holding a pitch attitude", "Letting the airplane drift off the extended centerline in a crosswind"),
            "Learn the Vy picture: the nose against the horizon at 65 KIAS. Set it, wait, then trim. Airspeed follows the attitude.",
        ) {
            pk(8.5f,
                K(0f, 0f, 0f, 0f, 0f, 15, "Line up · flaps 15° · full power"),
                K(0.24f, 400f, 0f, 0f, 42f, 15, "Gauges green · airspeed alive"),
                K(0.34f, 560f, 0f, 6f, 52f, 15, "Lighten the nosewheel"),
                K(0.40f, 620f, 3f, 8f, 57f, 15, "Lift off ≈ 57 KIAS"),
                K(0.62f, 1440f, 50f, 9f, 57f, 15, "Over 50 ft at 1,440 ft (POH)"),
                K(0.76f, 2400f, 150f, 9f, 58f, 0, "150 ft: flaps up"),
                K(1f, 4200f, 420f, 8f, 65f, 0, "Climb at Vy 65 KIAS"),
            ) { runway = floatArrayOf(-100f, 3400f); refLine = 150f; refLabel = "150 FT · FLAPS UP" }
        },

        M("xwind_to", G_TKO, "Crosswind takeoff & climb", "PA.IV.A",
            "Ailerons into the wind, then crab on the climb",
            "Take off with a wind across the runway without letting it drift the airplane or lift the upwind wing, then climb on the extended centerline with a crab.",
            listOf("Flaps" to "15°", "Lift-off" to "≈ 57 KIAS — a little firmer", "Climb" to "Vy 65 KIAS", "Max demonstrated crosswind" to "16 kt", "Max tailwind" to "6 kt"),
            listOf(
                "Full aileron into the wind at the start of the roll; rudder to hold the centerline.",
                "As the speed builds and the ailerons bite, ease the aileron off — just enough to keep the wings level.",
                "Hold the airplane on the ground a little longer, then lift off cleanly so it does not skip sideways.",
                "Once airborne, turn slightly into the wind (crab) to track the extended centerline.",
                "Flaps up at 150 ft; climb at Vy, still tracking the centerline.",
            ),
            listOf("Direction" to "Centerline, no drift", "Climb" to "Vy +10/−5 kt", "Wind" to "Proper aileron and rudder for the crosswind"),
            listOf("Releasing the aileron input too soon: the upwind wing lifts", "Lifting off too slowly and drifting sideways with the wheels near the ground", "Not crabbing after lift-off: drifting off the extended centerline"),
            "Say it on the roll: “aileron into the wind… less… less…”. The control wheel ends up almost neutral at lift-off.",
        ) {
            GroundTrack(8.5f, 60f, 12f)
                .start(0f, 0f, 0f, 0f, 20f)
                .straight(420f, 0f, 57f, 15, slip = 1f, label = "Aileron into the wind · rudder straight")
                .straight(500f, 220f, 60f, 15, slip = 0f, label = "Lift off · crab into the wind")
                .straight(900f, 600f, 65f, 0, label = "Track the centerline at Vy")
                .apply { scene.runway = floatArrayOf(0f, 0f, 0f, 900f); scene.runwayNames = "36" to "18" }
        },

        M("short_to", G_TKO, "Short-field takeoff & max-performance climb", "PA.IV.E",
            "Brakes, full power, Vx over the obstacle",
            "Get airborne in the least distance and climb over a 50-ft obstacle at the best angle (Vx), then continue at Vy.",
            listOf("Flaps" to "15°", "Vx" to "54 KIAS (flaps 15°) · 56 KIAS (flaps 0°)", "Vy" to "65 KIAS", "Ground run (POH)" to "620 ft paved", "Over 50 ft (POH)" to "1,440 ft paved · 1,540 ft grass"),
            listOf(
                "Use all the runway: line up at the very beginning.",
                "Hold the brakes, full power, check the engine; then release the brakes.",
                "Keep the attitude for minimum drag; rotate at lift-off speed.",
                "Climb at Vx 54 KIAS (flaps 15°) until the obstacle is cleared.",
                "Then lower the nose to Vy, retract the flaps at 150 ft and continue the climb.",
            ),
            listOf("Climb" to "Vx +10/−5 kt to the obstacle, then Vy +10/−5 kt", "Takeoff point" to "Use the most runway", "Direction" to "Centerline"),
            listOf("Not using all the runway", "Rotating too early: more drag, longer run", "Pitching too steep: speed decays below Vx", "Retracting the flaps too low"),
            "Vx gives altitude per foot of runway; Vy gives altitude per minute. Over the trees, you want Vx.",
        ) {
            pk(9f,
                K(0f, 0f, 0f, 0f, 0f, 15, "Brakes · full power"),
                K(0.08f, 0f, 0f, 0f, 0f, 15, "Release the brakes"),
                K(0.34f, 520f, 0f, 0f, 50f, 15, "Minimum drag attitude"),
                K(0.40f, 620f, 3f, 10f, 54f, 15, "Rotate · lift off"),
                K(0.62f, 1440f, 50f, 12f, 54f, 15, "Vx 54 KIAS over the obstacle"),
                K(0.78f, 2200f, 150f, 10f, 60f, 0, "Clear: Vy · flaps up at 150 ft"),
                K(1f, 3800f, 430f, 9f, 65f, 0, "Climb at Vy 65 KIAS"),
            ) { runway = floatArrayOf(-50f, 1250f); obstacle = floatArrayOf(1350f, 50f) }
        },

        M("soft_to", G_TKO, "Soft-field takeoff & climb", "PA.IV.C",
            "Keep moving, nose up, accelerate in ground effect",
            "Take off from grass, sand or snow: keep the weight off the nosewheel, get airborne at the lowest speed, then accelerate in ground effect before climbing.",
            listOf("Flaps" to "15°", "Elevator" to "Full back to start, then less", "Climb" to "Vx 54 / Vy 65 KIAS", "Ground run (POH, grass)" to "720 ft", "Over 50 ft (POH, grass)" to "1,540 ft"),
            listOf(
                "Do not stop on the soft surface: taxi onto the runway with the elevator back and keep rolling.",
                "Full power smoothly while still moving; keep back pressure to lift the nosewheel early.",
                "Hold the nosewheel just off the surface; the airplane lifts off below the normal speed.",
                "Lower the nose slightly and stay in ground effect while it accelerates.",
                "At Vx/Vy, climb. Flaps up at 150 ft.",
            ),
            listOf("Climb" to "Vx or Vy +10/−5 kt", "Ground effect" to "Remain in it until a safe climb speed", "Direction" to "Centerline"),
            listOf("Stopping on the soft surface", "Letting the nosewheel dig in", "Climbing out of ground effect too soon: settling back", "Over-rotation: tail strike"),
            "The secret is the transition: right after lift-off, ease forward. If you feel nothing, you are about to climb at a speed it can’t hold.",
        ) {
            pk(9f,
                K(0f, -300f, 0f, 3f, 8f, 15, "Keep rolling · elevator back"),
                K(0.2f, 150f, 0f, 7f, 30f, 15, "Nosewheel up early"),
                K(0.36f, 560f, 3f, 8f, 42f, 15, "Lift off at the lowest speed"),
                K(0.55f, 1100f, 6f, 2f, 54f, 15, "Stay in ground effect · accelerate"),
                K(0.68f, 1450f, 40f, 10f, 56f, 15, "Climb at Vx / Vy"),
                K(0.82f, 2300f, 150f, 9f, 60f, 0, "Flaps up at 150 ft"),
                K(1f, 3400f, 330f, 9f, 65f, 0, "Vy 65 KIAS"),
            ) { soft = true; runway = floatArrayOf(-350f, 2600f); refLine = 10f; refLabel = "GROUND EFFECT" }
        },

        M("normal_ldg", G_TKO, "Normal approach & landing", "PA.IV.B",
            "Stabilized at 60 KIAS, flare, mains first",
            "Fly a stabilized approach to a chosen touchdown point and land on the main wheels, slowly, on the centerline, without drift.",
            listOf("Final" to "60 KIAS", "Flaps" to "30° or 50°", "Stall, flaps 50°" to "37 KIAS", "Over 50 ft (POH)" to "1,310 ft paved · 1,250 ft grass", "Landing run (POH)" to "590 ft paved · 520 ft grass", "Tailwind" to "+4.5 % per kt"),
            listOf(
                "On final: flaps as needed, 60 KIAS, trimmed. Pick the aim point and keep it still in the windshield.",
                "Power controls the glidepath, pitch the airspeed; stabilized by 300 ft AGL or go around.",
                "Over the threshold (≈ 10–20 ft): power to idle, begin the round-out by shifting your eyes down the runway.",
                "Flare: keep raising the nose to hold it just off the runway while the speed decays.",
                "Touch down on the main wheels at the slowest speed, nose high.",
                "Lower the nosewheel gently; brakes as necessary. Stay on the centerline.",
            ),
            listOf("Approach speed" to "+10/−5 kt", "Touchdown" to "Within 400 ft beyond the point", "Drift" to "None; axis on the centerline", "Attitude" to "Proper pitch at touchdown"),
            listOf("Unstabilized approach and chasing the glide path", "Flaring too high or too low", "Ballooning: too much back pressure too fast", "Landing on the nosewheel (wheelbarrowing)", "Looking at the runway just in front of the nose"),
            "Look at the far end of the runway during the flare: the sides of the runway tell you your height better than the nearby asphalt.",
        ) {
            pk(9f,
                K(0f, 0f, 400f, -3f, 62f, 30, "Final · flaps 30° · 60 KIAS"),
                K(0.35f, 3200f, 130f, -3f, 60f, 50, "Stabilized · full flaps"),
                K(0.55f, 4700f, 18f, -1f, 58f, 50, "Idle · round out"),
                K(0.67f, 5150f, 3f, 4f, 49f, 50, "Flare · hold it off"),
                K(0.75f, 5420f, 0f, 6f, 43f, 50, "Touch down on the mains"),
                K(0.88f, 5850f, 0f, 1f, 22f, 50, "Nosewheel down · brakes"),
                K(1f, 6010f, 0f, 0f, 6f, 50, ""),
            ) { runway = floatArrayOf(4600f, 7600f); aimX = 5000f }
        },

        M("xwind_ldg", G_TKO, "Crosswind approach & landing", "PA.IV.B",
            "Crab on final, wing-low to touchdown",
            "Land with a wind across the runway, touching down without sideways drift and with the airplane pointing down the runway.",
            listOf("Final" to "60 KIAS", "Gusts" to "Add half the gust factor", "Max demonstrated crosswind" to "16 kt", "Max tailwind" to "6 kt"),
            listOf(
                "On final, crab (turn into the wind) to track the extended centerline.",
                "Before the round-out, change to the wing-low method: lower the upwind wing and use opposite rudder so the nose points straight down the runway.",
                "Adjust the bank to stop the drift and the rudder to keep the alignment.",
                "Touch down on the upwind main wheel first, then the other, then the nose.",
                "On the rollout keep adding aileron into the wind as the airplane slows.",
            ),
            listOf("Drift" to "None at touchdown", "Alignment" to "Axis along the centerline", "Touchdown" to "Within 400 ft beyond the point", "Approach speed" to "+10/−5 kt"),
            listOf("Touching down while still crabbed (side load on the gear)", "Not enough aileron: drifting downwind in the flare", "Relaxing the aileron on the rollout", "Over-controlling with rudder"),
            "Rudder points the nose, aileron fixes the drift. If the centerline moves sideways in your windshield, it’s an aileron problem.",
        ) {
            GroundTrack(9f, 60f, 12f)
                .start(0f, -1500f, 0f, 500f, 63f)
                .straight(1050f, 120f, 60f, 50, label = "Final: crab into the wind")
                .straight(500f, 0f, 48f, 50, slip = 1f, label = "Wing low · opposite rudder")
                .straight(300f, 0f, 18f, 50, slip = 1f, label = "Upwind main first · aileron in")
                .apply { scene.runway = floatArrayOf(0f, -50f, 0f, 900f); scene.runwayNames = "36" to "18" }
        },

        M("short_ldg", G_TKO, "Short-field approach & landing", "PA.IV.F",
            "Steep, slow, firm touchdown on the point",
            "Clear a 50-ft obstacle and land in the shortest distance: a precise speed, a steeper approach, a touchdown at the aim point and maximum braking.",
            listOf("Flaps" to "50°", "Approach" to "≈ 1.3 VSO ≈ 48 KIAS (VSO 37) — or as your school sets", "Over 50 ft (POH)" to "1,310 ft paved", "Landing run (POH)" to "590 ft paved, braked"),
            listOf(
                "Full flaps early on a longer final; trim for the short-field approach speed.",
                "Steeper glidepath; aim point just beyond the obstacle. Power to hold the path, pitch to hold the speed exactly.",
                "Little or no float: reduce power smoothly and touch down firmly at the aim point at minimum speed.",
                "After touchdown: flaps up (for weight on the wheels), elevator back, maximum braking without skidding.",
            ),
            listOf("Approach speed" to "+5/−0 kt", "Touchdown" to "Within 200 ft beyond the point", "Drift" to "None; centerline", "Stopping" to "Shortest distance, safely"),
            listOf("Too fast: long float", "Too slow on final: hard landing or stall", "Floating to find the “perfect” landing", "Skidding the tires with too much braking"),
            "Every 1 kt too fast adds about 2 % to the landing distance — on a short field, speed is the whole game.",
        ) {
            pk(9f,
                K(0f, 0f, 430f, -5f, 50f, 50, "Full flaps · 1.3 VSO ≈ 48 KIAS"),
                K(0.42f, 3250f, 95f, -5f, 48f, 50, "Steep path over the obstacle"),
                K(0.6f, 4300f, 12f, -2f, 47f, 50, "Power off · minimal float"),
                K(0.68f, 4520f, 0f, 4f, 42f, 50, "Firm touchdown on the point"),
                K(0.74f, 4620f, 0f, 2f, 36f, 0, "Flaps up · max braking"),
                K(1f, 5110f, 0f, 0f, 0f, 0, "Stopped in ≈ 590 ft"),
            ) { runway = floatArrayOf(3950f, 6800f); obstacle = floatArrayOf(3500f, 50f); aimX = 4520f }
        },

        M("soft_ldg", G_TKO, "Soft-field approach & landing", "PA.IV.D",
            "Touch down slowly, nose held off, keep rolling",
            "Land on a soft surface as gently and slowly as possible, keeping the weight off the nosewheel and the airplane moving.",
            listOf("Flaps" to "50°", "Final" to "60 KIAS", "Landing run (POH, grass)" to "520 ft", "Over 50 ft (POH, grass)" to "1,250 ft"),
            listOf(
                "Normal approach with full flaps at 60 KIAS.",
                "In the flare keep a little power to touch down at the slowest speed with the lowest descent rate.",
                "Hold the nose off the surface with back pressure as long as possible.",
                "Keep the elevator back and the airplane moving; avoid braking. Add power if needed to keep rolling.",
            ),
            listOf("Approach speed" to "+10/−5 kt", "Touchdown" to "Minimum descent rate and groundspeed", "Drift" to "None", "After landing" to "Weight off the nosewheel; keep moving"),
            listOf("Letting the nosewheel drop", "Braking on the soft surface", "Closing the throttle too soon: a hard touchdown"),
            "Think of it as flying the airplane onto the ground and continuing to fly it there with the elevator.",
        ) {
            pk(9f,
                K(0f, 0f, 380f, -3f, 62f, 50, "Final · full flaps · 60 KIAS"),
                K(0.42f, 3300f, 60f, -2f, 60f, 50, "Stabilized"),
                K(0.58f, 4300f, 6f, 3f, 52f, 50, "Round out · keep a little power"),
                K(0.7f, 4800f, 0f, 8f, 42f, 50, "Touch down slowly, nose high"),
                K(0.86f, 5200f, 0f, 7f, 25f, 50, "Hold the nose off · no brakes"),
                K(1f, 5500f, 0f, 1f, 10f, 50, "Keep it rolling"),
            ) { soft = true; runway = floatArrayOf(4100f, 7400f) }
        },

        M("slip", G_TKO, "Forward slip to a landing", "PA.IV.G",
            "Lose altitude without speed: wing down, opposite rudder",
            "Descend steeply without gaining airspeed — when too high on final or with no flaps — while keeping the airplane on the extended centerline, and recover before the touchdown.",
            listOf("Airspeed" to "60 KIAS — keep it constant", "Bank" to "Into the wind", "Rudder" to "Opposite, to keep the track"),
            listOf(
                "Throttle to idle; lower the upwind wing with aileron.",
                "Apply opposite rudder so the airplane keeps tracking the centerline; the nose yaws away from the low wing.",
                "Lower the nose to keep 60 KIAS (the airspeed indicator may read wrong in the slip).",
                "Adjust the bank to control the rate of descent.",
                "Recover smoothly before the round-out: wings level, rudder neutral, then land normally.",
            ),
            listOf("Touchdown" to "Within 400 ft beyond the point", "Track" to "On the extended centerline", "Airspeed" to "Constant; no drift at touchdown"),
            listOf("Letting the speed build or decay in the slip", "Holding the slip into the flare", "Not enough rudder: turning instead of slipping"),
            "In a slip the ball is way off center on purpose — trust the runway, not the ball.",
        ) {
            pk(9f,
                K(0f, 0f, 620f, -2f, 60f, 0, "Too high on final"),
                K(0.12f, 500f, 590f, -5f, 60f, 0, "Idle · upwind wing down · opposite rudder", bank = -14f),
                K(0.5f, 2600f, 140f, -8f, 60f, 0, "Steep descent on the centerline", bank = -16f),
                K(0.62f, 3150f, 35f, -2f, 60f, 0, "Recover before the flare", bank = 0f),
                K(0.73f, 3550f, 3f, 4f, 50f, 0, "Flare"),
                K(0.8f, 3750f, 0f, 6f, 44f, 0, "Touch down"),
                K(1f, 4400f, 0f, 0f, 10f, 0, ""),
            ) { runway = floatArrayOf(3300f, 6500f); aimX = 3600f; glide = floatArrayOf(0f, 620f, 6500f, 0f) }
        },

        M("go_around", G_TKO, "Go-around / rejected landing", "PA.IV.N",
            "Power, attitude, flaps 15°, climb",
            "Abandon a landing safely: stop the descent, start a climb and clean up the airplane in the right order, while staying clear of traffic on the runway.",
            listOf("Power" to "Full", "Flaps" to "15° at once, 0° above 150 ft", "Climb" to "56 KIAS, then Vy 65 KIAS", "POH" to "Balked landing 4.5.12"),
            listOf(
                "Decide early — any doubt is a go-around.",
                "Full power, carb heat off (if used), pitch up to stop the descent.",
                "Flaps to 15° immediately; climb at 56 KIAS.",
                "Move to the side of the runway to keep traffic in sight; announce the go-around.",
                "Above 150 ft: flaps up, climb at Vy 65 KIAS, trim, rejoin the pattern.",
            ),
            listOf("Decision" to "Timely", "Climb" to "Vx or Vy +10/−5 kt", "Flaps" to "Retract in stages", "Track" to "Proper wind correction; avoid traffic"),
            listOf("Hesitating", "Retracting all the flaps at once near the ground", "Not enough right rudder at full power", "Pitch up too far with full flaps: the speed falls"),
            "Power – attitude – configure: P-A-C. Never “touch and fix” a bad approach.",
        ) {
            pk(9f,
                K(0f, 0f, 320f, -3f, 60f, 50, "Final · runway blocked"),
                K(0.28f, 2400f, 70f, -3f, 60f, 50, "Go around!"),
                K(0.36f, 2850f, 55f, 4f, 58f, 15, "Full power · pitch up · flaps 15°"),
                K(0.6f, 4100f, 150f, 8f, 56f, 15, "Climb at 56 KIAS"),
                K(0.72f, 4800f, 230f, 7f, 61f, 0, "Above 150 ft: flaps up"),
                K(1f, 6600f, 520f, 8f, 65f, 0, "Vy 65 KIAS · offset · announce"),
            ) { runway = floatArrayOf(2900f, 6000f); refLine = 150f; refLabel = "150 FT · FLAPS UP" }
        },

        // ---------------------------------------------------------------- performance
        M("steep", G_PERF, "Steep turns", "PA.V.A",
            "45° bank, 360° each way, altitude ±100 ft",
            "Develop coordination and orientation by turning through 360° in each direction at 45° of bank while holding altitude and airspeed.",
            listOf("Entry speed" to "At or below VA 90 KIAS (≈ 80–85)", "Bank" to "45°", "Altitude" to "≥ 1,500 ft AGL", "Load factor" to "1.41 g · stall ≈ 1.19 × VS"),
            listOf(
                "Clearing turns; pick a prominent reference on the horizon and note the heading.",
                "Roll into 45° smoothly; as the bank passes 30°, add back pressure (and a little power) to hold altitude.",
                "Hold the bank with the horizon picture; check altitude and airspeed; keep the ball centered.",
                "Begin the rollout about 20° (half the bank) before the entry heading; release the back pressure.",
                "Roll straight into the turn the other way and repeat.",
            ),
            listOf("Bank" to "45° ±5°", "Altitude" to "±100 ft", "Airspeed" to "±10 kt", "Rollout heading" to "±10°"),
            listOf("Not enough back pressure: losing altitude", "Overbanking tendency not checked", "Looking at the instruments instead of outside", "Late or early rollout", "Uncoordinated: ball not centered"),
            "Fix your eyes on the cowling’s position on the horizon at 45°. If the nose drops below it, reduce the bank first, then pull.",
        ) {
            GroundTrack(9f)
                .start(0f, -400f, 0f, 3500f, 84f)
                .straight(320f, label = "Clear · pick a reference · 84 KIAS")
                .turn(-360f, 196f, label = "Left 45° · back pressure, a little power")
                .turn(360f, 196f, label = "Reverse: right 45°")
                .straight(320f, label = "Roll out on the entry heading")
        },

        // ---------------------------------------------------------------- ground reference
        M("rect", G_GND, "Rectangular course", "PA.V.B",
            "Wind correction around a field",
            "Fly a uniform distance around a rectangular field at a constant altitude, correcting for the wind on every leg — the traffic pattern’s skills, practiced at altitude.",
            listOf("Altitude" to "600–1,000 ft AGL", "Airspeed" to "≈ 80 KIAS", "Distance" to "About ¼–½ mile from the boundary", "Bank" to "Steepest when downwind, ≤ 45°"),
            listOf(
                "Pick a field with suitable forced-landing areas nearby; enter at 45° to the downwind leg.",
                "Downwind: fastest groundspeed — begin the turn to base early and use the steepest bank.",
                "Base: crab into the wind to keep parallel to the boundary; the turn to the upwind leg is shallower.",
                "Upwind: slowest groundspeed; turn to the crosswind leg with the shallowest bank.",
                "Crosswind: crab toward the wind, then turn to the downwind leg with a medium bank.",
            ),
            listOf("Altitude" to "±100 ft", "Airspeed" to "±10 kt", "Track" to "Uniform distance; proper wind correction", "Separation" to "Clear of obstacles"),
            listOf("Turning at the same bank on every corner", "Not crabbing: the legs bend inward or outward", "Gaining or losing altitude in the turns", "Watching the field and forgetting other traffic"),
            "A corner is late when the ground track overshoots: begin the turn when the boundary is just ahead of the wingtip, not abeam.",
        ) {
            GroundTrack(10f, 270f, 15f)
                .start(0f, 1050f, 90f, 800f, 80f)
                .straight(1270f, label = "Downwind: fastest groundspeed")
                .turn(90f, 180f, label = "Turn to base: steepest bank")
                .straight(940f, label = "Base: crab into the wind")
                .turn(90f, 180f)
                .straight(1340f, label = "Upwind: slowest groundspeed")
                .turn(90f, 180f, label = "Shallowest bank")
                .straight(940f, label = "Crosswind: crab into the wind")
                .turn(90f, 180f)
                .straight(380f)
                .apply { scene.field = RectF(0f, 0f, 1200f, 800f) }
        },

        M("sturns", G_GND, "S-turns", "PA.V.B",
            "Half-circles across a road, bank changing with groundspeed",
            "Fly two equal half-circles on opposite sides of a straight road perpendicular to the wind, varying the bank to keep a constant radius over the ground.",
            listOf("Altitude" to "600–1,000 ft AGL", "Airspeed" to "≈ 80 KIAS", "Bank" to "Steepest when heading downwind, ≤ 45°"),
            listOf(
                "Choose a straight road at right angles to the wind; cross it heading downwind, wings level.",
                "Roll into the steepest bank right over the road; groundspeed is highest now.",
                "Reduce the bank gradually as the airplane turns toward the wind; shallowest heading upwind.",
                "Cross the road again wings level, heading upwind, then begin the opposite turn with a shallow bank, steepening as you turn downwind.",
            ),
            listOf("Altitude" to "±100 ft", "Airspeed" to "±10 kt", "Shape" to "Equal half-circles", "Crossing" to "Wings level over the road"),
            listOf("Constant bank: the half-circles become uneven", "Not level when crossing the road", "Altitude changes in the steep part", "Fixating on the road"),
            "Look at the road ahead of the wing and keep the radius: the bank is just the tool, the circle on the ground is the maneuver.",
        ) {
            GroundTrack(9f, 360f, 15f)
                .start(0f, 380f, 180f, 800f, 80f)
                .straight(380f, label = "Cross the road heading downwind")
                .turn(-180f, 260f, label = "Steepest bank first, shallowing upwind")
                .turn(180f, 260f, label = "Wings level over the road · reverse")
                .straight(300f, label = "Equal half-circles")
                .apply { scene.road = floatArrayOf(-400f, 0f, 1500f, 0f) }
        },

        M("tap", G_GND, "Turns around a point", "PA.V.B",
            "Constant radius around a point in the wind",
            "Circle a prominent point on the ground at a constant radius and altitude, varying the bank with the groundspeed.",
            listOf("Altitude" to "600–1,000 ft AGL", "Airspeed" to "≈ 80 KIAS", "Entry" to "Downwind, at the chosen radius", "Bank" to "Steepest downwind, ≤ 45°"),
            listOf(
                "Choose an isolated point; enter heading downwind at the radius you want, on the left side of it.",
                "Steepest bank when heading downwind (highest groundspeed).",
                "Shallow it as you turn crosswind and upwind; shallowest when heading straight into the wind.",
                "Steepen again as you turn back downwind; keep the point at the same spot near the wingtip.",
                "Complete at least two turns; exit on the entry heading.",
            ),
            listOf("Altitude" to "±100 ft", "Airspeed" to "±10 kt", "Radius" to "Constant; proper wind correction", "Bank" to "≤ 45°"),
            listOf("Constant bank: the circle drifts downwind", "Point sliding forward or behind the wingtip", "Losing altitude at the steepest bank"),
            "The wingtip is your sight: if the point moves ahead of it, steepen; if it falls behind, shallow.",
        ) {
            GroundTrack(9.5f, 360f, 14f)
                .start(-350f, 650f, 180f, 800f, 80f)
                .straight(650f, label = "Enter downwind at the radius")
                .turn(-360f, 350f, label = "Steepest downwind, shallowest upwind")
                .straight(450f, label = "Exit on the entry heading")
                .apply { scene.point = floatArrayOf(0f, 0f) }
        },

        // ---------------------------------------------------------------- slow flight & stalls
        M("slow", G_SLOW, "Maneuvering during slow flight", "PA.VII.A",
            "Just above the stall warning, altitude held",
            "Fly at an airspeed at which any more angle of attack would trigger the stall warning, in straight flight, turns, climbs and descents, with full control.",
            listOf("Altitude" to "Recovery ≥ 1,500 ft AGL", "Flaps" to "As assigned (often 50°)", "Stall, flaps 50°" to "37 KIAS", "Stall, flaps 0°" to "38 KIAS", "Target" to "Just above the stall warning"),
            listOf(
                "Clearing turns. Carb heat (if fitted); power back.",
                "As the speed falls through the flap range (VFE 70 KIAS), extend the flaps in stages.",
                "Raise the nose to hold altitude; when near the target speed, add power to hold it there.",
                "Pitch and power together: power for altitude, pitch for airspeed (or as your school teaches).",
                "Fly straight, turns up to 30° of bank, climbs and descents as assigned. More right rudder.",
                "Recover: full power, lower the nose, flaps up in stages, back to cruise.",
            ),
            listOf("Altitude" to "±100 ft", "Heading" to "±10°", "Airspeed" to "+10/−0 kt", "Bank" to "±10° of the specified bank"),
            listOf("Triggering the stall warning", "Not enough right rudder: ball out", "Losing altitude when turning", "Exceeding VFE with the flaps"),
            "It is a coordination exercise — the controls are soft and slow to answer. Make small inputs and wait.",
        ) {
            pk(9f,
                K(0f, 0f, 3500f, 1f, 84f, 0, "Clear the area · power back"),
                K(0.2f, 1500f, 3500f, 5f, 68f, 15, "Below 70 KIAS: flaps 15°"),
                K(0.4f, 2700f, 3502f, 9f, 55f, 50, "Flaps 50° · nose up · add power"),
                K(0.56f, 3500f, 3500f, 12f, 45f, 50, "Slow flight: no stall warning"),
                K(0.8f, 4700f, 3498f, 12f, 45f, 50, "Altitude ±100 ft · airspeed +10/−0"),
                K(1f, 5800f, 3500f, 12f, 45f, 50, "Small inputs · right rudder"),
            ) { horizonOnly = true }
        },

        M("stall_off", G_SLOW, "Power-off stall", "PA.VII.B",
            "Landing configuration, stall, recover promptly",
            "Recognize and recover from a stall in the approach-to-landing configuration — the one most often met close to the ground.",
            listOf("Altitude" to "Recovery ≥ 1,500 ft AGL", "Flaps" to "50° (landing)", "Approach" to "60 KIAS", "Stall, flaps 50°" to "37 KIAS", "Turning stall (POH)" to "43 KIAS"),
            listOf(
                "Clearing turns. Slow down, flaps 50°, establish a stabilized descent at 60 KIAS.",
                "Throttle idle (or as on a final approach), raise the nose to a landing attitude and keep raising it.",
                "Acknowledge the cues: stall warning, buffet, mushy controls, the nose dropping.",
                "Recover at once: reduce the angle of attack (push), level the wings, full power, right rudder.",
                "Flaps to 15°, climb at Vx/Vy; then flaps up, Vy 65 KIAS.",
            ),
            listOf("Heading" to "±10° straight, or bank ≤ 20° ±5° in turns", "Recovery" to "Promptly: reduce AoA first", "Climb" to "Vx or Vy", "Altitude loss" to "Minimum; no secondary stall"),
            listOf("Adding power before reducing the angle of attack", "Using aileron to pick up a dropping wing (rudder first)", "Retracting all the flaps at once", "Secondary stall from pulling up too fast"),
            "Reduce the AoA first — that alone ends the stall. Power only shortens the altitude loss.",
        ) {
            pk(9f,
                K(0f, 0f, 3500f, -3f, 60f, 50, "Flaps 50° · descend at 60 KIAS"),
                K(0.2f, 1300f, 3440f, -2f, 60f, 50, "Idle · landing attitude"),
                K(0.36f, 2200f, 3420f, 7f, 50f, 50, "Keep raising the nose"),
                K(0.5f, 2800f, 3412f, 12f, 41f, 50, "Stall warning", warn = "STALL WARNING"),
                K(0.58f, 3100f, 3400f, 14f, 37f, 50, "Buffet · the break", warn = "STALL"),
                K(0.65f, 3350f, 3350f, -2f, 40f, 50, "Push: reduce AoA · wings level"),
                K(0.74f, 3750f, 3320f, 3f, 50f, 15, "Full power · flaps 15°"),
                K(0.88f, 4600f, 3360f, 9f, 56f, 15, "Climb at Vx 56"),
                K(1f, 5600f, 3450f, 8f, 65f, 0, "Flaps up · Vy 65 KIAS"),
            ) { horizonOnly = true }
        },

        M("stall_on", G_SLOW, "Power-on stall", "PA.VII.C",
            "Takeoff/departure configuration, high pitch, recover",
            "Recognize and recover from a stall in the takeoff and departure configuration, as happens after lift-off when pitched too high.",
            listOf("Altitude" to "Recovery ≥ 1,500 ft AGL", "Entry" to "Slow to lift-off speed ≈ 57 KIAS", "Power" to "Climb power (≥ 65 %)", "Stall, flaps 0°" to "38 KIAS · turning 44 KIAS"),
            listOf(
                "Clearing turns. Slow to about lift-off speed in the takeoff configuration.",
                "Set climb power and raise the nose to an attitude that will cause a stall; hold it. Right rudder.",
                "Acknowledge the cues: warning, buffet, nose dropping.",
                "Recover: reduce the angle of attack, level the wings with coordinated controls, full power.",
                "Climb at Vx/Vy and return to the specified altitude and heading.",
            ),
            listOf("Heading" to "±10° straight, or bank ≤ 20° ±5° in turns", "Recovery" to "Promptly: reduce AoA first", "Climb" to "Vx or Vy", "Altitude loss" to "Minimum"),
            listOf("Too little right rudder at high power: a wing drops (spin entry)", "Not holding the pitch: the stall never comes", "Pushing too far: negative g and lost altitude"),
            "With the engine at climb power the left-turning tendency is strong — keep the ball centered all the way to the break.",
        ) {
            pk(9f,
                K(0f, 0f, 3500f, 0f, 62f, 0, "Slow to lift-off speed"),
                K(0.16f, 900f, 3505f, 6f, 57f, 0, "Climb power · pitch up"),
                K(0.4f, 2200f, 3590f, 18f, 46f, 0, "Hold the attitude · right rudder"),
                K(0.52f, 2700f, 3620f, 20f, 41f, 0, "Stall warning", warn = "STALL WARNING"),
                K(0.6f, 2950f, 3628f, 19f, 38f, 0, "The break", warn = "STALL"),
                K(0.67f, 3200f, 3600f, 0f, 42f, 0, "Push · wings level · full power"),
                K(0.82f, 4000f, 3590f, 7f, 56f, 0, "Climb at Vx 56 KIAS"),
                K(1f, 5200f, 3680f, 9f, 65f, 0, "Vy 65 KIAS"),
            ) { horizonOnly = true }
        },

        // ---------------------------------------------------------------- emergency
        M("emer", G_EMER, "Emergency approach & landing (simulated)", "PA.IX.B",
            "Best glide 59 KIAS, a field, a plan",
            "After a simulated engine failure, establish the best glide, choose a suitable landing area within gliding distance, run the checklist, and plan an approach that reaches it.",
            listOf("Best glide (POH)" to "59 KIAS", "Flaps" to "When the field is made", "Checklist" to "POH section 3", "Brief" to "Fuel, ignition, mixture/choke, master as the POH says"),
            listOf(
                "Airspeed: pitch for 59 KIAS at once and trim.",
                "Best field: within gliding distance, into the wind if possible, the longest and smoothest.",
                "Checklist: find the cause — fuel selector, electric pump, carb heat, ignition, choke — attempt a restart.",
                "Plan the descent: spiral over the field to a high key position, then a normal pattern to it.",
                "Communicate: 121.5 or the frequency in use, squawk 7700 (when not simulated).",
                "Secure the airplane for the landing per the POH; flaps when the field is made.",
            ),
            listOf("Glide" to "Best glide ±10 kt", "Field" to "Suitable, within range", "Checklist" to "Completed from memory, then the POH", "Plan" to "Pattern reaches the field"),
            listOf("Delaying the pitch for best glide", "Picking a field behind you or too far", "Getting too low before the base turn", "Stretching the glide by pulling up"),
            "Aim for the first third of the field; it’s far better to land long at slow speed than short into the fence.",
        ) {
            GroundTrack(10f, 360f, 8f)
                .start(-420f, 2200f, 180f, 3000f, 84f)
                .straight(200f, 2950f, 59f, label = "Engine out: pitch for 59 KIAS")
                .straight(500f, 2700f, 59f, label = "Best field · checklist · restart")
                .turn(-360f, 300f, 1500f, 59f, label = "Spiral down over the field")
                .straight(1700f, 650f, 59f, label = "Key position · downwind")
                .turn(-90f, 200f, 420f, 59f, 15, label = "Base: flaps when the field is made")
                .turn(-90f, 200f, 220f, 59f, 50)
                .straight(260f, 0f, 45f, 50, label = "Touch down in the first third")
                .straight(220f, 0f, 12f, 50)
                .apply { scene.runway = floatArrayOf(0f, -40f, 0f, 700f); scene.soft = true }
        },
    ) }

    fun byId(id: String?) = ALL.firstOrNull { it.id == id }
}
