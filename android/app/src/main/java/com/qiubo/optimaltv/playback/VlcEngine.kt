package com.qiubo.optimaltv.playback

import android.content.Context
import android.view.TextureView
import android.view.View
import com.qiubo.optimaltv.OtvLog
import java.util.concurrent.Executors
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.videolan.libvlc.LibVLC
import org.videolan.libvlc.Media
import org.videolan.libvlc.MediaPlayer
import org.videolan.libvlc.interfaces.IVLCVout

/**
 * libVLC 兜底引擎（v1.8 2026-08-30，直播解码失败三段回退的最后一棒）：
 *
 * 背景：MuMu/部分盒子的 MediaCodec 生态里「硬解」OMX.qcom.video.decoder.avc 内部
 * 实际包的是上古 SoftAVCDec 软件内核，遇到 AVC High 压段（8x8 变换 + CABAC，
 * bb 原版足球直播2 的 CDN 压片特征）直接 Fatal Error 0xffffffff；软解
 * OMX.google.h264.decoder 是同一内核同样必挂——MediaCodec 路线全线无解。
 * VLC 自带完整 ffmpeg 解码器，且按媒体关闭其 mediacodec 硬解（否则又会踩回
 * 同一批坏 codec），因此在本引擎里永远走自带 avcodec 软解，任何设备都能出画面。
 *
 * 引擎定位：仅直播 DECODING_FAILED 后自动切入（PlayerViewModel 回退链），
 * 正常设备硬解顺畅时不会用到，不给用户当默认引擎选。
 */
class VlcEngine(context: Context) : MediaEngine {

    override val engineId = "vlc"
    override val displayName = "libVLC 兜底"

    private val appCtx: Context = context.applicationContext
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    /** VLC 的 stop/release 是阻塞调用，必须在工作线程串行执行（事件线程/主线程调用会死锁） */
    private val vlcOps = Executors.newSingleThreadExecutor { r -> Thread(r, "otv-vlc-ops").apply { isDaemon = true } }
    private val _ui = MutableStateFlow(EngineUiState())
    override val uiState: StateFlow<EngineUiState> = _ui.asStateFlow()

    /** v1.17 IPTV 大缓冲档：network-caching 1.5s → 6s（远端源抖动平滑） */
    @Volatile private var largeBuffer = false

    // v1.19 并发修复：两字段在 vlcOps 单线程写、主线程 ticker/setLargeBufferPreferred 读，
    // 无 @Volatile 时 JMM 无 happens-before——ticker 可能看到过期 null/半构造引用
    @Volatile private var libvlc: LibVLC? = null
    @Volatile private var player: MediaPlayer? = null
    @Volatile private var currentUrl: String? = null
    private var ticker: Job? = null
    /** vout 只允许 attach 一次（2026-08-30 实测教训：直播结束追边重开时重复 attachViews
     *  抛 IllegalStateException「Can't set view when already attached」→ 重开失败卡 BUFFERING） */
    private var voutAttached = false

    override val renderView: View = TextureView(appCtx).apply {
        // 渲染层不参与焦点（遥控焦点全部留给 Compose 控制层，与 Media3 引擎一致）
        isFocusable = false
        isFocusableInTouchMode = false
    }

    override fun setLargeBufferPreferred(on: Boolean) {
        if (largeBuffer == on) return
        largeBuffer = on
        // LibVLC 参数在实例创建时固定：已建实例则标记重建（下次 prepare 生效）
        if (libvlc != null) {
            vlcOps.execute {
                runCatching {
                    player?.let { p ->
                        p.setEventListener(null)
                        p.stop()
                        runCatching { p.detachViews() }
                        p.release()
                    }
                    libvlc?.release()
                }
                player = null
                libvlc = null
                voutAttached = false
            }
        }
    }

    private fun ensureLibVlc(): LibVLC {
        libvlc?.let { return it }
        val options = arrayListOf(
            // 直播链路（经 127.0.0.1:8090 中继）抖动大：加大网络缓存换稳定；
            // v1.17 IPTV 远端源用 6s 大缓存档；
            // v1.22 足球直播兜底档 1500ms→3000ms：上游 CDN 瞬时抖动直接穿透 1.5s 缓存
            "--network-caching=${if (largeBuffer) 6000 else 3000}",
            // 关掉 VLC 的 mediacodec/iomx 硬解尝试：MuMu 等环境下这些 codec 就是故障源
            "--no-mediacodec-dr",
            "--no-omxil",
            "--no-omxil-dr",
            // 音频不做时间拉伸（变速语义对齐 Media3）
            "--no-audio-time-stretch",
        )
        return LibVLC(appCtx, options).also { libvlc = it }
    }

    private fun buildMedia(url: String): Media {
        val m = Media(ensureLibVlc(), android.net.Uri.parse(url))
        // 关键：禁用本媒体硬解 → 强制 VLC 自带 avcodec 软解（回退到本引擎的全部意义）
        m.setHWDecoderEnabled(false, false)
        return m
    }

    private val eventListener = MediaPlayer.EventListener { ev ->
        when (ev.type) {
            MediaPlayer.Event.Opening -> {
                _ui.value = _ui.value.copy(state = EnginePlayState.BUFFERING, errorMsg = null)
                OtvLog.i("vlc opening")
            }
            MediaPlayer.Event.Buffering -> {
                val pct = ev.buffering
                if (pct >= 100f) {
                    // Buffering 100% 只代表可用，出画面以 Playing/首帧为准
                    if (_ui.value.state != EnginePlayState.READY) {
                        _ui.value = _ui.value.copy(state = EnginePlayState.READY)
                    }
                } else if (_ui.value.state != EnginePlayState.ERROR) {
                    _ui.value = _ui.value.copy(state = EnginePlayState.BUFFERING)
                }
            }
            MediaPlayer.Event.Playing -> {
                _ui.value = _ui.value.copy(state = EnginePlayState.READY, isPlaying = true)
                OtvLog.i("vlc playing（画面输出中）")
            }
            // v1.15 首帧看门狗信号：vout 建立 = 视频输出管线就绪（软解路径必出画面）
            MediaPlayer.Event.Vout -> {
                _ui.value = _ui.value.copy(firstFrameRendered = true)
                OtvLog.i("vlc vout established（视频输出建立）")
            }
            MediaPlayer.Event.Paused -> _ui.value = _ui.value.copy(isPlaying = false)
            MediaPlayer.Event.EncounteredError -> {
                OtvLog.e("vlc error: EncounteredError url=${currentUrl?.take(90)}")
                _ui.value = _ui.value.copy(
                    state = EnginePlayState.ERROR,
                    isPlaying = false,
                    errorMsg = "VLC_ERROR: 播放失败（流不可用或格式异常）",
                )
            }
            MediaPlayer.Event.EndReached -> {
                OtvLog.w("vlc end reached（直播窗口结束/流被掐）")
                _ui.value = _ui.value.copy(state = EnginePlayState.ENDED, isPlaying = false)
            }
        }
    }

    private fun attachVout(p: MediaPlayer) {
        if (voutAttached) return
        val vout = p.getVLCVout()
        vout.setVideoView(renderView as TextureView)
        vout.addCallback(object : IVLCVout.Callback {
            override fun onSurfacesCreated(vout: IVLCVout) {}
            override fun onSurfacesDestroyed(vout: IVLCVout) {}
        })
        vout.attachViews()
        voutAttached = true
    }

    private fun startTicker() {
        ticker?.cancel()
        ticker = scope.launch {
            var beat = 0
            while (isActive) {
                player?.let { p ->
                    val time = p.time.coerceAtLeast(0)
                    val len = p.length
                    _ui.value = _ui.value.copy(
                        positionMs = time,
                        durationMs = if (len > 0) len else 0,
                        // VLC 不暴露正向缓冲；直播下恒报健康水位（续签热切换的保护条件）
                        bufferedAheadMs = if (_ui.value.isPlaying) 15_000L else _ui.value.bufferedAheadMs,
                    )
                    if (++beat % 20 == 0) {
                        val st = _ui.value
                        OtvLog.i("hb vlc ${st.state} playing=${st.isPlaying} pos=${st.positionMs / 1000}s")
                    }
                }
                delay(500)
            }
        }
    }

    override fun prepare(request: PrepareRequest) {
        currentUrl = request.url
        _ui.value = _ui.value.copy(
            state = EnginePlayState.BUFFERING, positionMs = 0, errorMsg = null,
            firstFrameRendered = false,   // 新媒体：首帧信号复位（首帧看门狗判定基准）
        )
        vlcOps.execute {
            runCatching {
                val p = player ?: createPlayer()
                p.setEventListener(eventListener)
                p.stop()
                p.media = buildMedia(request.url)
                attachVout(p)
                // v1.19 断点续播修复：旧版丢弃 request.startMs——Media3 引擎有 seekTo(startMs)
                // 而 VLC 没有，切 VLC 后点播续播/卡顿原位恢复全部从 0 重播。
                // play() 前 setTime 在起播前定位（等效 Media3 的 seekTo(startPos)）
                if (request.startMs > 0) p.time = request.startMs
                p.play()
            }.onFailure { OtvLog.e("vlc prepare failed: ${it.message}") }
        }
        startTicker()
    }

    private fun createPlayer(): MediaPlayer =
        MediaPlayer(ensureLibVlc()).also { player = it }

    override fun swapSource(url: String, autoplay: Boolean) {
        // VLC 无真正热切换：换源=重开（冻结约 1s，仅直播续签换签名时发生）。
        // autoplay=false 的暂停静默续签不会走到本引擎（PlayerViewModel 已拦：VLC 重开必播）
        OtvLog.i("vlc 换源（重开, autoplay=$autoplay）: ${url.take(100)}")
        prepare(PrepareRequest(url, 0L))
    }

    override fun seekToLiveEdge() {
        // 直播卡顿追边：VLC 对 HLS 直播重开即从直播边缘起播
        OtvLog.w("vlc 追直播边缘（重开当前源）")
        currentUrl?.let { prepare(PrepareRequest(it, 0L)) }
    }

    override fun setSoftwareDecoderPreferred(on: Boolean) {
        // 本引擎恒为软解，无操作（接口兼容）
    }

    override fun play() {
        vlcOps.execute {
            runCatching { player?.play() }
            // 乐观镜像（见 Media3Engine.play）：快速连按时 UI 读镜像不再拿旧值
            if (player != null) _ui.value = _ui.value.copy(isPlaying = true)
        }
    }

    override fun pause() {
        vlcOps.execute {
            runCatching { player?.pause() }
            if (player != null) _ui.value = _ui.value.copy(isPlaying = false)
        }
    }

    override fun seekTo(ms: Long) {
        vlcOps.execute { runCatching { player?.setTime(ms.coerceAtLeast(0)) } }
    }

    override fun setSpeed(v: Float) {
        vlcOps.execute { runCatching { player?.setRate(v) } }
        _ui.value = _ui.value.copy(speed = v)
    }

    override fun release() {
        scope.cancel()
        vlcOps.execute {
            runCatching {
                player?.let { p ->
                    p.setEventListener(null)
                    p.stop()
                    p.detachViews()
                    voutAttached = false
                    p.release()
                }
                player = null
                libvlc?.release()
                libvlc = null
            }
        }
    }
}
