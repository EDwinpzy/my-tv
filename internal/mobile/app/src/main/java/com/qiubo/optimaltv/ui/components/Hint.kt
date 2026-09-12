package com.qiubo.optimaltv.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import com.qiubo.optimaltv.ui.theme.rememberUiScale
import com.qiubo.optimaltv.ui.theme.sx
import com.qiubo.optimaltv.ui.theme.sxs
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 双击返回才彻底退出应用（移动版沿用 TV 版交互习惯）：
 * 首次返回轻提示「再按一次退出」，2.5s 内再按 finishAffinity。
 */
@Composable
fun rememberDoubleBackExit(onHint: (String) -> Unit): () -> Unit {
    val activity = androidx.compose.ui.platform.LocalContext.current as? android.app.Activity
    var lastBackAt by remember { mutableLongStateOf(0L) }
    return {
        // v1.19：交互计时改 uptimeMillis——墙钟受 NTP 校时跳变影响会出现
        // 「连按两次退不出去/误退出」（与 v1.18 跨时钟域 bug 同源）
        val now = android.os.SystemClock.uptimeMillis()
        if (now - lastBackAt < 2500) {
            activity?.finishAffinity()
        } else {
            lastBackAt = now
            onHint("再按一次返回键退出应用")
        }
    }
}

/** 底部轻提示（需求 足球#5：只保留文字，背景半透明灰色；v1.18 尺寸与 TV 版 1:1 同款）。
 *  需求 影视#3：全站浮窗提示统一贴屏幕最下方（底边距 40，不再浮在半空）。
 */
@Composable
fun BoxScope.OtvHint(text: String?, modifier: Modifier = Modifier) {
    if (text.isNullOrBlank()) return
    val s = rememberUiScale()
    Box(
        modifier
            .align(Alignment.BottomCenter)
            .padding(bottom = 40f.sx(s))
            .background(Color(0x8C808080), RoundedCornerShape(24f.sx(s)))
            .padding(horizontal = 36f.sx(s), vertical = 16f.sx(s)),
    ) {
        Text(
            text, color = Color.White, fontSize = 26f.sxs(s), fontWeight = FontWeight.Medium,
        )
    }
}
