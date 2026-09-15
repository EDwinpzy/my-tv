package com.qiubo.optimaltv.playback

enum class PlaybackKind { LIVE, VOD }

enum class RecoveryAction {
    RELOAD_CURRENT,
    REFRESH_CURRENT,
    SWITCH_SOURCE,
    RECREATE_ENGINE,
    RESET_RUNTIME,
    GIVE_UP,
}

/** Pure recovery ladder shared by TV/mobile player coordinators. */
object PlaybackRecoveryPolicy {
    const val STALL_THRESHOLD_MS = 8_000L
    private const val RESUME_REWIND_MS = 2_000L

    fun isStalled(durationMs: Long): Boolean = durationMs >= STALL_THRESHOLD_MS

    fun action(kind: PlaybackKind, attempt: Int): RecoveryAction = when (kind) {
        PlaybackKind.LIVE -> when (attempt) {
            0 -> RecoveryAction.REFRESH_CURRENT
            1 -> RecoveryAction.SWITCH_SOURCE
            2 -> RecoveryAction.RECREATE_ENGINE
            3 -> RecoveryAction.RESET_RUNTIME
            else -> RecoveryAction.GIVE_UP
        }
        PlaybackKind.VOD -> when (attempt) {
            0 -> RecoveryAction.RELOAD_CURRENT
            1 -> RecoveryAction.REFRESH_CURRENT
            2 -> RecoveryAction.SWITCH_SOURCE
            3 -> RecoveryAction.RECREATE_ENGINE
            else -> RecoveryAction.GIVE_UP
        }
    }

    fun resumePosition(positionMs: Long): Long = (positionMs - RESUME_REWIND_MS).coerceAtLeast(0L)

    class Generation {
        private var current = 0L

        fun next(): Long = ++current
        fun accepts(value: Long): Boolean = value == current
    }
}

