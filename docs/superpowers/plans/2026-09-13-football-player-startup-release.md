# Football, Player, Startup, and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the eleven approved football/player fixes, silent backend/Web updates, APK-based native UI updates, and a coherent GitHub project release.

**Architecture:** Keep match normalization and caching in the embedded Python backend, while Android owns exact-time UI projection, paged TV layout, playback session switching, startup readiness, and APK installation. Preserve the shared TV/mobile data and playback layers, keep Web behavior aligned where applicable, and make release artifacts content-addressed and explicitly typed.

**Tech Stack:** Kotlin, Jetpack Compose, Media3, DataStore, OkHttp, Python standard library, JavaScript, Gradle, unittest, Git/GitHub.

**Spec:** `docs/superpowers/specs/2026-09-12-football-live-player-hotupdate-flash-design.md`

## Global Constraints

- TV, mobile, and Web behavior stays aligned unless the interaction is platform-specific.
- Backend/Web packages update silently; native Compose changes are delivered as a signed APK and may still require Android's system installation confirmation.
- No private keys, credentials, APK files, build directories, caches, or local screenshots are committed.
- Tests are written and observed failing before each production behavior change.
- Do not deploy CloudBase functions or publish an App update package unless the relevant release verification passes.

---

### Task 1: Match State and Important-Team Policy

**Files:**
- Modify: `tools/backend-src/proxy.py`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/data/repo/LiveRepository.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/live/LiveScreen.kt`
- Test: `tools/backend-src/tests/test_live_flash_contract.py`
- Test: `android/app/src/test/java/com/qiubo/optimaltv/LiveFlashPolicyTest.kt`

**Interfaces:**
- Produces: exact-time status normalization and `ImportantTeamPolicy.isImportant(MatchItem): Boolean`.

- [ ] Write failing tests for kickoff projection, finished-match protection, popular-team aliases, and exclusion of generic Chinese Super League matches.
- [ ] Run the focused Python and JVM tests and confirm the new assertions fail for the intended behavior.
- [ ] Implement short active-match caching, response-time normalization, and the shared important-team whitelist policy.
- [ ] Run focused tests until green, then run existing football contract tests.

### Task 2: Today Match Paging and Foreground Refresh

**Files:**
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/live/LiveScreen.kt`
- Test: `android/app/src/test/java/com/qiubo/optimaltv/LiveFlashPolicyTest.kt`

**Interfaces:**
- Produces: `TodayMatchPager.pages(items): List<TodayMatchPage>` with row-major 4+4 pages.

- [ ] Add failing tests proving five matches split 4+1, eight split 4+4, and nine start a second page.
- [ ] Run the focused JVM test and confirm the current two-independent-row model fails it.
- [ ] Implement one horizontal page row containing a two-row, four-column grid per page and deterministic D-pad navigation.
- [ ] Change foreground refresh to 10 seconds and schedule a local update at the nearest kickoff.
- [ ] Run the focused tests and compile the TV UI.

### Task 3: Remembered Source and Immediate Live Switching

**Files:**
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/data/prefs/SettingsStore.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/player/PlayerViewModel.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/playback/Media3Engine.kt`
- Test: `android/app/src/test/java/com/qiubo/optimaltv/PlaybackPolicyTest.kt`

**Interfaces:**
- Consumes: dynamic `MatchChannel.src` list.
- Produces: remembered-source selection and generation-guarded switch decisions.

- [ ] Add failing policy tests for remembered-source priority, absent-source fallback, automatic-failure non-persistence, and stale-generation rejection.
- [ ] Run the tests and verify RED.
- [ ] Implement selection policy and ensure only manual source changes call `rememberLiveLastSrc`.
- [ ] On source click, increment generation, stop/clear old media immediately, expose switching UI state, and ignore stale async callbacks.
- [ ] Run tests and the player compilation checks.

### Task 4: Episode Navigation, Ranked Lines, and Seek Step

**Files:**
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/player/PlayerScreen.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/player/PlayerViewModel.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/data/repo/VodRepository.kt`
- Modify: corresponding mobile player UI files under `internal/mobile/`
- Test: `android/app/src/test/java/com/qiubo/optimaltv/PlaybackPolicyTest.kt`

**Interfaces:**
- Produces: `EpisodeMenuPolicy`, `VisibleVodLinePolicy`, and 10-second seek constants.

- [ ] Add failing tests for the 19/20 episode boundary, ten-episode ranges, numeric child labels, available top-five lines, public line labels, and 10-second seek clamping.
- [ ] Run focused tests and verify RED.
- [ ] Implement the policies in pure Kotlin and bind them to TV/mobile player screens.
- [ ] Redesign primary range chips and secondary episode buttons with distinct container, focus, and selected states.
- [ ] Run focused tests and compile both apps sequentially.

### Task 5: Startup Readiness Gate

**Files:**
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/App.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/MainActivity.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/EmbeddedBackend.kt`
- Modify: shared counterparts under `internal/mobile/`
- Test: `android/app/src/test/java/com/qiubo/optimaltv/StartupReadinessPolicyTest.kt`

**Interfaces:**
- Produces: readiness state covering update check, backend health, packaged resources, and catalog availability.

- [ ] Add failing tests for all-ready, cached-catalog timeout fallback, and no-resource retry states.
- [ ] Run focused tests and verify RED.
- [ ] Implement bounded readiness aggregation and render a startup screen until the gate settles.
- [ ] Run focused tests and both app builds.

### Task 6: Silent Web/Backend Update and Native APK Update

**Files:**
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/hotupdate/HotUpdateManager.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/EmbeddedBackend.kt`
- Modify: `cloudfunctions/hotupdate/index.js`
- Modify: `tools/admin_server.py`
- Modify: `tools/admin.html`
- Modify: `tools/build_backend_zip.py`
- Test: `tools/backend-src/tests/test_hotupdate_flash_contract.py`
- Test: `android/app/src/test/java/com/qiubo/optimaltv/HotUpdatePolicyTest.kt`

**Interfaces:**
- Produces: typed update manifests (`backend_web` or `apk`), content hash extraction markers, silent backend application, and signature-checked APK installation intents.

- [ ] Add failing contract/JVM tests for silent backend application, mandatory `www/` entries, content-hash re-extraction, typed APK metadata, and signature/SHA rejection.
- [ ] Run focused tests and verify RED.
- [ ] Implement content-addressed backend extraction and remove the optional-update App dialog for `backend_web` packages.
- [ ] Add APK metadata/download verification and direct handoff to the Android package installer without an App-owned confirmation dialog.
- [ ] Update the admin release form and cloud check response to distinguish package types.
- [ ] Run focused tests, syntax checks, and sequential app builds.

### Task 7: Web Parity and Package Synchronization

**Files:**
- Modify: `tools/backend-src/www/app.js`
- Modify: `tools/backend-src/www/style.css`
- Generate: `cloudfunctions/otv-web/`
- Generate: `android/app/src/main/assets/backend/python-backend.zip`
- Generate: `internal/mobile/app/src/main/assets/backend/python-backend.zip`

**Interfaces:**
- Consumes: match policy and update manifests from earlier tasks.

- [ ] Add or extend Web contract tests for 10-second live refresh, row-major today paging, important-team filtering, source memory, and the player control bar.
- [ ] Run tests and verify RED.
- [ ] Implement applicable Web parity and cache-busting behavior.
- [ ] Add the Web player return, play/pause, seek bar, time labels, fullscreen, and accessible overflow controls; hide seek-only controls for live media.
- [ ] Rebuild Web function and embedded backend packages, then run `tools/sync_shared.py`.

### Task 7A: Team Logo Provider Boundary

**Files:**
- Modify: `tools/backend-src/team_backdrop.py`
- Modify: `tools/backend-src/proxy.py`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/ui/live/LiveScreen.kt`
- Test: `tools/backend-src/tests/test_live_flash_contract.py`

**Interfaces:**
- Produces: built-in-first team logo resolution with optional licensed online provider and disk cache.

- [ ] Add failing tests for alias normalization, built-in priority, cached-online fallback, and text fallback.
- [ ] Run focused tests and verify RED.
- [ ] Extract provider-independent logo lookup and caching without adding or hotlinking `football-logos.cc` assets.
- [ ] Preserve the existing bundled logos until an explicitly commercial-compatible source or written permission is available.
- [ ] Document the rejected provider and legal reason in the project documentation.

### Task 8: Project and Documentation Reorganization

**Files:**
- Modify: `README.md`
- Modify: `docs/项目文档.md`
- Modify: `docs/版本史.md`
- Modify: `docs/测试记录.md`
- Create: `docs/README.md`
- Modify: `.gitignore`

**Interfaces:**
- Produces: current architecture, build, testing, update, and release documentation with a single navigable index.

- [ ] Inventory tracked files for generated artifacts, secrets, stale source claims, duplicated documents, and broken links.
- [ ] Update ignore rules without deleting user-owned artifacts; move only clearly generated or obsolete tracked files into documented archive locations.
- [ ] Rewrite README current-state sections and add a documentation index.
- [ ] Update project architecture from hhkan-only to Douban catalog plus managed playback sources; document silent backend/Web versus APK-native update behavior.
- [ ] Append version and verification records without rewriting historical logs.
- [ ] Run link/path, secret-pattern, and tracked-artifact checks.

### Task 9: Full Verification and GitHub Publication

**Files:**
- Verify: entire repository

**Interfaces:**
- Produces: tested commit(s) pushed to `origin/main`.

- [ ] Run all Python tests and Python/JavaScript syntax checks.
- [ ] Run TV unit tests and Debug build, then mobile unit tests and Debug build sequentially.
- [ ] Verify embedded zip required entries and TV/mobile shared-file consistency.
- [ ] Review `git diff`, confirm no credentials/build artifacts are staged, and ensure all 11 requirements map to implemented tests.
- [ ] Commit the coherent release with a descriptive message.
- [ ] Pull/rebase only if the remote advanced, rerun affected verification, and push `main` to `origin`.
- [ ] Report commit ID, push result, artifact paths, verification counts, and explicitly state that CloudBase/App packages were not deployed unless separately requested.
