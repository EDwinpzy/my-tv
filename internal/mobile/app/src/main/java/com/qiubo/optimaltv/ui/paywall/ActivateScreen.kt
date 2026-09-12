package com.qiubo.optimaltv.ui.paywall

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.qiubo.optimaltv.license.ActivateResult
import com.qiubo.optimaltv.license.LicenseManager
import com.qiubo.optimaltv.ui.components.tapCard
import com.qiubo.optimaltv.ui.components.MobileBackButton
import com.qiubo.optimaltv.ui.theme.OtvColors
import com.qiubo.optimaltv.ui.theme.rememberUiScale
import com.qiubo.optimaltv.ui.theme.sx
import com.qiubo.optimaltv.ui.theme.sxs
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * v1.20 激活输码页（移动#1 用户需求：不要自带软键盘，呼出系统默认输入法）：
 * 氛围径向光晕 + 金属标徽章页头 + OTV- 固定前缀 + 分段码位格（5+5）。
 * 码位格整块即输入热区：点按呼出系统输入法（BasicTextField 隐藏承载，光标随输入
 * 实时落在当前码位）；输入过滤为卡密字母表并截断到 10 位。输满高亮「激活卡密」。
 * 键入过程中系统输入法弹出/收起会重组布局——页面内容上移由 imePadding 自然处理。
 */
@Composable
fun ActivateScreen(nav: NavController) {
    val s = rememberUiScale()
    var input by remember { mutableStateOf("") }
    var result by remember { mutableStateOf<String?>(null) }
    var resultOk by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    val fieldFocus = remember { FocusRequester() }

    BackHandler { nav.popBackStack() }

    // 激活成功 → 停留展示结果后自动返回（会员页/门控页状态即时刷新）
    // 总体#1（2026-09-03）：激活成功自动进入足球界面（popUpTo 起点页直达）
    LaunchedEffect(resultOk) {
        if (resultOk) {
            kotlinx.coroutines.delay(1000)
            com.qiubo.optimaltv.ui.components.navigateToTab(nav, "live")
        }
    }

    // 移动#1：进页自动落焦隐藏输入框 → 系统输入法直接弹出，点码位可随时唤回
    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(300)
        runCatching { fieldFocus.requestFocus() }
    }

    Box(Modifier.fillMaxSize().background(OtvColors.Bg)) {
        // 氛围光晕：码位区主光 + 右上品牌蓝晕（纯装饰）
        Canvas(Modifier.fillMaxSize()) {
            val mainC = Offset(size.width * 0.5f, size.height * 0.34f)
            drawCircle(
                brush = Brush.radialGradient(
                    listOf(Color(0x10FFFFFF), Color.Transparent), mainC, size.width * 0.52f,
                ),
                radius = size.width * 0.52f, center = mainC,
            )
            val blueC = Offset(size.width * 0.9f, -size.height * 0.06f)
            drawCircle(
                brush = Brush.radialGradient(
                    listOf(Color(0x140A84FF), Color.Transparent), blueC, size.width * 0.36f,
                ),
                radius = size.width * 0.36f, center = blueC,
            )
        }

        // 需求③（2026-09-04）：内容左对齐（页头/码位/按钮/标语统一左构图，不再居中）
        Column(
            horizontalAlignment = Alignment.Start,
            modifier = Modifier
                .fillMaxSize()
                .padding(start = 90f.sx(s), end = 60f.sx(s), top = 130f.sx(s))
                .imePadding(),
        ) {
            // ---- 页头：金属标徽章 + 标题 ----
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier,
            ) {
                Box(
                    contentAlignment = Alignment.Center,
                    modifier = Modifier
                        .size(112f.sx(s))
                        .background(Color(0x14FFFFFF), RoundedCornerShape(30f.sx(s)))
                        .border(1.2f.sx(s), Color(0x1FFFFFFF), RoundedCornerShape(30f.sx(s))),
                ) {
                    Image(
                        painter = painterResource(com.qiubo.optimaltv.R.drawable.my_tv_logo),
                        contentDescription = null,
                        contentScale = ContentScale.Fit,
                        modifier = Modifier.size(84f.sx(s)),
                    )
                }
                Spacer(Modifier.width(30f.sx(s)))
                Column {
                    Text(
                        "激活卡密", color = OtvColors.White, fontSize = 46f.sxs(s), fontWeight = FontWeight.Bold,
                    )
                    Spacer(Modifier.height(10f.sx(s)))
                    Text(
                        "输入购买获得的 10 位卡密（OTV-XXXXX-XXXXX）",
                        color = OtvColors.White50, fontSize = 24f.sxs(s),
                    )
                }
            }

            Spacer(Modifier.height(52f.sx(s)))

            // ---- 分段码位：OTV- 前缀 + 5+5，中横杠。整块 = 系统输入法输入热区 ----
            BasicTextField(
                value = input,
                onValueChange = { raw ->
                    input = raw.uppercase().filter { it in CODE_ALPHABET }.take(10)
                },
                textStyle = androidx.compose.ui.text.TextStyle(color = Color.Transparent),
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Ascii,
                    capitalization = KeyboardCapitalization.Characters,
                    autoCorrect = false,
                ),
                modifier = Modifier
                    .focusRequester(fieldFocus)
                    .width(1.dp)
                    .height(1.dp)
                    .alpha(0f),
            )
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .tapCard { runCatching { fieldFocus.requestFocus() } },
            ) {
                    Text(
                        "OTV-",
                        color = OtvColors.White50, fontSize = 46f.sxs(s), fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(end = 18f.sx(s)),
                    )
                    repeat(5) { i ->
                        CodeSlot(ch = input.getOrNull(i), active = input.length == i, s = s)
                        if (i < 4) Spacer(Modifier.width(10f.sx(s)))
                    }
                    Spacer(Modifier.width(16f.sx(s)))
                    Box(
                        Modifier
                            .width(26f.sx(s))
                            .height(6f.sx(s))
                            .alpha(0.8f)
                            .background(Color(0x38FFFFFF), RoundedCornerShape(3f.sx(s))),
                    )
                    Spacer(Modifier.width(16f.sx(s)))
                    repeat(5) { i ->
                        CodeSlot(ch = input.getOrNull(5 + i), active = input.length == 5 + i, s = s)
                        if (i < 4) Spacer(Modifier.width(10f.sx(s)))
                    }
            }

            Spacer(Modifier.height(46f.sx(s)))

            // ---- 激活按钮 + 结果 ----
            Row(
                horizontalArrangement = Arrangement.spacedBy(18f.sx(s)),
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier,
            ) {
                val ready = input.length == 10 && !busy
                AcKey("激活卡密", s, wide = true, enabled = ready) {
                    if (ready) {
                        busy = true
                        result = null
                        scope.launch {
                            when (val r = LicenseManager.activate(input)) {
                                is ActivateResult.Ok -> {
                                    resultOk = true
                                    result = if (LicenseManager.isLifetime()) "激活成功 · 终身会员"
                                    else "激活成功 · 剩余 ${LicenseManager.daysLeft()} 天"
                                }
                                is ActivateResult.Error -> result = r.msg
                            }
                            busy = false
                        }
                    }
                }
                result?.let {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            Modifier
                                .size(12f.sx(s))
                                .background(
                                    if (resultOk) Color(0xFF30D158) else Color(0xFFFF453A),
                                    CircleShape,
                                ),
                        )
                        Spacer(Modifier.width(12f.sx(s)))
                        Text(
                            it,
                            color = if (resultOk) Color(0xFF30D158) else Color(0xFFFF453A),
                            fontSize = 28f.sxs(s),
                            fontWeight = FontWeight.Medium,
                            maxLines = 1, overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }

            Spacer(Modifier.height(20f.sx(s)))
            Text(
                "点按上方码位输入 · 激活后立即生效 · 一码可绑 2 台设备",
                color = OtvColors.White30,
                fontSize = 22f.sxs(s),
            )
        }
        // 移动① 修复：内容之后声明 = 最上层可点
        MobileBackButton { nav.popBackStack() }
    }
}

/** 卡密输入字母表（与生成器一致：剔除 0/O/1/I） */
private val CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

/** 单个码位格：已填大字 / 当前位亮框（外圈微光）+脉冲光标 / 空位暗点 */
@Composable
private fun CodeSlot(ch: Char?, active: Boolean, s: Float) {
    val shape = RoundedCornerShape(22f.sx(s))
    val pulse = rememberInfiniteTransition(label = "caret").animateFloat(
        initialValue = 0.35f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(650), RepeatMode.Reverse),
        label = "caretA",
    )
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .width(104f.sx(s))
            .height(134f.sx(s))
            .then(if (active) Modifier.border(5f.sx(s), Color(0x12FFFFFF), shape) else Modifier)
            .border(
                if (active) 1.5f.sx(s) else 1f.sx(s),
                if (active) Color(0x66FFFFFF) else Color(0x1AFFFFFF),
                shape,
            )
            .background(
                Brush.verticalGradient(listOf(Color(0x20FFFFFF), Color(0x12FFFFFF))),
                shape,
            ),
    ) {
        when {
            ch != null -> Text(
                ch.toString(),
                color = OtvColors.White,
                fontSize = 46f.sxs(s),
                fontWeight = FontWeight.SemiBold,
            )
            active -> Box(
                Modifier
                    .width(3.5f.sx(s))
                    .height(46f.sx(s))
                    .background(
                        Color.White.copy(alpha = pulse.value),
                        RoundedCornerShape(2f.sx(s)),
                    ),
            )
            else -> Box(Modifier.size(9f.sx(s)).background(Color(0x2EFFFFFF), CircleShape))
        }
    }
}

/** 宽胶囊 CTA（启用=白底黑字；禁用=暗底）；触控点按 */
@Composable
private fun AcKey(
    label: String,
    s: Float,
    wide: Boolean = false,
    enabled: Boolean = true,
    onTap: () -> Unit,
) {
    val shape = RoundedCornerShape(38f.sx(s))   // 76 高的一半：真胶囊
    val bg: Brush = when {
        wide && enabled -> Brush.verticalGradient(listOf(Color(0xE6FFFFFF), Color(0xE6FFFFFF)))
        wide -> Brush.verticalGradient(listOf(Color(0x16FFFFFF), Color(0x16FFFFFF)))
        else -> Brush.verticalGradient(listOf(Color(0x24FFFFFF), Color(0x12FFFFFF)))
    }
    val stroke = if (wide && enabled) null else Color(0x1FFFFFFF)
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .tapCard { if (enabled) onTap() }
            .background(bg, shape)
            .then(if (stroke != null) Modifier.border(1f.sx(s), stroke, shape) else Modifier)
            .width(if (wide) 300f.sx(s) else 64f.sx(s))
            .height(76f.sx(s)),
    ) {
        Text(
            label,
            color = when {
                wide && enabled -> OtvColors.Bg
                wide -> OtvColors.White30
                else -> OtvColors.White70
            },
            fontSize = 30f.sxs(s),
            fontWeight = FontWeight.SemiBold,
        )
    }
}
