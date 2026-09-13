package com.qiubo.optimaltv.ui.player

import com.qiubo.optimaltv.data.model.LineInfo

object PlaybackPolicy { const val SEEK_STEP_MS = 10_000L }
object EpisodeMenuPolicy {
    const val RANGE_SIZE = 10
    fun hasRanges(count: Int) = count >= 20
    fun rangeLabels(count: Int): List<String> = if (!hasRanges(count)) emptyList() else
        (0 until (count + RANGE_SIZE - 1) / RANGE_SIZE).map { p -> "第${p * RANGE_SIZE + 1}-${minOf(count, (p + 1) * RANGE_SIZE)}集" }
    fun episodeLabel(index: Int) = (index + 1).toString()
}
object VisibleVodLinePolicy {
    fun apply(lines: List<LineInfo>) = lines.take(5).mapIndexed { i, line -> line.copy(label = "信号源${i + 1}") }
}
