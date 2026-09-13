package com.qiubo.optimaltv.ui.player

import com.qiubo.optimaltv.data.model.LineInfo

object PlaybackPolicy { const val SEEK_STEP_MS = 10_000L }

object EpisodeMenuPolicy {
    const val RANGE_SIZE = 10
    fun hasRanges(count: Int) = count >= 20
    fun rangeLabels(count: Int): List<String> = if (!hasRanges(count)) emptyList() else
        (0 until (count + RANGE_SIZE - 1) / RANGE_SIZE).map { page ->
            val from = page * RANGE_SIZE + 1
            val to = minOf(count, from + RANGE_SIZE - 1)
            "第${from}-${to}集"
        }
    fun episodeLabel(index: Int) = (index + 1).toString()
}

object VisibleVodLinePolicy {
    fun apply(lines: List<LineInfo>): List<LineInfo> = lines.take(5).mapIndexed { index, line ->
        line.copy(label = "信号源${index + 1}")
    }
}
