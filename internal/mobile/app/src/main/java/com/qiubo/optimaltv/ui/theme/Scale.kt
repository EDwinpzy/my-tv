package com.qiubo.optimaltv.ui.theme

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp

/**
 * 设计稿坐标系（v1.18 与 TV 版 1:1 同款，1:1 复刻原版 web）：
 * 原版按 1920×1080 CSS px 设计，运行时等比缩放（与原版 fit() 同思路）。
 * 移动版 v1.18 起前端样式/布局与 TV 版完全一致（横屏），仅交互保留触控。
 * v1.19（2026-09-03 总体#2）竖屏自适应：竖屏时改按 750 移动设计宽缩放——
 * 字号/控件呈手机常规尺寸（420dp 宽手机：chip 高 36dp、字号 16sp、海报卡 130dp），
 * 横屏仍按 1920 与 TV 版 1:1。屏内固定列数由 rememberRowColumns 按此尺度自适应。
 * 用法：val s = rememberUiScale()
 *   320f.sx(s)  → 320 设计px 的尺寸(dp)
 *   29f.sxs(s)  → 29 设计px 的字号(sp)
 */
@Composable
fun rememberUiScale(): Float {
    val cfg = LocalConfiguration.current
    // 横屏：scale = 屏宽dp / 1920（sx(v) = v*scale dp = v×屏宽物理px/1920）
    // 竖屏：scale = 屏宽dp / 750（移动 2x 设计宽基准，全站 sx() 尺寸自动手机化）
    return if (cfg.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE)
        cfg.screenWidthDp / 1920f
    else cfg.screenWidthDp / 750f
}

/**
 * 竖屏自适应列数（总体#2）：按「设计卡宽+间距」与当前可用宽（屏宽-两侧留白）计算
 * 一行能放几张卡；横屏下该公式自然得出 TV 设计列数（如 232 卡 + 20 间距 + 80 留白
 * = 1920 宽下 7 列），无需按方向分支。最少 2 列。
 */
@Composable
fun rememberRowColumns(
    cardW: Float,          // 设计稿卡宽（设计 px，与 sx() 同坐标系）
    gap: Float = 20f,      // 设计稿卡间距
    sidePad: Float = 80f,  // 设计稿两侧留白
    minColumns: Int = 2,
): Int {
    val cfg = LocalConfiguration.current
    val s = rememberUiScale()
    val avail = cfg.screenWidthDp - 2 * sidePad * s
    val per = (cardW + gap) * s
    return maxOf(minColumns, ((avail + gap * s) / per).toInt())
}

fun Float.sx(scale: Float): Dp = (this * scale).dp

@Composable
fun Float.sxs(scale: Float): TextUnit = with(LocalDensity.current) { (this@sxs * scale).dp.toSp() }

/** 原版 web 色板（index.html :root 与组件 CSS） */
object OtvColors {
    val Bg = Color(0xFF0E0E0F)          // --bg
    val Panel = Color(0xFF232323)       // --panel
    val Live = Color(0xFFFF3A5F)        // --live（LIVE 徽章红）
    val AccentBlue = Color(0xFF0A84FF)
    val White = Color(0xFFFFFFFF)
    val White60 = Color(0x99FFFFFF)     // --muted
    val White75 = Color(0xBFFFFFFF)     // .75
    val White70 = Color(0xB3FFFFFF)     // .7
    val White55 = Color(0x8CFFFFFF)     // .55
    val White50 = Color(0x80FFFFFF)     // .5
    val White30 = Color(0x4DFFFFFF)     // --dim
    val Line = Color(0x1AFFFFFF)        // --line
    val ChipBg = Color(0x1FFFFFFF)      // rgba(255,255,255,.12)
    val TabBarBg = Color(0x801E1E1E)    // rgba(30,30,30,.5)
    val CardBlack80 = Color(0xCC000000) // gc-score rgba(0,0,0,.8)
    val PanelBg = Color(0xF517171C)
    val InputBg = Color(0xFF1C1C22)
}
