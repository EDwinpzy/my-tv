package com.qiubo.optimaltv.mobileui

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.click
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import com.qiubo.optimaltv.data.model.Episode
import com.qiubo.optimaltv.data.model.VodItem
import com.qiubo.optimaltv.ui.components.DetailActionButton
import com.qiubo.optimaltv.ui.components.MobileUiTags
import com.qiubo.optimaltv.ui.components.PortraitPlayerControls
import com.qiubo.optimaltv.ui.detail.shouldShowEpisodePicker
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

class MobileDetailPlayerComponentsTest {
    @get:Rule
    val rule = createAndroidComposeRule<MobileUiHarnessActivity>()

    @Before
    fun resetScene() {
        MobileUiHarness.scene = null
    }

    @Test
    fun detailButtonsDispatchIndependentActions() {
        var play = 0
        var favorite = 0
        MobileUiHarness.scene = {
            Row(Modifier.fillMaxWidth()) {
                DetailActionButton("立即播放", true, true, 0.7f, MobileUiTags.DetailPlay) { play++ }
                DetailActionButton("☆ 收藏", false, true, 0.7f, MobileUiTags.DetailFavorite) { favorite++ }
            }
        }
        rule.waitForIdle()

        rule.onNodeWithTag(MobileUiTags.DetailPlay).performClick()
        rule.onNodeWithTag(MobileUiTags.DetailFavorite).performClick()
        rule.runOnIdle {
            assertEquals(1, play)
            assertEquals(1, favorite)
        }
    }

    @Test
    fun moviePlaybackVersionsStayHiddenWhileSeriesEpisodesRemain() {
        val versions = listOf(
            Episode(0, "HD中字", ""),
            Episode(1, "HD国语", ""),
            Episode(2, "正片", ""),
        )
        val movie = VodItem("movie", "hhkan", "电影", "hhkan:1", episodes = versions)
        val series = VodItem("series", "hhkan", "剧集", "hhkan:2", episodes = versions)

        assertFalse(shouldShowEpisodePicker(movie))
        assertTrue(shouldShowEpisodePicker(series))
    }

    @Test
    fun portraitPlayerControlsDispatchPlayFullscreenMoreAndSeek() {
        var play = 0
        var fullscreen = 0
        var more = 0
        var seekTo = -1L
        MobileUiHarness.scene = {
            PortraitPlayerControls(
                title = "自动化测试影片",
                meta = "2025 / 中国 / 剧情",
                positionMs = 2_000,
                durationMs = 10_000,
                isLive = false,
                isPlaying = true,
                onSeek = { seekTo = it },
                onTogglePlay = { play++ },
                onFullscreen = { fullscreen++ },
                onMore = { more++ },
            )
        }
        rule.waitForIdle()

        rule.onNodeWithText("暂停").assertExists()
        rule.onNodeWithText("-0:08").assertExists()
        rule.onNodeWithTag(MobileUiTags.PlayerSeek).performTouchInput { click(center) }
        rule.onNodeWithTag(MobileUiTags.PlayerPlayPause).performClick()
        rule.onNodeWithTag(MobileUiTags.PlayerFullscreen).performClick()
        rule.onNodeWithTag(MobileUiTags.PlayerMore).performClick()
        rule.runOnIdle {
            assertTrue("点击进度条中点应定位到约 5 秒", seekTo in 4_900L..5_100L)
            assertEquals(1, play)
            assertEquals(1, fullscreen)
            assertEquals(1, more)
        }
    }

    @Test
    fun livePortraitControlsHideMoreAndShowLiveLabel() {
        MobileUiHarness.scene = {
            PortraitPlayerControls("CCTV-5", "", 0, 0, true, true, {}, {}, {}, {})
        }
        rule.waitForIdle()

        rule.onNodeWithText("直播", useUnmergedTree = true).assertExists()
        rule.onNodeWithTag(MobileUiTags.PlayerMore).assertDoesNotExist()
    }

    @Test
    fun zeroDurationNeverProducesInvalidSeek() {
        var seekTo = -1L
        MobileUiHarness.scene = {
            PortraitPlayerControls("冷启动", "", 0, 0, false, false, { seekTo = it }, {}, {}, {})
        }
        rule.waitForIdle()

        rule.onNodeWithTag(MobileUiTags.PlayerSeek).performTouchInput { click(center) }
        rule.runOnIdle { assertEquals(-1L, seekTo) }
    }
}
