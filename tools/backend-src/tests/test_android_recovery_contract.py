import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]


class AndroidRecoveryContractTest(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_player_monitors_buffering_and_runs_shared_recovery_ladder(self):
        source = self.read("android/app/src/main/java/com/qiubo/optimaltv/ui/player/PlayerViewModel.kt")
        self.assertIn("EnginePlayState.BUFFERING", source[source.index("private fun startStallMonitor"):])
        self.assertIn("PlaybackRecoveryPolicy.action", source)
        self.assertIn("recoverPlaybackStall", source)
        renewal = source[source.index("private fun startLiveRenewal"):source.index("private fun writeBackLineUrl")]
        self.assertNotIn("if (s.playState != EnginePlayState.READY) continue", renewal)

    def test_decrypt_bridge_has_reset_and_shutdown_lifecycle(self):
        source = self.read("android/app/src/main/java/com/qiubo/optimaltv/playback/StreamDecryptServer.kt")
        self.assertIn("fun reset()", source)
        self.assertIn("fun shutdown()", source)
        self.assertIn("consecutiveTimeouts", source)

    def test_mobile_has_the_same_recovery_policy_and_buffering_observer(self):
        source = self.read("internal/mobile/app/src/main/java/com/qiubo/optimaltv/ui/player/PlayerViewModel.kt")
        self.assertIn("PlaybackRecoveryPolicy.action", source)
        self.assertIn("EnginePlayState.BUFFERING", source[source.index("private fun startStallMonitor"):])


if __name__ == "__main__":
    unittest.main()
