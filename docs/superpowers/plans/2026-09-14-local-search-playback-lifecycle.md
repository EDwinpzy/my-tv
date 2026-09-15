# Local Search, Playback Recovery, and Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver persistent Douban-backed local search, bounded football/VOD playback recovery, foreground refresh, explicit-exit cleanup, and synchronized TV/mobile/Web releases.

**Architecture:** Add a standard-library SQLite search index beside the embedded backend but outside its replaceable extraction directory. Keep the current repositories and players, adding small policy/state-machine units which can be tested without Android framework dependencies, then bind those policies to TV, mobile, Web, and the Python relay.

**Tech Stack:** Python 3.11 standard library, SQLite/FTS5, Kotlin, Jetpack Compose, Media3, VLC, JavaScript, hls.js, Gradle, unittest, JUnit.

**Spec:** `docs/superpowers/specs/2026-09-14-local-search-playback-lifecycle-design.md`

## Global Constraints

- Existing five-category film UI and managed playback sources remain unchanged.
- Search never contacts Douban or playback providers.
- Device databases survive backend hot updates and APK upgrades.
- Recovery attempts are bounded and stale callbacks are rejected by session generation.
- TV and mobile shared production files stay byte-identical except registered UI/player differences.
- No credentials, device database, logs, screenshots, APKs, or build directories are committed.
- External release actions are authorized only for this confirmed combined scope.

---

### Task 1: Persistent Media Index and Local Search API

**Files:**
- Create: `tools/backend-src/media_index.py`
- Create: `tools/backend-src/pinyin_map.json`
- Modify: `tools/backend-src/douban_catalog.py`
- Modify: `tools/backend-src/vod_api.py`
- Modify: `tools/backend-src/proxy.py`
- Modify: `tools/build_backend_zip.py`
- Modify: `tools/build_web_function.py`
- Test: `tools/backend-src/tests/test_media_index.py`
- Test: `tools/backend-src/tests/test_vod_api.py`

**Interfaces:**
- Produces: `MediaIndex(db_path, pinyin_path)`, `upsert_many(items)`, and `search(query, limit=30) -> list[dict]`.
- Produces: `GET /api/search?q=<query>&limit=<1..100>` returning `{query, items, total, local: true}`.

- [ ] Write failing tests using a temporary SQLite database for title/alias/original/person/genre/full-pinyin/initial/season/fuzzy ranking and reopen persistence.
- [ ] Run `python -m unittest tools.backend-src.tests.test_media_index -v` and confirm failure because `media_index` does not exist.
- [ ] Implement schema migration, normalization, generated pinyin lookup, transactional upsert, exact/prefix/contains ranking, and result-limited fuzzy fallback.
- [ ] Run the focused test until green, then add failing API tests proving `/api/search` uses the local index and performs no network fetch.
- [ ] Bind successful Douban home/show/detail payloads to `upsert_many`, expose the API, and run all focused tests.

### Task 2: Three-Client Search Integration

**Files:**
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/data/repo/LiveRepository.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/search/SearchScreen.kt`
- Modify: corresponding files under `internal/mobile/`
- Modify: `tools/backend-src/www/app.js`
- Test: `tools/backend-src/tests/test_local_search_contract.py`

**Interfaces:**
- Consumes: `/api/search` from Task 1.
- Produces: `searchMedia(query, limit)` mapping every result to a `douban:` item.

- [ ] Add a failing source-contract test which requires `/api/search`, accepts Latin input during debounce, and rejects `/hhkan/search` in client search paths.
- [ ] Run the contract test and verify RED against the existing clients.
- [ ] Replace Android and Web search calls, remove Chinese-only gating, preserve category tabs, and map returned Douban categories locally.
- [ ] Run the contract test and Android compilation tests until green.

### Task 3: Stream Cache and Recovery Policies

**Files:**
- Modify: `tools/backend-src/proxy.py`
- Create: `android/app/src/main/java/com/qiubo/optimaltv/playback/PlaybackRecoveryPolicy.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/playback/StreamDecryptServer.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/player/PlayerViewModel.kt`
- Mirror shared changes under `internal/mobile/`
- Test: `tools/backend-src/tests/test_stream_recovery.py`
- Test: `android/app/src/test/java/com/qiubo/optimaltv/PlaybackRecoveryPolicyTest.kt`

**Interfaces:**
- Produces: 60-second positive stream cache and non-sticky failures.
- Produces: `PlaybackRecoveryPolicy.next(context): RecoveryAction` and public decrypt-pool reset/shutdown calls.

- [ ] Add failing Python tests proving missing-player and exception payloads are not positively cached and positive entries expire after 60 seconds.
- [ ] Run the focused Python test and confirm current 300-second behavior fails.
- [ ] Implement the cache fix and run focused tests green.
- [ ] Add failing JVM tests for BUFFERING timing, position-stall timing, live fresh resolve, VOD resume offset, source fallback, engine recreation, backend reset, budgets, and generation rejection.
- [ ] Implement the pure policy and bind it to both PlayerViewModels, including BUFFERING observation and VOD re-resolution with saved position.
- [ ] Add consecutive decrypt timeout reset plus public `reset()`/`shutdown()` and run Python/JVM tests green.

### Task 4: Web Playback Self-Healing and Refresh Hooks

**Files:**
- Modify: `tools/backend-src/www/app.js`
- Test: `tools/backend-src/tests/test_web_recovery_contract.py`

**Interfaces:**
- Consumes: fresh `/api/stream`, `/vod/play`, and existing `attachPlayer`.
- Produces: bounded Web recovery, fresh live URLs, preserved VOD position, and foreground/network refresh hooks.

- [ ] Add failing contracts for `fresh=1`, recovery generation, bounded attempts, `online/focus/pageshow/visibilitychange`, and replacement of stale-manifest `startLoad()` behavior.
- [ ] Run the contract and verify RED.
- [ ] Implement recovery state, resolve-current-source helpers, long-background renewal, player teardown, and deduplicated page refresh.
- [ ] Run JavaScript syntax and the contract test green.

### Task 5: Native Refresh and Explicit Exit

**Files:**
- Create: `android/app/src/main/java/com/qiubo/optimaltv/lifecycle/AppLifecyclePolicy.kt`
- Create: `android/app/src/main/java/com/qiubo/optimaltv/lifecycle/ExitCoordinator.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/App.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/MainActivity.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/BackendService.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/components/Hint.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/live/LiveScreen.kt`
- Mirror shared/applicable changes under `internal/mobile/`
- Test: `android/app/src/test/java/com/qiubo/optimaltv/AppLifecyclePolicyTest.kt`

**Interfaces:**
- Produces: foreground epoch/state, long-background decisions, explicit-exit marker, and ordered process cleanup.

- [ ] Add failing JVM tests for ordinary background, 30-second live renewal, explicit exit, restart clearing the marker, and refresh deduplication.
- [ ] Run focused JVM tests and verify RED.
- [ ] Implement the pure policy, Activity lifecycle dispatch, network callback, explicit-exit cleanup, and `START_NOT_STICKY` backend behavior.
- [ ] Bind foreground refresh to the football screen and playback supervisor, then run focused tests and both app unit suites.

### Task 6: Packaging, Documentation, and Local Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/01-overview/项目文档.md`
- Modify: `docs/04-records/版本史.md`
- Modify: `docs/04-records/测试记录.md`
- Generate: `cloudfunctions/otv-web/`
- Generate: both `python-backend.zip` files

**Interfaces:**
- Produces: versioned hot-update bundle, Web function, TV APK, mobile APK, and verification record.

- [ ] Run the full Python suite, Python compile checks, JavaScript syntax checks, TV/mobile unit suites, and `tools/sync_shared.py`.
- [ ] Build Web/backend packages and verify required SQLite/search/Web entries without embedding `mytv.db`.
- [ ] Build signed TV/mobile release APKs and record version, SHA-256, and paths.
- [ ] Update current architecture, release, version, and test records; inspect the final diff for secrets and accidental artifacts.

### Task 7: Confirmed External Release

**Files:**
- Verify: release artifacts and Git history.

**Interfaces:**
- Produces: deployed public Web, published App hot update, released APK artifacts, and pushed Git commit.

- [ ] Reconfirm that the authorization applies exactly to the combined local-search/playback/lifecycle release; the user's 2026-09-14 “确认” satisfies this gate.
- [ ] Deploy `otv-web`, upload and publish the new hot-update version through the existing admin API/UI, and verify public health/version endpoints.
- [ ] Publish the two signed APK artifacts through the project's documented channel and verify downloadable hashes.
- [ ] Commit the reviewed changes, integrate the feature branch into `main`, pull/rebase only if remote advanced, and push `origin/main`.
- [ ] Report deployed versions, commit ID, artifact hashes, public smoke-test results, and any unresolved external-source limitations.

