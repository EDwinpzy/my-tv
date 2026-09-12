package com.qiubo.optimaltv.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.qiubo.optimaltv.ui.theme.OtvColors

private fun playerClock(sec: Long): String {
    val h = sec / 3600
    val m = sec % 3600 / 60
    val s = sec % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%d:%02d".format(m, s)
}

/** 竖屏播放器的纯 UI/交互组件；播放状态与动作由调用方注入，便于稳定自动回归。 */
@Composable
fun PortraitPlayerControls(
    title: String,
    meta: String,
    positionMs: Long,
    durationMs: Long,
    isLive: Boolean,
    isPlaying: Boolean,
    onSeek: (Long) -> Unit,
    onTogglePlay: () -> Unit,
    onFullscreen: () -> Unit,
    onMore: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .background(OtvColors.Bg)
            .padding(horizontal = 24.dp, vertical = 18.dp),
    ) {
        Text(
            title,
            color = OtvColors.White,
            fontSize = 18.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        if (meta.isNotBlank()) {
            Spacer(Modifier.height(6.dp))
            Text(meta, color = OtvColors.White50, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Spacer(Modifier.height(14.dp))
        val positionSeconds = positionMs / 1000
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(playerClock(positionSeconds), color = OtvColors.White75, fontSize = 12.sp, fontWeight = FontWeight.Medium)
            Spacer(Modifier.width(10.dp))
            BoxWithConstraints(Modifier.weight(1f).height(26.dp)) {
                val density = LocalDensity.current
                val trackWidth = with(density) { maxWidth.toPx() }
                val trackHeight = 5.dp
                val fraction = if (isLive) 1f
                    else if (durationMs > 0) (positionMs.toFloat() / durationMs.toFloat()).coerceIn(0f, 1f)
                    else 0f
                Box(
                    Modifier.align(Alignment.CenterStart).fillMaxWidth().height(trackHeight)
                        .background(OtvColors.White.copy(alpha = 0.25f), RoundedCornerShape(trackHeight / 2)),
                )
                Box(
                    Modifier.align(Alignment.CenterStart).fillMaxWidth(fraction).height(trackHeight)
                        .background(OtvColors.White, RoundedCornerShape(trackHeight / 2)),
                )
                Box(
                    Modifier
                        .align(Alignment.CenterStart)
                        .fillMaxWidth()
                        .height(26.dp)
                        .testTag(MobileUiTags.PlayerSeek)
                        .pointerInput(durationMs) {
                            detectTapGestures { offset ->
                                if (durationMs > 0 && trackWidth > 0f) {
                                    onSeek(((offset.x / trackWidth).coerceIn(0f, 1f) * durationMs).toLong())
                                }
                            }
                        },
                )
            }
            Spacer(Modifier.width(10.dp))
            Text(
                if (isLive) "直播" else "-" + playerClock(((durationMs - positionMs) / 1000).coerceAtLeast(0)),
                color = OtvColors.White75,
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium,
            )
        }
        Spacer(Modifier.height(16.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            PlayerTextButton(
                tag = MobileUiTags.PlayerPlayPause,
                text = if (isPlaying) "暂停" else "播放",
                primary = false,
                onClick = onTogglePlay,
            )
            Spacer(Modifier.width(12.dp))
            PlayerTextButton(
                tag = MobileUiTags.PlayerFullscreen,
                text = "全屏播放",
                primary = true,
                onClick = onFullscreen,
            )
            Spacer(Modifier.weight(1f))
            if (!isLive) {
                PlayerTextButton(
                    tag = MobileUiTags.PlayerMore,
                    text = "更多",
                    primary = false,
                    onClick = onMore,
                )
            }
        }
    }
}

@Composable
private fun PlayerTextButton(tag: String, text: String, primary: Boolean, onClick: () -> Unit) {
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .clip(RoundedCornerShape(12.dp))
            .testTag(tag)
            .semantics { role = Role.Button }
            .tapCard(onClick)
            .background(if (primary) OtvColors.White else Color(0x29FFFFFF), RoundedCornerShape(12.dp))
            .padding(horizontal = 22.dp, vertical = 12.dp),
    ) {
        Text(
            text,
            color = if (primary) OtvColors.Bg else OtvColors.White,
            fontSize = 14.sp,
            fontWeight = if (primary) FontWeight.Bold else FontWeight.SemiBold,
        )
    }
}
