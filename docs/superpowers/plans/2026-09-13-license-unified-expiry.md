# License Unified Expiry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PostgreSQL authoritative for a card's activation and expiry, share that expiry across two devices, add a 24-hour network grace period, and synchronize TV, mobile, Web, cloud functions, admin, reset tooling, and documentation.

**Architecture:** Authorization protocol v2 distinguishes explicit activation, non-binding verification, and renewal. PostgreSQL owns the canonical card row and renewal transaction; clients verify the existing P-256 ticket but store server-returned activation/expiry timestamps. Android and Web use a shared policy: explicit business rejection is immediate, while transport failure preserves access for at most 24 hours after the last successful verification.

**Tech Stack:** PostgreSQL PL/pgSQL, CloudBase HTTP functions (Node.js), Kotlin/Jetpack Compose/DataStore/OkHttp, browser JavaScript/WebCrypto, Python unittest contract tests, Gradle.

**Spec:** `docs/superpowers/specs/2026-09-13-license-unified-expiry-design.md`

## Global Constraints

- Keep `OTV-XXXXX-XXXXX`, ECDSA P-256 + SHA-256, local-only private key, weekly/monthly/quarterly/yearly/lifetime plans, and `max_dev = 2`.
- Android device ID is the full lowercase SHA-256 of `ANDROID_ID|packageName|Build.MODEL`.
- Web requests send only a SHA-256 identifier derived from a persistent random seed and origin.
- Explicit 403/404/405/406 responses invalidate immediately; transport/5xx failures allow at most 24 hours from the last successful verification.
- Renewal keeps the current card as the canonical membership and consumes the new card into `redeemed_to`.
- Existing cards and activation logs are deleted only by a separate one-time reset command after a local backup and plan-count snapshot.
- TV, mobile, and Web behavior must stay synchronized. Do not overwrite unrelated dirty-worktree changes.

---

### Task 1: Protocol v2 PostgreSQL migration and reset tooling

**Files:**
- Create: `tools/license_v2_migration.sql`
- Create: `tools/license_v2_reset.py`
- Create: `tools/backend-src/tests/test_license_v2_contract.py`

**Interfaces:**
- Produces RPC `activate_code(p_code text, p_device text, p_ip text, p_protocol int, p_action text, p_current_code text)` returning `{ret,ticket,licenseCode,activatedAt,expireAt,serverNow}`.
- Produces admin rows with `activated_at`, `expire_at`, `redeemed_at`, `redeemed_to`.
- Produces reset CLI modes `snapshot`, `clear`, and `regenerate --snapshot <path>`.

- [ ] **Step 1: Add failing SQL contract tests**

Create `test_license_v2_contract.py` that reads the migration and asserts the exact columns, six-argument RPC, `FOR UPDATE`, protocol-426 guard, action branches, verify-without-device-append, device limit, renewal fields, and admin projection. It must also assert that the migration contains no `TRUNCATE` or unconditional `DELETE FROM licenses`.

```python
def test_schema_migration_is_idempotent_and_non_destructive(self):
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for column in ("activated_at", "expire_at", "redeemed_at", "redeemed_to"):
        self.assertIn(f"add column if not exists {column}", sql)
    self.assertNotIn("truncate", sql)
    self.assertNotIn("delete from licenses", sql)

def test_activate_rpc_has_v2_actions_and_locking(self):
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    self.assertIn("p_protocol integer", sql)
    self.assertIn("p_action text", sql)
    self.assertIn("p_current_code text", sql)
    self.assertIn("for update", sql)
    for action in ("activate", "verify", "renew"):
        self.assertIn(f"'{action}'", sql)
```

- [ ] **Step 2: Run the contract tests and confirm RED**

Run: `python -m unittest tools/backend-src/tests/test_license_v2_contract.py -v`  
Expected: FAIL because `tools/license_v2_migration.sql` and reset CLI do not exist.

- [ ] **Step 3: Implement the idempotent schema/RPC migration**

The migration must:

```sql
alter table public.licenses add column if not exists activated_at timestamptz;
alter table public.licenses add column if not exists expire_at timestamptz;
alter table public.licenses add column if not exists redeemed_at timestamptz;
alter table public.licenses add column if not exists redeemed_to text;
create index if not exists idx_licenses_expire_at on public.licenses(expire_at);
create index if not exists idx_licenses_redeemed_to on public.licenses(redeemed_to);
```

Replace `activate_code` with the protocol v2 signature. Normalize inputs, reject `p_protocol <> 2` with 426, reject unknown actions with 400, and record every result in `activate_log`. `activate` initializes canonical time once and appends a device only below `max_dev`; `verify` never mutates devices; `renew` locks both codes in lexical order, validates ownership, extends only the canonical card, and marks the renewal card redeemed.

- [ ] **Step 4: Implement guarded reset tooling**

`license_v2_reset.py snapshot` signs in using the existing CloudBase service credentials, fetches plan counts and rows, and writes a timestamped JSON snapshot under `out/license-v2-reset/`. `clear` requires `--environment appletv-d5ge1bth794873f76`, `--snapshot <existing file>`, and `--confirm CLEAR-ALL-LICENSES`; it calls a dedicated admin-only RPC that deletes `activate_log` then `licenses` in one transaction. `regenerate` reads the snapshot counts, invokes the existing generator per plan, and imports every generated batch.

- [ ] **Step 5: Run Task 1 tests**

Run: `python -m unittest tools/backend-src/tests/test_license_v2_contract.py -v`  
Expected: all Task 1 tests PASS.

---

### Task 2: Activate cloud function protocol v2

**Files:**
- Modify: `cloudfunctions/activate/index.js`
- Create: `tools/backend-src/tests/test_activate_v2_contract.py`

**Interfaces:**
- Consumes RPC parameters from Task 1.
- Accepts JSON `{code,deviceId,protocol,action,currentCode?}`.
- Returns the RPC response unchanged.

- [ ] **Step 1: Add failing function contract tests**

Assert that the function validates a 64-character lowercase hex device ID, requires `protocol === 2`, validates `action` against activate/verify/renew, requires a valid `currentCode` for renew, and forwards all six named RPC parameters.

```python
def test_activate_function_forwards_protocol_action_and_current_code(self):
    src = FUNCTION.read_text(encoding="utf-8")
    for token in ("p_protocol", "p_action", "p_current_code"):
        self.assertIn(token, src)
    self.assertIn("^[a-f0-9]{64}$", src)
```

- [ ] **Step 2: Run and confirm RED**

Run: `python -m unittest tools/backend-src/tests/test_activate_v2_contract.py -v`  
Expected: FAIL because the function still forwards only code/device/IP.

- [ ] **Step 3: Implement validation and forwarding**

Update comments and request validation, preserve CORS/error handling, and send:

```js
body: JSON.stringify({
  p_code: code,
  p_device: deviceId,
  p_ip: ip,
  p_protocol: protocol,
  p_action: action,
  p_current_code: currentCode || null,
})
```

- [ ] **Step 4: Verify JavaScript and tests**

Run: `node --check cloudfunctions/activate/index.js`  
Run: `python -m unittest tools/backend-src/tests/test_activate_v2_contract.py -v`  
Expected: syntax check exits 0 and tests PASS.

---

### Task 3: Android device identity and 24-hour authorization policy

**Files:**
- Create: `android/app/src/main/java/com/qiubo/optimaltv/license/LicensePolicy.kt`
- Create: `android/app/src/test/java/com/qiubo/optimaltv/license/LicensePolicyTest.kt`
- Modify: `android/app/src/main/java/com/qiubo/optimaltv/license/LicenseManager.kt`
- Synchronize: `internal/mobile/app/src/main/java/com/qiubo/optimaltv/license/LicensePolicy.kt`
- Synchronize: `internal/mobile/app/src/main/java/com/qiubo/optimaltv/license/LicenseManager.kt`

**Interfaces:**
- Produces pure `LicensePolicy.sha256DeviceId(androidId, packageName, model): String`.
- Produces pure `LicensePolicy.accessAllowed(expireAt, lastVerifySuccessAt, now): Boolean`.
- License requests use protocol 2 and actions activate/verify/renew.

- [ ] **Step 1: Add failing pure unit tests**

Test full 64-character deterministic SHA-256, package separation, expiry boundary, 24-hour grace boundary, and no-verification denial.

```kotlin
@Test fun graceExpiresAtExactlyTwentyFourHours() {
    val day = 24 * 60 * 60 * 1000L
    val verified = 1_000L
    assertTrue(LicensePolicy.accessAllowed(verified + 10 * day, verified, verified + day - 1))
    assertFalse(LicensePolicy.accessAllowed(verified + 10 * day, verified, verified + day))
}
```

- [ ] **Step 2: Run and confirm RED**

Run from `android/`: `.\gradlew.bat testDebugUnitTest --tests '*LicensePolicyTest'`  
Expected: FAIL because `LicensePolicy` does not exist.

- [ ] **Step 3: Implement pure policy and update LicenseManager**

Remove `MAX_SEEN`, rollback tolerance, HTTP Date parsing, and local expiry calculation. Parse `licenseCode`, `activatedAt`, `expireAt`, and `serverNow` from protocol v2. Save `LAST_VERIFY_SUCCESS`; `isPremium()` delegates to `LicensePolicy.accessAllowed`.

Explicit activation uses action `activate` when no different current code exists and action `renew` with `currentCode` when a member enters another code. Silent reverify uses action `verify`. Clear local state on 403/404/406; retain the card but deny access on 405; retain state on transport/5xx until the 24-hour boundary. Add a throttled public `requestReverify()` used at startup/foreground/member gates.

- [ ] **Step 4: Synchronize TV and mobile shared files**

Copy the completed TV files through `tools/sync_shared.py --source android --target internal/mobile`, then run `python tools/sync_shared.py` and require no shared drift.

- [ ] **Step 5: Run Android unit tests and compilation**

Run from `android/`: `.\gradlew.bat testDebugUnitTest --tests '*LicensePolicyTest'`  
Run from `android/`: `.\gradlew.bat compileDebugKotlin`  
Expected: tests PASS and Kotlin compilation exits 0.

---

### Task 4: Web protocol v2 and hashed installation identity

**Files:**
- Modify: `tools/backend-src/www/app.js`
- Synchronize: `cloudfunctions/otv-web/www/app.js`
- Create: `tools/backend-src/tests/test_web_license_v2_contract.py`

**Interfaces:**
- Consumes the protocol v2 response from Task 2.
- Stores `{code,plan,days,expiry_at,activated_at,last_verify_success_at}`.
- Produces async hashed `webDeviceId()` and throttled `ensureLicenseVerified()`.

- [ ] **Step 1: Add failing Web contract tests**

Assert that WebCrypto SHA-256 is used for the device ID, requests include protocol/action/currentCode, expiry comes from `jo.expireAt`, renewal stores `jo.licenseCode`, and the 24-hour constant is exactly `24 * 60 * 60 * 1000`.

- [ ] **Step 2: Run and confirm RED**

Run: `python -m unittest tools/backend-src/tests/test_web_license_v2_contract.py -v`  
Expected: FAIL against the existing local-expiry implementation.

- [ ] **Step 3: Implement Web behavior**

Make `webDeviceId()` async, persist only a random seed locally, hash seed/origin before each cached use, and await it in activate/verify. Replace local `days` arithmetic with parsed server timestamps. On explicit business rejection clear/disable immediately; on fetch/5xx preserve only within 24 hours. Invoke verification on startup, `visibilitychange` to visible, and before protected playback with request coalescing.

- [ ] **Step 4: Synchronize and verify**

Run: `python tools/build_web_function.py`  
Run: `node --check tools/backend-src/www/app.js`  
Run: `python -m unittest tools/backend-src/tests/test_web_license_v2_contract.py -v`  
Expected: source/deployment copies match, syntax exits 0, tests PASS.

---

### Task 5: Admin visibility and deployment bundles

**Files:**
- Modify: `tools/admin.html`
- Create: `tools/backend-src/tests/test_admin_license_v2_contract.py`
- Generated by build: `cloudfunctions/otv-admin/admin.html`
- Generated by build: `cloudfunctions/otv-admin/admin_server.py`

**Interfaces:**
- Consumes admin RPC fields from Task 1.
- Displays activation, expiry, and renewal redemption state without exposing secrets.

- [ ] **Step 1: Add failing admin contract tests**

Assert visible column labels and field bindings for `activated_at`, `expire_at`, `redeemed_at`, and `redeemed_to`, plus the redeemed filter value.

- [ ] **Step 2: Run and confirm RED**

Run: `python -m unittest tools/backend-src/tests/test_admin_license_v2_contract.py -v`  
Expected: FAIL because the fields are not rendered.

- [ ] **Step 3: Implement admin rendering**

Add compact date formatting, status precedence `banned > redeemed > active > sold > unsold`, and a redeemed filter. Keep existing unbind/ban controls on canonical cards; hide those controls for redeemed renewal cards.

- [ ] **Step 4: Build and verify admin bundle**

Run: `python tools/build_admin_function.py`  
Run: `python -m py_compile tools/admin_server.py cloudfunctions/otv-admin/admin_server.py`  
Run: `python -m unittest tools/backend-src/tests/test_admin_license_v2_contract.py -v`  
Expected: build succeeds, Python compiles, tests PASS.

---

### Task 6: Build artifacts, reset inventory, deploy, and document

**Files:**
- Modify: `docs/01-overview/项目文档.md` (or current project-doc path from `docs/README.md`)
- Modify: `docs/04-records/版本史.md`
- Modify: `docs/04-records/测试记录.md`
- Generated: TV/mobile `python-backend.zip`, APK artifacts, CloudBase function bundles
- Generated outside Git: `out/license-v2-reset/<timestamp>/...`

**Interfaces:**
- Consumes all prior tasks.
- Produces deployed protocol v2 and fresh unsold/unbound card batches.

- [ ] **Step 1: Run all local automated verification**

```powershell
python -m unittest discover -s tools/backend-src/tests -p 'test_*.py'
node --check cloudfunctions/activate/index.js
python tools/sync_shared.py
python tools/build_backend_zip.py
```

Run Android TV and mobile builds sequentially, never in parallel.

- [ ] **Step 2: Snapshot the exact production inventory**

Run `python tools/license_v2_reset.py snapshot --environment appletv-d5ge1bth794873f76`. Verify the output contains total rows, per-plan counts, SHA-256, and timestamp. Do not proceed if the snapshot is empty while production contains cards.

- [ ] **Step 3: Deploy schema and compatible services**

Apply `tools/license_v2_migration.sql` to the named CloudBase PostgreSQL environment. Deploy activate, admin, and Web function bundles from this local checkout. Verify an old-protocol synthetic request returns 426 and a malformed v2 request returns 400 before clearing data.

- [ ] **Step 4: Clear and regenerate inventory**

Run the guarded clear command with the exact environment, snapshot path, and confirmation token. Run regenerate against that snapshot. Verify database totals equal the snapshot's per-plan counts and every new row has empty devices, null activation/expiry/redemption fields, and new code values.

- [ ] **Step 5: Publish clients and perform end-to-end tests**

Install the new TV and mobile APKs. Verify first activation, same-card second device shared expiry, third-device rejection, unbind/rebind, explicit invalidation, 24-hour policy unit boundary, renewal sharing, and Web parity. Publish only after those checks pass.

- [ ] **Step 6: Update documentation and final evidence**

Update current architecture, version history, and test record with the protocol, deployment identifiers, generated inventory counts, build hashes, and E2E evidence. Run `git diff --check` and a primary Markdown-link check. Do not include card values, service credentials, cookies, or private-key material.
