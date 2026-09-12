# 豆瓣影视目录与可管理播放源 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 TV、移动端和网页版以设备端豆瓣刮削结果生成影视目录与筛选，并通过后台可发布的播放源配置自动匹配、测速、择优和失败换源。

**Architecture:** 新增彼此隔离的豆瓣目录模块与播放源模块，由现有 `proxy.py` 暴露统一 `/vod/*` 接口。后台通过草稿/发布版本管理源配置，App 从现有公网热更新函数获取配置版本并在设备端原子更新；豆瓣目录、匹配和线路质量历史均保留在设备本地。

**Tech Stack:** Python 3.11 标准库、Kotlin 1.9.24、Jetpack Compose、OkHttp 4.12、Media3 1.5.1、原生 HTML/CSS/JavaScript、Node.js CloudBase 函数、PostgreSQL RPC、Python `unittest`、JUnit 4、Android instrumentation tests。

**Spec:** `docs/superpowers/specs/2026-09-12-douban-catalog-vod-source-management-design.md`

## Global Constraints

- 豆瓣片单与元数据在每台设备的内置 Python 后端刮削，不建立集中式豆瓣目录服务。
- 现有公网云服务只保存和分发影视源草稿/发布配置，并继续承担原有热更新职责。
- TV、移动端、网页版行为与文案保持一致；共享文件通过 `python tools/sync_shared.py --source android --target internal/mobile` 同步后，再用无参数检查模式验证。
- 所有生产 Python 只能使用标准库，保持 Chaquopy Python 3.11 和 CloudBase Python 3.9 可运行语法。
- 新增外部 URL 必须经过现有公网 DNS/重定向 SSRF 防护；失败配置不得替换客户端最近一次有效配置。
- 现有收藏、历史和返回焦点数据不得删除；`hhkan:*` 记录只在可靠匹配时迁移为 `douban:*`。
- 所有行为改动遵循 RED → GREEN → REFACTOR；每个生产函数必须先由失败测试定义。
- 当前工作区没有 `.git`，不得擅自初始化仓库；计划中的版本控制检查点以测试结果和修改文件清单代替 commit。

## File Structure

- `tools/backend-src/douban_catalog.py`：豆瓣目录、筛选、搜索、详情、缓存与快照回退。
- `tools/backend-src/douban_snapshot.json`：首次安装和豆瓣不可用时的最小目录快照。
- `tools/backend-src/vod_sources.py`：源模型、配置加载、适配器发现、影片匹配、线路探测与排序。
- `tools/backend-src/vod_sources.default.json`：当前九个源的内置默认发布配置。
- `tools/backend-src/proxy.py`：仅负责 HTTP 路由和既有接口兼容，不承载新增业务算法。
- `tools/backend-src/tests/fixtures/douban/`：固定豆瓣 HTML/JSON fixture。
- `tools/backend-src/tests/test_douban_catalog.py`：豆瓣解析、映射和缓存测试。
- `tools/backend-src/tests/test_vod_sources.py`：源发现、匹配、排名、配置原子更新测试。
- `tools/backend-src/tests/test_vod_api.py`：统一 `/vod/*` HTTP 契约测试。
- `tools/vod_sources_migration.sql`：影视源草稿、发布版本和 RPC。
- `tools/admin_server.py`：受登录保护的影视源草稿、测试、试看解析与发布接口。
- `tools/admin.html`：影视源管理页、测试弹窗和试看播放器。
- `cloudfunctions/hotupdate/index.js`：公开的影视源版本检查与配置下载响应。
- `android/app/src/main/java/com/qiubo/optimaltv/data/source/VodApiSource.kt`：统一 `/vod/*` 客户端解析。
- `android/app/src/main/java/com/qiubo/optimaltv/data/repo/VodRepository.kt`：目录状态、旧 ID 迁移和播放源异步匹配。
- `android/app/src/main/java/com/qiubo/optimaltv/ui/all/AllScreen.kt`：豆瓣片库筛选。
- `android/app/src/main/java/com/qiubo/optimaltv/ui/detail/DetailViewModel.kt`：正在查找/暂无片源状态。
- `android/app/src/main/java/com/qiubo/optimaltv/ui/detail/DetailScreen.kt`：详情状态文案与按钮。
- `android/app/src/main/java/com/qiubo/optimaltv/ui/player/PlayerViewModel.kt`：自动择优与失败换源。
- `tools/backend-src/www/app.js`：网页版统一 VOD API、筛选和播放状态。
- `tools/build_backend_zip.py`、`tools/build_web_function.py`、`tools/sync_shared.py`：新增后端文件打包与三端同步。

---

### Task 1: 豆瓣目录、筛选与缓存模块

**Files:**
- Create: `tools/backend-src/douban_catalog.py`
- Create: `tools/backend-src/douban_snapshot.json`
- Create: `tools/backend-src/tests/fixtures/douban/explore_movie.json`
- Create: `tools/backend-src/tests/fixtures/douban/subject_1292052.html`
- Create: `tools/backend-src/tests/test_douban_catalog.py`

**Interfaces:**
- Consumes: `urllib.request`, `html`, `json`, `re`, `pathlib`, `threading`, `time` from the Python standard library.
- Produces: `DoubanCatalog.home(category)`, `filters(category)`, `show(category, genre, region, year, rating, sort, page)`, `search(query, page)`, `detail(douban_id)`, each returning JSON-serializable dictionaries with `douban:{id}` item IDs.

- [ ] **Step 1: Write failing parser and taxonomy tests**

```python
class DoubanCatalogTest(unittest.TestCase):
    def test_movie_explore_maps_to_stable_subject(self):
        payload = fixture_json("explore_movie.json")
        item = douban_catalog.parse_explore(payload)[0]
        self.assertEqual(item["id"], "douban:1292052")
        self.assertEqual(item["title"], "肖申克的救赎")
        self.assertEqual(item["category"], "movie")

    def test_short_category_rejects_plain_animated_short(self):
        self.assertFalse(douban_catalog.is_short_drama({"genres": ["动画", "短片"], "tags": []}))
        self.assertTrue(douban_catalog.is_short_drama({"genres": ["剧情"], "tags": ["网络短剧"]}))

    def test_detail_uses_douban_metadata(self):
        item = douban_catalog.parse_subject_html(fixture_text("subject_1292052.html"), "1292052")
        self.assertEqual(item["year"], "1994")
        self.assertEqual(item["rating"], 9.7)
        self.assertIn("弗兰克·德拉邦特", item["directors"])
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_douban_catalog.py" -v`

Expected: import failure for missing `douban_catalog`.

- [ ] **Step 3: Implement the normalized model and pure parsers**

```python
HOME_SECTION_NAMES = ("最近热门", "最新上映", "豆瓣高分")
CATEGORY_VALUES = {"movie", "tv", "anime", "variety", "short"}
SUBJECT_FIELDS = (
    "id", "douban_id", "title", "original_title", "aliases", "year",
    "category", "genres", "regions", "season", "rating", "rating_count",
    "summary", "directors", "actors", "poster_url", "backdrop_url", "release_date",
)
```

Map product categories to `movie`, `tv`, animation-within-movie/tv, variety/reality-show-within-tv, and strict short-drama tags. Return home sections in exact order `最近热门`, `最新上映`, `豆瓣高分`.

- [ ] **Step 4: Add failing cache fallback tests**

```python
def test_failed_refresh_keeps_last_success(self):
    cache = douban_catalog.JsonDiskCache(self.tmp)
    cache.put("home:movie", {"sections": [1]}, fetched_at=100)
    self.assertEqual(cache.get_stale("home:movie", now=999999)["sections"], [1])

def test_first_run_uses_bundled_snapshot(self):
    catalog = douban_catalog.DoubanCatalog(fetch=lambda *_: (_ for _ in ()).throw(OSError()), snapshot=self.snapshot)
    self.assertTrue(catalog.home("movie")["stale"])
```

- [ ] **Step 5: Run cache tests and verify RED**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_douban_catalog.py" -v`

Expected: missing `JsonDiskCache` and constructor dependencies.

- [ ] **Step 6: Implement request coalescing, TTLs and snapshot fallback**

```python
TTL = {"home": 21600, "filters": 86400, "detail": 604800, "search": 1800}
CACHE_SCHEMA = 1
CACHE_ENVELOPE_KEYS = {"schema", "fetched_at", "value"}
```

Use a per-key condition variable so concurrent identical requests share one upstream fetch. Write cache files as `.tmp`, flush, then `os.replace`; never store failed/empty responses over successful data.

- [ ] **Step 7: Run the complete Task 1 suite**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_douban_catalog.py" -v`

Expected: all tests pass with no live network dependency.

- [ ] **Step 8: Record checkpoint**

Run: `Get-Item tools/backend-src/douban_catalog.py,tools/backend-src/douban_snapshot.json,tools/backend-src/tests/test_douban_catalog.py | Select-Object FullName,Length,LastWriteTime`

Expected: all three files exist and are non-empty.

---

### Task 2: 播放源注册、适配器、匹配与排名

**Files:**
- Create: `tools/backend-src/vod_sources.py`
- Create: `tools/backend-src/vod_sources.default.json`
- Create: `tools/backend-src/tests/test_vod_sources.py`
- Modify: `tools/backend-src/hhkan.py`

**Interfaces:**
- Consumes: Task 1 subject dictionaries and existing `hhkan` parsing primitives.
- Produces: `SourceRegistry`, `HhkanAdapter`, `MacCmsAdapter`, `match_score(subject, candidate)`, `rank_lines(lines, history)`, and `SourceRegistry.resolve_subject(subject, episode_index)`.

- [ ] **Step 1: Write failing source configuration and discovery tests**

```python
def test_default_registry_contains_current_nine_sources(self):
    registry = vod_sources.SourceRegistry.load_default()
    self.assertEqual([s.name for s in registry.sources],
        ["好好看", "暴风", "极速", "金鹰", "虎牙", "豪华", "红牛", "速播", "360"])

def test_discover_maccms_home_normalizes_api(self):
    result = vod_sources.discover_source("https://example.test", fake_fetch)
    self.assertEqual(result.adapter_type, "macms_json")
    self.assertEqual(result.api_url, "https://example.test/api.php/provide/vod/")

def test_discovery_rejects_private_redirect(self):
    with self.assertRaises(vod_sources.UnsafeSourceUrl):
        vod_sources.discover_source("https://example.test", redirects_to_127_0_0_1)
```

- [ ] **Step 2: Run discovery tests and verify RED**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_vod_sources.py" -v`

Expected: import failure for missing `vod_sources`.

- [ ] **Step 3: Implement immutable source models and adapter discovery**

```python
@dataclass(frozen=True)
class VodSource:
    id: str
    name: str
    site_url: str
    api_url: str
    adapter_type: str
    enabled: bool
    revision: int

class SourceAdapter(Protocol):
    def search(self, subject: dict) -> list[dict]:
        """Return normalized candidates with title, aliases, year, category and season."""
    def detail(self, candidate: dict) -> list[dict]:
        """Return normalized line groups with stable source-local IDs and episodes."""
    def resolve(self, line: dict, episode_index: int) -> dict:
        """Return name, url and request headers for exactly one episode."""
```

Move MacCMS request/parsing behavior out of `proxy.py` without changing its URL safety rules. Keep a dedicated `HhkanAdapter` for current mirrors and a shared `MacCmsAdapter` for JSON/XML sources.

- [ ] **Step 4: Write failing match-score boundary tests**

```python
def test_alias_exact_year_type_and_season_auto_matches(self):
    self.assertEqual(vod_sources.match_score(subject, candidate), 100)

def test_same_title_wrong_year_does_not_auto_match(self):
    candidate["year"] = "2004"
    self.assertLess(vod_sources.match_score(subject, candidate), 80)

def test_punctuation_difference_still_matches(self):
    subject["title"] = "蜘蛛侠：英雄无归"
    candidate["title"] = "蜘蛛侠英雄无归"
    self.assertGreaterEqual(vod_sources.match_score(subject, candidate), 80)
```

- [ ] **Step 5: Implement normalization and the exact 100-point confidence model**

```python
AUTO_MATCH_THRESHOLD = 80
TITLE_SEPARATORS = re.compile(r"[^\w\u4e00-\u9fff]+")

def normalize_title(value: str) -> str:
    return TITLE_SEPARATORS.sub("", value or "").casefold()
```

Award 60 for exact normalized title/original-title/alias overlap, 20 for exact year or 10 for ±1 year, 10 for category, and 10 for matching season or both absent. Reject candidates below 80 from automatic playback.

- [ ] **Step 6: Write failing line-ranking tests**

```python
def test_rank_prefers_quality_latency_and_reliability(self):
    ranked = vod_sources.rank_lines([
        {"id": "slow-1080", "height": 1080, "latency_ms": 5000, "alive": True},
        {"id": "fast-1080", "height": 1080, "latency_ms": 800, "alive": True},
        {"id": "fast-720", "height": 720, "latency_ms": 500, "alive": True},
        {"id": "dead-4k", "height": 2160, "latency_ms": 200, "alive": False},
    ], {"fast-1080": 0.9, "slow-1080": 1.0, "fast-720": 1.0})
    self.assertEqual([x["id"] for x in ranked], ["fast-1080", "fast-720", "slow-1080", "dead-4k"])
```

- [ ] **Step 7: Implement probing, ranking and local 20-attempt history**

```python
from typing import Optional

QUALITY_SCORES = {2160: 100, 1080: 85, 720: 65}

def quality_score(height: int) -> int:
    return 100 if height >= 2160 else 85 if height >= 1080 else 65 if height >= 720 else 35 if height > 0 else 20

def latency_score(milliseconds: Optional[int]) -> int:
    if milliseconds is None: return 0
    return 100 if milliseconds <= 1000 else 80 if milliseconds <= 3000 else 50 if milliseconds <= 6000 else 20
```

Compute `0.50 * quality + 0.30 * latency + 0.20 * reliability`; mark confirmed dead lines unavailable and last. Store only the latest 20 booleans per line in device-local JSON.

- [ ] **Step 8: Run the Task 2 suite**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_vod_sources.py" -v`

Expected: all source, SSRF, matching and ranking tests pass.

- [ ] **Step 9: Record checkpoint**

Run: `Get-Item tools/backend-src/vod_sources.py,tools/backend-src/vod_sources.default.json,tools/backend-src/tests/test_vod_sources.py | Select-Object FullName,Length,LastWriteTime`

Expected: all files are present and non-empty.

---

### Task 3: 统一 `/vod/*` 后端接口与旧接口兼容

**Files:**
- Modify: `tools/backend-src/proxy.py`
- Create: `tools/backend-src/tests/test_vod_api.py`
- Modify: `tools/backend-src/tests/test_hhkan_catalog_contract.py`

**Interfaces:**
- Consumes: `douban_catalog.DoubanCatalog` and `vod_sources.SourceRegistry`.
- Produces: `GET /vod/home`, `/vod/filters/{category}`, `/vod/show/{category}`, `/vod/search`, `/vod/detail/{douban_id}`, `/vod/play/{douban_id}/{line_id}/{episode}` and `/vod/sources/status`.

- [ ] **Step 1: Write failing HTTP contract tests**

```python
def test_vod_home_uses_douban_cards(self):
    payload = fetch("/vod/home?category=movie")
    self.assertEqual([s["name"] for s in payload["sections"]],
                     ["最近热门", "最新上映", "豆瓣高分"])
    self.assertTrue(all(i["id"].startswith("douban:") for s in payload["sections"] for i in s["items"]))

def test_detail_keeps_subject_when_no_source_matches(self):
    payload = fetch("/vod/detail/1292052")
    self.assertEqual(payload["id"], "douban:1292052")
    self.assertEqual(payload["source_state"], "unavailable")
    self.assertEqual(payload["sources"], [])

def test_detail_distinguishes_matching_from_unavailable(self):
    self.assertEqual(fetch("/vod/detail/1292052?defer_sources=1")["source_state"], "matching")
```

- [ ] **Step 2: Run endpoint tests and verify RED**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_vod_api.py" -v`

Expected: `/vod/*` returns 404.

- [ ] **Step 3: Add a thin router that delegates to the two new modules**

```python
VOD_ROUTES = {
    "/vod/home": "home",
    "/vod/search": "search",
    "/vod/sources/status": "source_status",
}
VOD_PREFIX_ROUTES = {
    "/vod/filters/": "filters",
    "/vod/show/": "show",
    "/vod/detail/": "detail",
    "/vod/play/": "play",
}
```

Keep all parsing, matching and ranking implementation outside `proxy.py`. Start source matching only for detail/play requests; directory endpoints must never contact playback sources.

- [ ] **Step 4: Preserve `/hhkan/*` for one compatibility cycle**

Route existing calls without changing their response schema, but remove them as the source of new UI cards. Keep `/hhkan/play/*` working for legacy saved history and existing hot-update clients.

- [ ] **Step 5: Run new and legacy backend tests**

Run: `python -m unittest discover -s tools/backend-src/tests -v`

Expected: all tests pass, including legacy hhkan outage and source-pool contracts.

- [ ] **Step 6: Smoke-test routes locally**

Run: `python tools/backend-src/proxy.py 8091`

In a second terminal run: `Invoke-RestMethod http://127.0.0.1:8091/vod/home?category=movie | ConvertTo-Json -Depth 6`

Expected: three named sections containing `douban:*` IDs; stop the local server after the response.

---

### Task 4: 云端影视源草稿、发布版本与客户端配置检查

**Files:**
- Create: `tools/vod_sources_migration.sql`
- Modify: `cloudfunctions/hotupdate/index.js`
- Create: `tools/backend-src/tests/test_vod_source_publish_contract.py`

**Interfaces:**
- Consumes: authenticated admin RPC calls and anonymous hotupdate function requests.
- Produces: PostgreSQL RPCs `vod_source_admin_list`, `vod_source_admin_save`, `vod_source_admin_delete`, `vod_source_admin_publish`, `vod_source_public_check`; public `POST /vod-sources/check` returning `{ret, hasUpdate, version, sha256, config}`.

- [ ] **Step 1: Write failing migration contract tests**

```python
def test_migration_exposes_required_rpc_without_table_grants(self):
    sql = MIGRATION.read_text(encoding="utf-8")
    for name in ("vod_source_admin_list", "vod_source_admin_save", "vod_source_admin_delete",
                 "vod_source_admin_publish", "vod_source_public_check"):
        self.assertIn("function " + name, sql.lower())
    self.assertNotIn("grant select on vod_source_drafts to anon", sql.lower())

def test_publish_is_versioned_and_atomic(self):
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    self.assertIn("for update", sql)
    self.assertIn("vod_source_versions", sql)
    self.assertIn("sha256", sql)
```

- [ ] **Step 2: Run migration tests and verify RED**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_vod_source_publish_contract.py" -v`

Expected: missing migration file.

- [ ] **Step 3: Implement tables and security-definer RPCs**

```sql
create table if not exists vod_source_drafts (
  id uuid primary key,
  name text not null,
  site_url text not null,
  api_url text not null,
  adapter_type text not null check (adapter_type in ('hhkan','macms_json','macms_xml')),
  enabled boolean not null default true,
  updated_at timestamptz not null default now()
);
create table if not exists vod_source_versions (
  version bigint primary key,
  config jsonb not null,
  sha256 text not null,
  published_at timestamptz not null default now()
);
```

Seed the current nine sources idempotently. Publish inside one transaction, require at least one enabled source, generate the next version under row lock, and grant only RPC execution—never direct anonymous table access.

- [ ] **Step 4: Write failing CloudBase route contract test**

```python
def test_hotupdate_exposes_vod_source_check(self):
    js = HOTUPDATE.read_text(encoding="utf-8")
    self.assertIn('url.pathname === "/vod-sources/check"', js)
    self.assertIn('rpc("vod_source_public_check"', js)
```

- [ ] **Step 5: Implement `/vod-sources/check` with two-minute coalesced caching**

```javascript
if (req.method === "POST" && url.pathname === "/vod-sources/check") {
  const localVersion = toInt(body.version, 0);
  const out = await vodSourceCheckCached(localVersion);
  return sendJson(res, out);
}
```

Reuse existing request-body limits, CORS policy and pending-promise cache pattern. Return the full immutable config only when the version differs.

- [ ] **Step 6: Run contract and syntax checks**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_vod_source_publish_contract.py" -v`

Run: `node --check cloudfunctions/hotupdate/index.js`

Expected: all tests pass and Node reports no syntax errors.

---

### Task 5: 后台影视源管理、指定影片测试与试看

**Files:**
- Modify: `tools/admin_server.py`
- Modify: `tools/admin.html`
- Create: `tools/backend-src/tests/test_vod_source_admin_contract.py`

**Interfaces:**
- Consumes: Task 4 admin RPCs and Task 2 adapter/test functions.
- Produces: authenticated POST routes `/api/vod_source_list`, `/api/vod_source_save`, `/api/vod_source_delete`, `/api/vod_source_discover`, `/api/vod_source_test`, `/api/vod_source_publish`; the test response `{grade, summary, matched, preview_url}`.

- [ ] **Step 1: Write failing authenticated route tests**

```python
def test_source_mutations_are_registered_behind_session_gate(self):
    source = ADMIN_SERVER.read_text(encoding="utf-8")
    for route in ("vod_source_list", "vod_source_save", "vod_source_delete",
                  "vod_source_discover", "vod_source_test", "vod_source_publish"):
        self.assertIn('"/api/' + route + '"', source)

def test_test_grade_boundaries(self):
    self.assertEqual(admin_server.vod_test_grade(80), "优秀")
    self.assertEqual(admin_server.vod_test_grade(60), "良好")
    self.assertEqual(admin_server.vod_test_grade(40), "一般")
    self.assertEqual(admin_server.vod_test_grade(39), "不可用")
```

- [ ] **Step 2: Run backend tests and verify RED**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_vod_source_admin_contract.py" -v`

Expected: missing routes and `vod_test_grade`.

- [ ] **Step 3: Implement admin handlers and bounded source testing**

```python
def vod_test_grade(score: int) -> str:
    return "优秀" if score >= 80 else "良好" if score >= 60 else "一般" if score >= 40 else "不可用"

def h_vod_source_test(d):
    return {
        "grade": vod_test_grade(d["score"]),
        "summary": d["summary"],
        "matched": d["matched"],
        "preview_url": d.get("preview_url", ""),
    }
```

Require admin session for every route. Clamp title to 120 characters, episode to 1–9999, and the whole test to 20 seconds. Do not mutate draft or publish state during a test.

- [ ] **Step 4: Write failing UI contract tests**

```python
def test_admin_has_draft_publish_and_per_source_test_controls(self):
    html = ADMIN_HTML.read_text(encoding="utf-8")
    self.assertIn('data-tab="vod-sources"', html)
    self.assertIn('id="btn-vod-source-publish"', html)
    self.assertIn('id="vod-source-test-veil"', html)
    self.assertIn('id="vod-source-preview"', html)
    self.assertIn("未发布变更", html)
```

- [ ] **Step 5: Implement the admin page using incumbent visual tokens**

```javascript
const VOD_SOURCE_ROUTES = {
  list: "vod_source_list", save: "vod_source_save", delete: "vod_source_delete",
  discover: "vod_source_discover", test: "vod_source_test", publish: "vod_source_publish"
};
const VOD_TEST_GRADES = ["优秀", "良好", "一般", "不可用"];
```

Add one navigation tab, a source table, edit modal and test modal. Disable “立即推送” when `dirtyCount === 0`; close/escape must pause the `<video>`, detach Hls.js and clear its URL. Reuse the existing IPTV preview relay and Hls.js dependency rather than adding a second player library.

- [ ] **Step 6: Run admin tests and local browser verification**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_vod_source_admin_contract.py" -v`

Run: `python tools/admin_server.py`

Open: `http://127.0.0.1:8765/`

Expected: login succeeds; “影视源” shows nine rows; edit creates a dirty marker; test accepts a title and reports one of four grades; preview opens and stops on close; publish clears the dirty count.

- [ ] **Step 7: Run the UI detector once after edits**

Run: `node C:\Users\63054\.agents\skills\ui-design\impeccable\scripts\detect.mjs --json tools/admin.html`

Expected: no high-severity accessibility, overflow or interaction findings remain.

---

### Task 6: Android TV 与移动端统一 VOD 客户端

**Files:**
- Create: `android/app/src/main/java/com/qiubo/optimaltv/data/source/VodApiSource.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/data/model/Models.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/data/repo/VodRepository.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/all/AllScreen.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/detail/DetailViewModel.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/detail/DetailScreen.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/player/PlayerViewModel.kt`
- Create: `android/app/src/test/java/com/qiubo/optimaltv/data/repo/DoubanVodPolicyTest.kt`
- Modify: `internal/mobile/app/src/androidTest/java/com/qiubo/optimaltv/mobileui/MobileVodComponentsTest.kt`

**Interfaces:**
- Consumes: Task 3 `/vod/*` responses.
- Produces: `VodApiSource`, `SourceAvailability.MATCHING|AVAILABLE|UNAVAILABLE`, `douban:*` models, new filter query mapping and ordered `LineInfo` lists.

- [ ] **Step 1: Write failing JVM policy and parsing tests**

```kotlin
@Test fun `douban ids are accepted as catalog origin`() {
    assertTrue(VodIdPolicy.isCatalogId("douban:1292052"))
    assertFalse(VodIdPolicy.isCatalogId("mcms:1:20"))
}

@Test fun `source state distinguishes matching and unavailable`() {
    assertEquals(SourceAvailability.MATCHING, SourceAvailability.fromWire("matching"))
    assertEquals(SourceAvailability.UNAVAILABLE, SourceAvailability.fromWire("unavailable"))
}
```

- [ ] **Step 2: Run JVM tests and verify RED**

Run: `cd android; .\gradlew.bat testDebugUnitTest --tests "*DoubanVodPolicyTest"`

Expected: missing `VodIdPolicy` and `SourceAvailability`.

- [ ] **Step 3: Implement `VodApiSource` and stable models**

```kotlin
enum class SourceAvailability { MATCHING, AVAILABLE, UNAVAILABLE;
    companion object {
        fun fromWire(value: String) = when (value) {
            "available" -> AVAILABLE
            "unavailable" -> UNAVAILABLE
            else -> MATCHING
        }
    }
}

object VodIdPolicy {
    fun isCatalogId(id: String) = id.startsWith("douban:")
}

object VodRoutes {
    fun home(category: String) = "/vod/home?category=$category"
    fun filters(category: String) = "/vod/filters/$category"
    fun detail(id: String) = "/vod/detail/${id.removePrefix("douban:")}"
}
```

Parse all absent arrays as empty and all absent numeric values safely. Do not expose upstream source IDs as catalog IDs.

- [ ] **Step 4: Replace repository catalog calls and migrate old IDs conservatively**

Implement repository methods with these exact signatures: `suspend fun resolveLegacyId(oldId: String, title: String, year: String): String?` and `suspend fun playbackDetailReady(doubanId: String): DetailInfo`. The first returns a new ID only for one unique title+year search hit; the second requests a non-deferred detail and returns only after `sourceState` is `AVAILABLE` or `UNAVAILABLE`.

Use `/vod/home`, `/vod/filters`, `/vod/show`, `/vod/search` and `/vod/detail`; keep `/hhkan/play` only for unresolved legacy history. Migrate only a unique title+year hit. Preserve the old entry if zero or multiple hits occur.

- [ ] **Step 5: Update filters and detail empty/loading states**

Replace the six filter rows with `类别、类型、地区、年份、评分、排序`; map sort values to `hot`, `new`, `rating`. Render “正在查找片源” while matching and a disabled “暂无片源” control only after the backend reports unavailable.

- [ ] **Step 6: Write failing player failover test around a pure selector**

```kotlin
@Test fun `failed active line advances to next ranked line`() {
    val next = PlaybackLineSelector.nextAfterFailure(listOf("a", "b", "c"), "a", setOf("a"))
    assertEquals("b", next)
}
```

- [ ] **Step 7: Implement automatic failover without leaving the player**

```kotlin
object PlaybackLineSelector {
    fun nextAfterFailure(rankedIds: List<String>, activeId: String?, failed: Set<String>): String? {
        val start = rankedIds.indexOf(activeId).coerceAtLeast(-1) + 1
        return rankedIds.drop(start).firstOrNull { it !in failed }
    }
}
```

On prepare/manifest/decoder failure, record the failed line, show “当前线路不可用，正在切换”, request the next line, and preserve episode/progress. Exhaustion produces the existing fatal state. Manual source selection clears only the current automatic attempt state.

- [ ] **Step 8: Run TV unit tests and synchronize shared sources**

Run: `cd android; .\gradlew.bat testDebugUnitTest`

Run: `python tools/sync_shared.py --source android --target internal/mobile`

Run: `python tools/sync_shared.py`

Expected: all JVM tests pass and TV/mobile shared files have identical hashes.

- [ ] **Step 9: Build both Android targets sequentially**

Run: `cd android; .\gradlew.bat assembleDebug`

After it finishes run: `cd internal\mobile; .\gradlew.bat assembleDebug`

Expected: both builds complete successfully; never run the two Gradle builds concurrently.

---

### Task 7: 网页版豆瓣目录、筛选和播放器状态

**Files:**
- Modify: `tools/backend-src/www/app.js`
- Modify: `tools/backend-src/www/index.html`
- Modify: `tools/backend-src/www/style.css`
- Create: `tools/backend-src/tests/test_web_douban_contract.py`

**Interfaces:**
- Consumes: Task 3 `/vod/*` endpoints.
- Produces: `douban:*` catalog navigation, six-row filter panel, source matching state, unavailable state and ordered source playback.

- [ ] **Step 1: Write failing static web contract tests**

```python
def test_web_uses_vod_api_and_douban_filters(self):
    app = APP.read_text(encoding="utf-8")
    self.assertIn('"/vod/home?category="', app)
    self.assertIn('"评分"', app)
    self.assertIn('[["hot", "热门"], ["new", "最新上映"], ["rating", "豆瓣高分"]]', app)
    self.assertNotIn('["lang", "语言"', app)

def test_web_renders_matching_and_unavailable_separately(self):
    app = APP.read_text(encoding="utf-8")
    self.assertIn("正在查找片源", app)
    self.assertIn("暂无片源", app)
```

- [ ] **Step 2: Run web contract tests and verify RED**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_web_douban_contract.py" -v`

Expected: assertions fail because current web code uses `/hhkan/*` and language filters.

- [ ] **Step 3: Migrate catalog and detail requests**

```javascript
const VOD_CATEGORIES = [
  ["movie", "电影"], ["tv", "电视剧"], ["anime", "动漫"],
  ["variety", "综艺"], ["short", "短剧"]
];
const VOD_SORTS = [["hot", "热门"], ["new", "最新上映"], ["rating", "豆瓣高分"]];
```

Use `/vod/*` for home, filters, show, search, detail and play. Preserve SWR rendering, request cancellation and responsive three-column portrait behavior. Remove the separate asynchronous `/api/douban` overlay because base detail data is already canonical豆瓣 data.

- [ ] **Step 4: Render no-source and matching states**

Disable play only for `source_state === "unavailable"`; display a loading label for `matching`. Keep source chips ordered exactly as returned by the backend so all three clients share the same ranking.

- [ ] **Step 5: Run web tests and syntax check**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_web_douban_contract.py" -v`

Run: `node --check tools/backend-src/www/app.js`

Expected: tests pass and JavaScript syntax is valid.

- [ ] **Step 6: Browser smoke test desktop and portrait**

Run local backend, open `/web/`, verify the five categories, three sections, six filters, detail matching state, unavailable state and successful playback at desktop width and 390×844 portrait.

Expected: no horizontal overflow; filters remain usable by touch; cards remain three columns in portrait; preview playback uses the first ranked source.

---

### Task 8: 打包、热更新覆盖与项目验收

**Files:**
- Modify: `tools/build_backend_zip.py`
- Modify: `tools/build_web_function.py`
- Modify: `tools/build_hhkan_snapshot.py`
- Modify: `tools/admin_server.py` (`HU_REQUIRED_ENTRIES`)
- Modify: `docs/项目文档.md`
- Modify: `docs/版本史.md`
- Modify: `docs/测试记录.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: deployable backend zip, updated cloud web function, current default snapshots and reproducible test evidence.

- [ ] **Step 1: Write failing packaging contract assertions**

Add to `test_vod_api.py`:

```python
def test_backend_packaging_requires_new_vod_modules(self):
    admin = (ROOT / "tools/admin_server.py").read_text(encoding="utf-8")
    build = (ROOT / "tools/build_backend_zip.py").read_text(encoding="utf-8")
    for name in ("douban_catalog.py", "douban_snapshot.json", "vod_sources.py", "vod_sources.default.json"):
        self.assertIn(name, admin)
        self.assertIn(name, build)
```

- [ ] **Step 2: Run packaging test and verify RED**

Run: `python -m unittest discover -s tools/backend-src/tests -p "test_vod_api.py" -v`

Expected: new files are absent from required-entry lists.

- [ ] **Step 3: Add all new files to backend, web-function and hot-update builds**

```python
BACKEND_FILES = [
    "proxy.py", "hhkan.py", "scraper.py", "team_backdrop.py",
    "douban_catalog.py", "douban_snapshot.json",
    "vod_sources.py", "vod_sources.default.json",
]
```

Make the same file set authoritative in build scripts and `HU_REQUIRED_ENTRIES`. Replace `build_hhkan_snapshot.py` behavior or add its豆瓣 branch so release preparation refreshes `douban_snapshot.json` without removing the legacy hhkan snapshot needed by old clients.

- [ ] **Step 4: Run the full automated verification matrix**

Run: `python -m unittest discover -s tools/backend-src/tests -v`

Run: `node --check tools/backend-src/www/app.js`

Run: `node --check cloudfunctions/hotupdate/index.js`

Run: `python tools/sync_shared.py`

Run: `cd android; .\gradlew.bat testDebugUnitTest assembleDebug`

After completion run: `cd internal\mobile; .\gradlew.bat testDebugUnitTest assembleDebug`

Expected: every command exits zero with no new warnings attributable to this feature.

- [ ] **Step 5: Run bounded live-source acceptance tests**

Use one current sample in each category plus one known unavailable title. From the admin page test at least好好看 and two MacCMS sources; confirm grade, short summary, preview start and cleanup. On Android verify automatic selection and induce one failed line to confirm failover preserves episode/progress.

- [ ] **Step 6: Update durable documentation and evidence**

Document the new data boundary, `/vod/*` endpoints, source publishing workflow, cache TTLs, matching threshold, ranking weights and rollback behavior in `docs/项目文档.md`. Append the release entry to `docs/版本史.md` and exact commands/devices/screenshots/results to `docs/测试记录.md`.

- [ ] **Step 7: Build final distributable artifacts without deploying automatically**

Run: `python tools/build_backend_zip.py`

Run: `python tools/build_web_function.py`

Expected: both artifacts contain the four new backend data/module files. Do not upload, publish, or push configuration until the user explicitly requests deployment.

- [ ] **Step 8: Record final checkpoint**

Run: `Get-Item android\app\src\main\assets\backend\python-backend.zip,android\app\build\outputs\apk\debug\app-debug.apk,internal\mobile\app\build\outputs\apk\debug\app-debug.apk,cloudfunctions\otv-web\proxy.py -ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime`

Expected: report which artifacts were rebuilt and which APK release artifacts were intentionally unchanged by debug-only verification.
