package com.saudi.privatevault

import android.view.MotionEvent

/** The pen's own eraser: its eraser end, or its side button held while writing (S Pen and others). */
object Stylus {
    private const val BUTTONS = MotionEvent.BUTTON_STYLUS_PRIMARY or MotionEvent.BUTTON_STYLUS_SECONDARY or MotionEvent.BUTTON_SECONDARY

    fun isPen(e: MotionEvent) = e.getToolType(0).let { it == MotionEvent.TOOL_TYPE_STYLUS || it == MotionEvent.TOOL_TYPE_ERASER }

    fun erasing(e: MotionEvent): Boolean {
        val t = e.getToolType(0)
        if (t == MotionEvent.TOOL_TYPE_ERASER) return true
        return t == MotionEvent.TOOL_TYPE_STYLUS && (e.buttonState and BUTTONS) != 0
    }
}
