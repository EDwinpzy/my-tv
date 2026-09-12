package com.qiubo.optimaltv.license

import android.annotation.SuppressLint
import android.content.Context
import android.os.Build
import android.provider.Settings
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.qiubo.optimaltv.BuildConfig
import com.qiubo.optimaltv.OtvLog
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.PublicKey
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.text.SimpleDateFormat
import java.util.Base64
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.TimeUnit

private val Context.licenseStore by preferencesDataStore(name = "license")

/** 已激活状态（expiryAt == null 表示终身） */
data class LicenseActivated(
    val code: String,
    val plan: String,
    val days: Int,
    val expiryAt: Long?,
    val activatedAt: Long,
)

/** 门控状态机（方案 §4.1）：null = 尚未从本地加载完成 */
sealed interface LicenseState {
    data object NotActivated : LicenseState
    data class Activated(val data: LicenseActivated) : LicenseState
}

/** 激活调用结果 */
sealed interface ActivateResult {
    data object Ok : ActivateResult
    data class Error(val msg: String) : ActivateResult
}

/**
 * v1.17 卡密授权管理（公测版专用；内测版 LICENSE_ENABLED=false 时 init 直接返回，零行为）。
 *
 * 核心安全性质：
 * - 票据由本机私钥预签名（license_gen.py），云端/本地任何篡改都过不了 P-256 验签；
 * - 激活后离线可用，联网时静默复验实现吊销降级（方案 §4.3）；
 * - 时间防回拨：本地只记「见过的最大时间戳」，回拨 >48h 冻结计时，
 *   联网时用 activate 响应的 HTTP Date 头校准（方案 §4.2）。
 */
object LicenseManager {

    private object K {
        val CODE = stringPreferencesKey("code")
        val PLAN = stringPreferencesKey("plan")
        val DAYS = intPreferencesKey("days")
        val EXPIRY = longPreferencesKey("expiry_at")      // -1 = 终身（DataStore 无可空标量）
        val ACTIVATED_AT = longPreferencesKey("activated_at")
        val MAX_SEEN = longPreferencesKey("max_seen_ms")
        val LAST_VERIFY = longPreferencesKey("last_verify_ms")
    }

    /** 票面 plan → days（与 license_gen.py PLANS 一致，验签时强校验）。
     *  v1.20 新增 weekly 周卡（7 天，仅后台签发赠送、app 内不售卖）——此处必须
     *  同步，否则 7 天卡激活时 verifyTicket 校验 PLAN_DAYS 失败（E2）。 */
    val PLAN_DAYS = mapOf("monthly" to 30, "quarterly" to 90, "yearly" to 365, "lifetime" to 0, "weekly" to 7)

    /** 内嵌验签公钥（X509/SPKI DER 的 base64；由 tools/license_gen.py pubkey 派生） */
    private const val PUB_KEY_B64 =
        "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEwJd4v53jwXWpinnG1qgVU3D9gM0VvvEFB83Bm/sAEwTcFnISEOJu8DyvyiEW7q9fR9Si7M0afjbMt6k3IOw1hw=="

    private val CODE_RE = Regex("^OTV-[A-HJ-NP-Z2-9]{5}-[A-HJ-NP-Z2-9]{5}$")
    private const val DAY_MS = 86_400_000L
    private const val ROLLBACK_TOLERANCE_MS = 48 * 3600_000L
    private const val RENEW_BADGE_MS = 7 * DAY_MS   // 到期前 7 天顶栏续费角标
    private const val REVERIFY_INTERVAL_MS = 6 * 3600_000L

    private val _state = MutableStateFlow<LicenseState?>(null)
    val state: StateFlow<LicenseState?> = _state.asStateFlow()

    @Volatile private var maxSeenMs: Long = 0L
    @Volatile private var lastPersistMs: Long = 0L
    @Volatile private var inited = false
    private lateinit var appContext: Context

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val http = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    private val pubKey: PublicKey by lazy {
        KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(Base64.getDecoder().decode(PUB_KEY_B64)))
    }

    /** App.onCreate 调用；异步加载本地状态后触发静默复验 */
    fun init(context: Context) {
        if (!BuildConfig.LICENSE_ENABLED || inited) return
        inited = true
        appContext = context.applicationContext
        scope.launch {
            runCatching {
                val p = appContext.licenseStore.data.first()
                maxSeenMs = p[K.MAX_SEEN] ?: 0L
                lastPersistMs = maxSeenMs
                val code = p[K.CODE]
                if (code.isNullOrBlank()) {
                    _state.value = LicenseState.NotActivated
                } else {
                    _state.value = LicenseState.Activated(
                        LicenseActivated(
                            code = code,
                            plan = p[K.PLAN] ?: "monthly",
                            days = p[K.DAYS] ?: 30,
                            expiryAt = p[K.EXPIRY]?.takeIf { it >= 0 },
                            activatedAt = p[K.ACTIVATED_AT] ?: 0L,
                        )
                    )
                }
            }.onFailure { OtvLog.w("license load failed: ${it.message}") ; _state.value = LicenseState.NotActivated }
            touchClock(System.currentTimeMillis())
            val lastVerify = appContext.licenseStore.data.first()[K.LAST_VERIFY] ?: 0L
            if (lastVerify <= 0L || effNow() - lastVerify >= REVERIFY_INTERVAL_MS) {
                silentReverify()
            }
        }
    }

    // ---------------- 门控查询 ----------------

    /** 播放权限门控（统一播放入口调用） */
    fun isPremium(): Boolean {
        val st = _state.value
        if (BuildConfig.LICENSE_ENABLED.not()) return true   // 内测版恒真（防御性，正常不会走到）
        if (st !is LicenseState.Activated) return false
        val expiry = st.data.expiryAt ?: return true         // 终身
        touchClock(System.currentTimeMillis())
        return effNow() < expiry
    }

    /** 到期时间戳（终身为 null）；未激活/未加载返回 null */
    fun expiryAt(): Long? = (_state.value as? LicenseState.Activated)?.data?.expiryAt

    /** 剩余天数（终身返回 Int.MAX_VALUE；未激活返回 0） */
    fun daysLeft(): Int {
        val st = _state.value as? LicenseState.Activated ?: return 0
        val expiry = st.data.expiryAt ?: return Int.MAX_VALUE
        return ((expiry - effNow()) / DAY_MS).toInt().coerceAtLeast(0)
    }

    /** 是否终身会员 */
    fun isLifetime(): Boolean = (_state.value as? LicenseState.Activated)?.data?.expiryAt == null

    /** 到期前 7 天（或已过期）→ 顶栏续费角标 */
    fun needRenewBadge(): Boolean {
        val st = _state.value as? LicenseState.Activated ?: return false
        val expiry = st.data.expiryAt ?: return false
        return effNow() > expiry - RENEW_BADGE_MS
    }

    /** 防回拨时间：回拨超容差时冻结在 maxSeen（方案 §4.2），联网后由 HTTP Date 校准追上 */
    fun effNow(): Long {
        val now = System.currentTimeMillis()
        return if (now < maxSeenMs - ROLLBACK_TOLERANCE_MS) maxSeenMs else maxOf(now, maxSeenMs)
    }

    private fun touchClock(now: Long) {
        if (now > maxSeenMs) maxSeenMs = now
        // 节流持久化：≥10 分钟推进才落盘（每次门控都写 DataStore 太频繁）
        if (maxSeenMs - lastPersistMs >= 600_000L) {
            lastPersistMs = maxSeenMs
            scope.launch { runCatching { appContext.licenseStore.edit { it[K.MAX_SEEN] = maxSeenMs } } }
        }
    }

    // ---------------- 激活 ----------------

    /** 设备指纹：ANDROID_ID + 机型哈希（方案 §4.1；重装不占新名额的口径见云侧幂等） */
    @SuppressLint("HardwareIds")
    fun deviceId(): String {
        val aid = runCatching {
            Settings.Secure.getString(appContext.contentResolver, Settings.Secure.ANDROID_ID)
        }.getOrNull() ?: "unknown"
        val seed = "$aid|${Build.MANUFACTURER}|${Build.MODEL}"
        val d = MessageDigest.getInstance("SHA-256").digest(seed.toByteArray(Charsets.UTF_8))
        return d.take(16).joinToString("") { "%02x".format(it) }
    }

    suspend fun activate(rawCode: String): ActivateResult {
        if (!inited) return ActivateResult.Error("授权模块未初始化")
        // 宽进严出：输码页键盘无「OTV-」前缀键，用户只输后 10 位（带/不带横杠均可）；
        // 统一归一为 OTV-XXXXX-XXXXX 再走 CODE_RE 强校验（charset 仍剔除 I/O/0/1）
        val compact = rawCode.trim().uppercase().filter { it.isLetterOrDigit() }
        val code = when {
            compact.length == 13 && compact.startsWith("OTV") ->
                "OTV-" + compact.substring(3, 8) + "-" + compact.substring(8)
            compact.length == 10 -> "OTV-" + compact.substring(0, 5) + "-" + compact.substring(5)
            else -> ""
        }
        if (!CODE_RE.matches(code)) return ActivateResult.Error("卡密格式不正确（OTV-XXXXX-XXXXX）")
        val resp = callEndpoint(code, deviceId()) ?: return ActivateResult.Error("网络不可用，请稍后重试")
        when (resp.ret) {
            0 -> {
                val t = resp.ticket ?: return ActivateResult.Error("服务端返回异常，请稍后重试")
                if (!verifyTicket(t, code)) return ActivateResult.Error("票据校验失败（E2）")
                applyTicket(t)
                OtvLog.i("license activated: plan=${t.plan}")
                return ActivateResult.Ok
            }
            402 -> return ActivateResult.Error("该卡密绑定设备数已满（一码 2 台）")
            403 -> return ActivateResult.Error("该卡密已被封禁")
            404 -> return ActivateResult.Error("卡密不存在，请检查输入")
            400 -> return ActivateResult.Error("卡密格式不正确（OTV-XXXXX-XXXXX）")
            else -> return ActivateResult.Error("激活失败（${resp.ret}），请稍后重试")
        }
    }

    /** 应用已验签票据；同码重复激活幂等（不叠加），换码续费叠加（方案 §2.5） */
    private suspend fun applyTicket(t: Ticket) {
        val now = effNow()
        val prev = (_state.value as? LicenseState.Activated)?.data
        val newExpiry: Long?
        val baseActivatedAt: Long
        if (prev != null && prev.code == t.code) {
            // 同码（重装后再激活 / 静默复验刷新）：票面不变，到期与激活时间保持
            newExpiry = prev.expiryAt
            baseActivatedAt = prev.activatedAt
        } else if (t.days == 0) {
            newExpiry = null                       // 终身买断
            baseActivatedAt = now
        } else {
            // 续费叠加：newExpiry = max(当前到期, now) + days；已是终身则保持终身
            val prevExpiry = prev?.expiryAt
            newExpiry = if (prev != null && prevExpiry == null) null
            else maxOf(now, prevExpiry ?: 0L) + t.days * DAY_MS
            baseActivatedAt = prev?.activatedAt ?: now
        }
        val data = LicenseActivated(t.code, t.plan, t.days, newExpiry, baseActivatedAt)
        _state.value = LicenseState.Activated(data)
        if (now > maxSeenMs) maxSeenMs = now
        appContext.licenseStore.edit { p ->
            p[K.CODE] = data.code
            p[K.PLAN] = data.plan
            p[K.DAYS] = data.days
            p[K.EXPIRY] = data.expiryAt ?: -1L
            p[K.ACTIVATED_AT] = data.activatedAt
            p[K.MAX_SEEN] = maxSeenMs
            // 显式激活与成功静默复验都已完成云端吊销检查；6 小时内无需重复查库。
            p[K.LAST_VERIFY] = now
        }
        lastPersistMs = maxSeenMs
    }

    private suspend fun clearLocal() {
        _state.value = LicenseState.NotActivated
        appContext.licenseStore.edit { it.clear() }
    }

    // ---------------- 启动静默复验（方案 §4.3） ----------------

    private suspend fun silentReverify() {
        val cur = (_state.value as? LicenseState.Activated)?.data ?: return
        val resp = withTimeoutOrNull(12_000) { callEndpoint(cur.code, deviceId()) } ?: return
        // HTTP Date 校准可信时间（无需 NTP 权限）
        resp.serverDateMs?.let { if (it > maxSeenMs) { maxSeenMs = it; lastPersistMs = maxSeenMs } }
        when {
            resp.ret == 0 && resp.ticket != null && verifyTicket(resp.ticket, cur.code) -> {
                // 幂等刷新（同码保持到期），顺带完成吊销检查
                applyTicket(resp.ticket)
            }
            resp.ret == 403 -> {
                OtvLog.w("license banned by server → downgrade")
                clearLocal()
            }
            else -> Unit   // 断网/超时/404 忽略：离线照常可用
        }
    }

    // ---------------- 票据验签（本地 P-256，方案 §2.3） ----------------

    private data class Ticket(
        val v: Int, val code: String, val plan: String, val days: Int,
        val issued: String, val nonce: String, val sig: String,
    )

    private fun parseTicket(jo: JSONObject): Ticket? = runCatching {
        Ticket(
            v = jo.getInt("v"),
            code = jo.getString("code"),
            plan = jo.getString("plan"),
            days = jo.getInt("days"),
            issued = jo.getString("issued"),
            nonce = jo.getString("nonce"),
            sig = jo.getString("sig"),
        )
    }.getOrNull()

    /** canonical 串与 license_gen.py 一致：v|code|plan|days|issued|nonce */
    private fun verifyTicket(t: Ticket, inputCode: String): Boolean {
        if (t.v != 1) return false
        if (t.code != inputCode) return false
        if (PLAN_DAYS[t.plan] != t.days) return false
        if (t.issued.length != 10 || t.nonce.length < 8 || t.sig.length < 64) return false
        val canonical = "1|${t.code}|${t.plan}|${t.days}|${t.issued}|${t.nonce}"
        return try {
            val sig = Base64.getDecoder().decode(t.sig)
            val verifier = Signature.getInstance("SHA256withECDSA")
            verifier.initVerify(pubKey)
            verifier.update(canonical.toByteArray(Charsets.UTF_8))
            verifier.verify(sig)
        } catch (e: Exception) {
            OtvLog.w("ticket verify error: ${e.message}")
            false
        }
    }

    // ---------------- 端点调用 ----------------

    private data class EndpointResp(
        val ret: Int, val ticket: Ticket?, val msg: String?, val serverDateMs: Long?,
    )

    // 挂起 + IO 调度：调用方可能在主线程（输码页 rememberCoroutineScope）——
    // 同步 execute() 会 NetworkOnMainThreadException，被 runCatching 吞成「网络不可用」
    private suspend fun callEndpoint(code: String, deviceId: String): EndpointResp? = withContext(Dispatchers.IO) {
        runCatching {
            val body = JSONObject().put("code", code).put("deviceId", deviceId).toString()
                .toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url(BuildConfig.LICENSE_ENDPOINT).post(body).build()
            http.newCall(req).execute().use { r ->
                val dateMs = r.header("Date")?.let(::parseHttpDate)
                val text = r.body?.string().orEmpty()
                val jo = runCatching { JSONObject(text) }.getOrNull()
                    ?: return@use EndpointResp(-1, null, "bad_json", dateMs)
                EndpointResp(jo.optInt("ret", -1), jo.optJSONObject("ticket")?.let(::parseTicket), jo.optString("msg"), dateMs)
            }
        }.getOrNull()
    }

    private fun parseHttpDate(s: String): Long? = runCatching {
        val fmt = SimpleDateFormat("EEE, dd MMM yyyy HH:mm:ss 'GMT'", Locale.US)
        fmt.timeZone = TimeZone.getTimeZone("UTC")
        fmt.parse(s)?.let { Date(it.time).time } ?: null
    }.getOrNull()
}
