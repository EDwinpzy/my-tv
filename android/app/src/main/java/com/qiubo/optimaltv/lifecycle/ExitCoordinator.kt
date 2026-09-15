package com.qiubo.optimaltv.lifecycle

import android.app.Activity
import android.content.Intent
import android.os.Handler
import android.os.Looper
import com.qiubo.optimaltv.BackendService
import com.qiubo.optimaltv.OtvLog
import com.qiubo.optimaltv.announcement.AnnouncementManager
import com.qiubo.optimaltv.hotupdate.HotUpdateManager
import com.qiubo.optimaltv.playback.StreamDecryptServer

/** Explicit user exit is intentionally stronger than an ordinary background transition. */
object ExitCoordinator {
    fun exit(activity: Activity) {
        OtvLog.i("explicit exit: release playback helpers and backend")
        AppLifecycleManager.shutdown()
        AnnouncementManager.shutdown()
        HotUpdateManager.shutdown()
        StreamDecryptServer.shutdown()
        runCatching {
            activity.startService(
                Intent(activity, BackendService::class.java).setAction(BackendService.ACTION_SHUTDOWN)
            )
        }
        activity.finishAffinity()
        Handler(Looper.getMainLooper()).postDelayed({
            android.os.Process.killProcess(android.os.Process.myPid())
        }, 350L)
    }
}
