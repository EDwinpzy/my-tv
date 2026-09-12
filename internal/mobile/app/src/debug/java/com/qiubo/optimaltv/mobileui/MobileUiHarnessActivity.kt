package com.qiubo.optimaltv.mobileui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** 只承载真实生产组件的轻量容器；测试场景从 androidTest 注入。 */
object MobileUiHarness {
    var scene by mutableStateOf<(@Composable () -> Unit)?>(null)
}

class MobileUiHarnessActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MobileUiHarness.scene?.invoke() }
    }
}
