package com.qiubo.optimaltv.data.cast

import android.util.Log
import android.util.Xml
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.xmlpull.v1.XmlPullParser
import java.net.DatagramPacket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.MulticastSocket
import java.net.NetworkInterface
import java.net.SocketTimeoutException
import java.net.URL

/**
 * v1.21 DLNA 投屏（2026-09-04）：SSDP 发现局域网 AVTransport 渲染器 + SOAP 播放控制。
 *
 * 零三方依赖：SSDP 用 MulticastSocket（设备应答为单播回包，无需 WifiManager 组播锁），
 * SOAP 用 HttpURLConnection，设备描述 XML 用系统 XmlPullParser。
 *
 * 投屏 URL 适配（[CastNet.castableUrl]）：本机中继地址 http://127.0.0.1:8090/... 电视
 * 无法访问，需改写为本机局域网 IP（EmbeddedBackend 绑定 0.0.0.0，电视经局域网拉同源
 * 中继流，签名轮换/防盗链由中继内部自愈，与手机本地播放同链路）。公网直连线路
 * （IPTV/点播直链）原样投出。
 */

/** 发现到的 DLNA 渲染器（电视/盒子/投影） */
data class DlnaDevice(
    val uuid: String,
    val name: String,
    /** AVTransport 控制端点绝对 URL */
    val controlUrl: String,
    /** 设备描述 XML 地址（SSDP LOCATION） */
    val location: String,
)

object DlnaDiscovery {
    private const val TAG = "OTV"
    private const val SSDP_ADDR = "239.255.255.250"
    private const val SSDP_PORT = 1900

    /** 局域网设备扫描：M-SEARCH 两种 ST（部分电视只应答其一）→ 收 LOCATION → 拉描述 XML。
     *  返回按 name 排序的去重设备表；无设备返回空表（不抛异常——UI 层提示"未发现设备"）。 */
    suspend fun scan(timeoutMs: Long = 4500L): List<DlnaDevice> = withContext(Dispatchers.IO) {
        val locations = LinkedHashSet<String>()
        runCatching {
            MulticastSocket().use { sock ->
                sock.soTimeout = 1200
                sock.broadcast = true
                // 一个包里拼两份 M-SEARCH（AVTransport:1 精准 + ssdp:all 兜底）
                val query = listOf(
                    "urn:schemas-upnp-org:service:AVTransport:1",
                    "ssdp:all",
                ).joinToString("\r\n") { st ->
                    "M-SEARCH * HTTP/1.1\r\n" +
                        "HOST: $SSDP_ADDR:$SSDP_PORT\r\n" +
                        "MAN: \"ssdp:discover\"\r\n" +
                        "MX: 2\r\n" +
                        "ST: $st\r\n\r\n"
                }.toByteArray()
                sock.send(DatagramPacket(query, query.size, InetAddress.getByName(SSDP_ADDR), SSDP_PORT))
                val deadline = System.currentTimeMillis() + timeoutMs
                val rx = ByteArray(4096)
                while (System.currentTimeMillis() < deadline) {
                    val pkt = DatagramPacket(rx, rx.size)
                    try {
                        sock.receive(pkt)
                    } catch (_: SocketTimeoutException) {
                        continue
                    }
                    val text = String(pkt.data, 0, pkt.length, Charsets.UTF_8)
                    Regex("(?im)^LOCATION:\\s*(\\S+)").find(text)?.groupValues?.get(1)
                        ?.let { locations.add(it) }
                }
            }
        }.onFailure { Log.w(TAG, "SSDP 扫描失败: ${it.message}") }

        // 拉取设备描述（逐台，单台失败跳过——扫描容错优先于速度）
        locations.mapNotNull { loc -> runCatching { parseDevice(loc) }.getOrNull() }
            .sortedBy { it.name }
    }

    /** 设备描述 XML → DlnaDevice（friendlyName + AVTransport controlURL 绝对化） */
    private fun parseDevice(location: String): DlnaDevice? {
        val conn = URL(location).openConnection() as HttpURLConnection
        conn.connectTimeout = 4000
        conn.readTimeout = 4000
        conn.useCaches = false
        conn.connect()
        val raw = conn.inputStream.use { it.readBytes() }
        var name = ""
        var controlUrl: String? = null
        var serviceType = ""
        var inFriendly = false
        var inControlUrl = false
        var inServiceType = false
        val parser = Xml.newPullParser()
        parser.setInput(raw.inputStream(), Charsets.UTF_8.name())
        var event = parser.eventType
        while (event != XmlPullParser.END_DOCUMENT) {
            when (event) {
                XmlPullParser.START_TAG -> when (parser.name?.lowercase()) {
                    "servicetype" -> inServiceType = true
                    "controlurl" -> inControlUrl = true
                    "service" -> { serviceType = ""; controlUrl = null }
                    "friendlyname" -> inFriendly = true
                }
                XmlPullParser.TEXT -> when {
                    inServiceType -> serviceType = parser.text?.trim().orEmpty()
                    inControlUrl && controlUrl == null -> controlUrl = parser.text?.trim()
                    inFriendly && name.isBlank() -> name = parser.text?.trim().orEmpty()
                }
                XmlPullParser.END_TAG -> when (parser.name?.lowercase()) {
                    "servicetype" -> inServiceType = false
                    "controlurl" -> inControlUrl = false
                    "friendlyname" -> inFriendly = false
                    // service 结束：AVTransport 的 controlURL 锁定为设备端点
                    "service" -> if (controlUrl != null && serviceType.contains("AVTransport", true)) {
                        val abs = runCatching { URL(URL(location), controlUrl!!).toString() }.getOrNull()
                        if (abs != null) {
                            val uuid = Regex("(?i)uuid:([0-9a-f-]+)").find(location)?.groupValues?.get(1)
                                ?: location
                            return DlnaDevice(
                                uuid = uuid, name = name.ifBlank { "未知设备" },
                                controlUrl = abs, location = location)
                        }
                    }
                }
            }
            event = parser.next()
        }
        return null
    }
}

/** AVTransport SOAP 控制（SetAVTransportURI / Play / Pause / Stop / Seek / GetPositionInfo） */
object DlnaControl {
    private const val NS = "urn:schemas-upnp-org:service:AVTransport:1"

    /** 投放并播放（SetAVTransportURI + Play）。失败返回 false（UI 提示换设备/重试）。 */
    suspend fun setUriAndPlay(dev: DlnaDevice, url: String, title: String): Boolean = withContext(Dispatchers.IO) {
        val didl = "<DIDL-Lite xmlns=\"urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/\" " +
            "xmlns:dc=\"http://purl.org/dc/elements/1.1/\" " +
            "xmlns:upnp=\"urn:schemas-upnp-org:metadata-1-0/upnp/\">" +
            "<item id=\"0\" parentID=\"-1\" restricted=\"1\">" +
            "<dc:title>${xmlEsc(title)}</dc:title>" +
            "<upnp:class>object.item.videoItem</upnp:class></item></DIDL-Lite>"
        val ok = soap(
            dev.controlUrl, "SetAVTransportURI",
            "<InstanceID>0</InstanceID>" +
                "<CurrentURI>${xmlEsc(url)}</CurrentURI>" +
                "<CurrentURIMetaData>${xmlEsc(didl)}</CurrentURIMetaData>")
        if (!ok) return@withContext false
        soap(dev.controlUrl, "Play", "<InstanceID>0</InstanceID><Speed>1</Speed>")
    }

    suspend fun play(dev: DlnaDevice) = withContext(Dispatchers.IO) {
        soap(dev.controlUrl, "Play", "<InstanceID>0</InstanceID><Speed>1</Speed>")
    }

    suspend fun pause(dev: DlnaDevice) = withContext(Dispatchers.IO) {
        soap(dev.controlUrl, "Pause", "<InstanceID>0</InstanceID>")
    }

    suspend fun stop(dev: DlnaDevice) = withContext(Dispatchers.IO) {
        soap(dev.controlUrl, "Stop", "<InstanceID>0</InstanceID>")
    }

    /** REL_TIME 定位（秒） */
    suspend fun seek(dev: DlnaDevice, seconds: Long) = withContext(Dispatchers.IO) {
        soap(
            dev.controlUrl, "Seek",
            "<InstanceID>0</InstanceID><Unit>REL_TIME</Unit><Target>${hms(seconds)}</Target>")
    }

    /** 位置查询 → (当前秒, 总秒)；解析不到返回 null（直播常无 TrackDuration）。
     *  元素可能带命名空间前缀（u:RelTime），正则统一容忍。 */
    suspend fun position(dev: DlnaDevice): Pair<Long, Long>? = withContext(Dispatchers.IO) {
        val body = soapRaw(dev.controlUrl, "GetPositionInfo", "<InstanceID>0</InstanceID>")
            ?: return@withContext null
        val rel = Regex("(?i)<(?:\\w+:)?RelTime>([^<]*)</(?:\\w+:)?RelTime>").find(body)?.groupValues?.get(1).orEmpty()
        val dur = Regex("(?i)<(?:\\w+:)?TrackDuration>([^<]*)</(?:\\w+:)?TrackDuration>").find(body)?.groupValues?.get(1).orEmpty()
        val relS = parseHms(rel)
        if (relS == null && dur.isBlank()) null else Pair(relS ?: 0L, parseHms(dur) ?: 0L)
    }

    private fun soap(controlUrl: String, action: String, args: String): Boolean =
        soapRaw(controlUrl, action, args) != null

    private fun soapRaw(controlUrl: String, action: String, args: String): String? = runCatching {
        val body = "<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"no\"?>" +
            "<s:Envelope xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\" " +
            "s:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\">" +
            "<s:Body><u:$action xmlns:u=\"$NS\">$args</u:$action></s:Body></s:Envelope>"
        val conn = URL(controlUrl).openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.connectTimeout = 6000
        conn.readTimeout = 8000
        conn.doOutput = true
        conn.useCaches = false
        conn.setRequestProperty("Content-Type", "text/xml; charset=\"utf-8\"")
        conn.setRequestProperty("SOAPACTION", "\"$NS#$action\"")
        conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        val code = conn.responseCode
        if (code !in 200..299) {
            val err = runCatching { conn.errorStream?.readBytes()?.toString(Charsets.UTF_8)?.take(160) }.getOrNull()
            Log.w("OTV", "DLNA $action → HTTP $code $err")
            null
        } else {
            conn.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }
        }
    }.getOrNull()

    private fun hms(sec: Long): String {
        val s = sec.coerceAtLeast(0)
        return "%d:%02d:%02d".format(s / 3600, s % 3600 / 60, s % 60)
    }

    /** "1:23:45.123" 形态解析（DLNA 时间常带小数毫秒尾巴） */
    private fun parseHms(t: String): Long? {
        val m = Regex("^(\\d+):(\\d{1,2}):(\\d{1,2})").find(t.trim()) ?: return null
        return m.groupValues[1].toLong() * 3600 + m.groupValues[2].toLong() * 60 + m.groupValues[3].toLong()
    }

    private fun xmlEsc(s: String) = s
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace("\"", "&quot;").replace("'", "&apos;")
}

/** 本机网络工具：局域网 IPv4 与投屏 URL 改写 */
object CastNet {
    /** 本机局域网 IPv4（接口须 up 且非环回）；无则 null（投屏不可用） */
    fun lanIp(): String? = runCatching {
        NetworkInterface.getNetworkInterfaces().asSequence()
            .filter { it.isUp && !it.isLoopback }
            .flatMap { nif -> nif.inetAddresses.asSequence() }
            .map { it.hostAddress ?: "" }
            .firstOrNull { it.count { c -> c == '.' } == 3 && !it.startsWith("127.") }
    }.getOrNull()

    /**
     * 投屏地址改写：本机中继 http://127.0.0.1:8090 → 局域网 IP:8090（电视可访问）。
     * 公网直连线路原样返回；无局域网 IP 返回 null（不可投）。
     */
    fun castableUrl(playUrl: String): String? {
        val ip = lanIp() ?: return null
        if (!playUrl.contains("127.0.0.1:8090")) return playUrl
        return "http://$ip:8090" + playUrl.removePrefix("http://127.0.0.1:8090")
    }
}
