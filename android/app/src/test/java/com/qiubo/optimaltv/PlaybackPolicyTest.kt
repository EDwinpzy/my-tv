package com.qiubo.optimaltv

import com.qiubo.optimaltv.data.model.LineInfo
import com.qiubo.optimaltv.ui.player.EpisodeMenuPolicy
import com.qiubo.optimaltv.ui.player.PlaybackPolicy
import com.qiubo.optimaltv.ui.player.VisibleVodLinePolicy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PlaybackPolicyTest {
    @Test fun episodeMenuUsesTwentyBoundaryAndTenEpisodeRanges() {
        assertFalse(EpisodeMenuPolicy.hasRanges(19))
        assertTrue(EpisodeMenuPolicy.hasRanges(20))
        assertEquals(listOf("第1-10集", "第11-20集"), EpisodeMenuPolicy.rangeLabels(20))
        assertEquals("3", EpisodeMenuPolicy.episodeLabel(2))
    }

    @Test fun vodLinesExposeOnlyFiveAnonymousSignals() {
        val lines = (1..8).map { LineInfo("v$it", "private-$it", "u$it") }
        assertEquals(listOf("信号源1", "信号源2", "信号源3", "信号源4", "信号源5"),
            VisibleVodLinePolicy.apply(lines).map { it.label })
    }

    @Test fun seekStepIsTenSeconds() = assertEquals(10_000L, PlaybackPolicy.SEEK_STEP_MS)
}
