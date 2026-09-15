"""影视 tab 三栏契约：分类 id 必须是「豆瓣口径」解析，否则片库恒空。

2026-09-15 线上实测事故：目录切豆瓣后分类 id 变成 `douban:movie` 形态，但首页仍按旧的
`removePrefix("hhkan:").toIntOrNull()` 解析 → 恒为 null → 三栏恒空，影视 tab 一直显示
「暂无内容」（数据其实已由 libBlocks 拉到 libBlocksFlow）。这里锁住「统一走
VodRepository.categoryCid」的契约。
"""
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
ANDROID = ROOT / "android/app/src/main/java/com/qiubo/optimaltv"
MOBILE = ROOT / "internal/mobile/app/src/main/java/com/qiubo/optimaltv"


class VodCategoryCidContractTest(unittest.TestCase):
    def test_repository_exposes_shared_resolver(self):
        src = (ANDROID / "data/repo/VodRepository.kt").read_text(encoding="utf-8")
        self.assertIn("fun categoryCid(categoryId: String): Int?", src)
        # 必须同时认豆瓣口径与旧的 hhkan:<数字> 形态
        self.assertIn('removePrefix("douban:")', src)
        self.assertIn('removePrefix("hhkan:")', src)

    def test_home_screen_uses_shared_resolver(self):
        src = (ANDROID / "ui/home/HomeScreen.kt").read_text(encoding="utf-8")
        self.assertIn("VodRepository.categoryCid(selCatId)", src)
        self.assertNotIn('selCatId.removePrefix("hhkan:").toIntOrNull()', src)

    def test_cover_preload_uses_shared_resolver(self):
        src = (ANDROID / "App.kt").read_text(encoding="utf-8")
        self.assertIn("VodRepository.categoryCid(cid)", src)
        self.assertNotIn('cid.removePrefix("hhkan:").toIntOrNull()', src)

    def test_mobile_tree_matches_tv_tree(self):
        """共享层两工程字节级一致（tools/sync_shared.py 监管；HomeScreen 属 UI 层各自维护）。"""
        for rel in ("data/repo/VodRepository.kt", "App.kt"):
            tv = (ANDROID / rel).read_text(encoding="utf-8")
            mb = (MOBILE / rel).read_text(encoding="utf-8")
            self.assertEqual(tv, mb, f"{rel} 两工程不一致，请跑 tools/sync_shared.py")

    def test_mobile_home_screen_uses_shared_resolver(self):
        src = (MOBILE / "ui/home/HomeScreen.kt").read_text(encoding="utf-8")
        self.assertIn("VodRepository.categoryCid(selCatId)", src)
        self.assertNotIn('selCatId.removePrefix("hhkan:").toIntOrNull()', src)


if __name__ == "__main__":
    unittest.main()
