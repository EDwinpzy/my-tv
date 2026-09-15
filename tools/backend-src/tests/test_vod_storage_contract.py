"""云端代码目录只读：影视缓存/索引必须能回落到可写位置。

线上 200406「Process exited unexpectedly」的根因就是这里：云函数把 /var/user
只读挂载，VOD 初始化在 /var/user/.cache 上 mkdir 抛 EROFS，异常又逃出了请求
处理器，于是每个 /vod/* 与 /api/search 请求都直接把进程带走。
"""
import pathlib
import sys
import tempfile
import unittest


BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import proxy  # noqa: E402


class VodStorageContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_prefers_the_code_dir_when_it_is_writable(self):
        target = pathlib.Path(self.tmp.name) / "cache"
        chosen = proxy._vod_data_dir(preferred=target)
        self.assertEqual(chosen, target)
        self.assertTrue(chosen.is_dir())

    def test_falls_back_to_a_writable_dir_when_the_code_dir_is_read_only(self):
        # 用「路径的父级是文件」模拟不可写挂载点：mkdir 抛 NotADirectoryError(OSError)。
        blocker = pathlib.Path(self.tmp.name) / "readonly-mount"
        blocker.write_text("not a directory", encoding="utf-8")
        blocked = blocker / "cache"

        chosen = proxy._vod_data_dir(preferred=blocked)

        self.assertNotEqual(chosen, blocked)
        self.assertTrue(chosen.is_dir())
        probe = chosen / "probe.bin"
        probe.write_bytes(b"ok")
        self.assertEqual(probe.read_bytes(), b"ok")

    def test_vod_service_init_sits_inside_the_try_block(self):
        """初始化失败要回 503，不能让异常逃出处理器把整条响应丢掉。"""
        source = (BACKEND / "proxy.py").read_text(encoding="utf-8")
        block = source[source.index("    def _vod_api"):]
        block = block[:block.index("\n    def ", 1)]
        self.assertLess(block.index("try:"), block.index("service = _get_vod_service()"))


if __name__ == "__main__":
    unittest.main()
