package com.qiubo.optimaltv.mobileui

import android.app.Application
import android.content.Context
import androidx.test.runner.AndroidJUnitRunner

/** 测试专用空壳 Application：组件测试不启动后端、热更新或许可证流程。 */
class MobileUiTestRunner : AndroidJUnitRunner() {
    override fun newApplication(cl: ClassLoader, name: String, context: Context): Application =
        super.newApplication(cl, MobileUiTestApp::class.java.name, context)
}

class MobileUiTestApp : Application()
