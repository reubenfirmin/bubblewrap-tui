# QA Test Cases - Golden Path

Quick validation tests for bubblewrap-tui core functionality.

---

## 1. Basic Interactive TUI

**Prerequisites:** bui installed (`bui --install`)

**Steps:**
1. Run `bui -- /bin/bash`
2. Navigate through tabs using mouse or keyboard
3. Go to Summary tab to review generated bwrap command
4. Press Enter or click "Execute"
5. Inside sandbox, run `whoami` and `pwd`
6. Exit with `exit`

**Expected Result:**
- TUI displays with Directories, Environment, Sandbox, Network, Overlays, Summary tabs
- Summary tab shows generated bwrap command with color-coded sections
- Sandbox executes bash
- `whoami` shows `nobody` or `sandbox` (depending on user config)
- Clean exit returns to host shell

---

## 2. Built-in Profile Usage

**Prerequisites:** bui installed with untrusted profile (`~/.config/bui/profiles/untrusted.json`)

**Steps:**
1. Run `bui --profile untrusted -- bash`
2. Inside sandbox, run:
   - `whoami` (should show `sandbox`)
   - `echo $HOME` (should show `/home/sandbox`)
   - `ls /usr/bin | head` (should show host binaries)
   - `touch /home/sandbox/testfile` (should succeed - persistent overlay)
3. Exit and re-run the same command
4. Check if `testfile` persists

**Expected Result:**
- Profile loads without TUI interaction
- User identity is `sandbox` with home at `/home/sandbox`
- Host binaries accessible via bound `/usr`, `/bin`
- Files written to home persist across sessions (persistent overlay)

---

## 3. Save and Load Custom Profile

**Prerequisites:** bui installed

**Steps:**
1. Run `bui -- /bin/bash`
2. Configure a custom setup:
   - Directories tab: bind `/tmp` read-write
   - Environment tab: add custom var `MYVAR=testing`
   - Sandbox tab: set username to `testuser`
3. Click "Save" in header, enter name `mytest`
4. Click "Cancel" to exit without executing
5. Verify profile exists: `cat ~/.config/bui/profiles/mytest.json`
6. Run `bui --profile mytest -- bash`
7. Inside sandbox: `echo $MYVAR`

**Expected Result:**
- Profile saves to `~/.config/bui/profiles/mytest.json`
- Profile loads successfully via `--profile mytest`
- Custom environment variable `MYVAR=testing` is present

---

## 4. curl | bash Execution

**Prerequisites:** bui installed, network access

**Steps:**
1. Run with untrusted profile to fetch and execute an install script:
   ```bash
   bui --profile untrusted -- 'curl -fsSL https://deno.land/install.sh | sh'
   ```
2. Wait for installation to complete
3. Verify deno binary exists in overlay:
   ```bash
   bui --profile untrusted -- ls -la /home/sandbox/.deno/bin/
   ```

**Expected Result:**
- Curl successfully fetches install script
- Script executes in sandbox with network access
- Deno installs to `/home/sandbox/.deno/bin/deno` (persistent overlay)
- Host system remains unmodified

---

## 5. Code Agent Sandbox (Claude Code)

**Prerequisites:** bui installed, npm available on host, network access

**Steps:**
1. Create a managed sandbox and install Claude Code:
   ```bash
   bui --profile untrusted --sandbox claude \
       --bind $(dirname $(which npm)) \
       --bind-env 'NPM_CONFIG_PREFIX=/home/sandbox/.npm-global' \
       -- npm install -g @anthropic-ai/claude-code
   ```
2. Install wrapper script:
   ```bash
   bui --sandbox claude --install
   ```
3. Select the `claude` binary from the list when prompted
4. Verify wrapper created: `cat ~/.local/bin/claude`
5. Test execution: `claude --help`

**Expected Result:**
- npm installs Claude Code in sandbox overlay
- Wrapper script created at `~/.local/bin/claude`
- Running `claude` launches sandboxed Claude Code
- Claude Code operates with network access and persistent storage

---

## 6. Network Filtering (Whitelist)

**Prerequisites:** bui installed, pasta installed, iptables available

**Steps:**
1. Run `bui -- bash`
2. Go to Network tab
3. Enable "Network access"
4. In hostname filter, set mode to "Whitelist"
5. Add hosts: `github.com`, `api.github.com`
6. Go to Summary tab and verify iptables rules are generated
7. Execute the sandbox
8. Test allowed: `curl -I https://github.com`
9. Test blocked: `curl -I https://google.com` (should timeout/fail)

**Expected Result:**
- Summary shows iptables whitelist rules for github.com
- Curl to github.com succeeds (200 response)
- Curl to google.com fails (connection refused or timeout)
- Only whitelisted hosts are accessible

---

## 7. Network Filtering (Blacklist)

**Prerequisites:** bui installed, pasta installed, iptables available

**Steps:**
1. Run `bui -- bash`
2. Go to Network tab
3. Enable "Network access"
4. In hostname filter, set mode to "Blacklist"
5. Add hosts: `facebook.com`, `twitter.com`
6. Execute the sandbox
7. Test allowed: `curl -I https://github.com`
8. Test blocked: `curl -I https://facebook.com`

**Expected Result:**
- Curl to github.com succeeds (not in blacklist)
- Curl to facebook.com fails (blacklisted)
- General internet access works except for blocked hosts

---

## 8. Directory Binding

**Prerequisites:** bui installed, test directories exist

**Steps:**
1. Create test directories:
   ```bash
   mkdir -p /tmp/readonly-test /tmp/readwrite-test
   echo "readonly content" > /tmp/readonly-test/file.txt
   echo "writable content" > /tmp/readwrite-test/file.txt
   ```
2. Run `bui -- bash`
3. In Directories tab:
   - Add `/tmp/readonly-test` as read-only (click 'ro')
   - Add `/tmp/readwrite-test` as read-write (click 'rw')
4. Execute the sandbox
5. Test read-only:
   ```bash
   cat /tmp/readonly-test/file.txt    # should work
   echo "new" > /tmp/readonly-test/x  # should fail (read-only)
   ```
6. Test read-write:
   ```bash
   cat /tmp/readwrite-test/file.txt   # should work
   echo "modified" >> /tmp/readwrite-test/file.txt  # should work
   ```

**Expected Result:**
- Read-only directory: reads succeed, writes fail with permission error
- Read-write directory: both reads and writes succeed
- Changes to read-write directory persist on host

---

## 9. Overlay Filesystem

**Prerequisites:** bui installed

**Steps:**

**Test tmpfs overlay:**
1. Run `bui -- bash`
2. In Overlays tab, add overlay:
   - Dest: `/tmp/volatile`
   - Mode: tmpfs
3. Execute sandbox
4. Create a file: `echo "test" > /tmp/volatile/myfile`
5. Exit sandbox
6. Re-run and check: `ls /tmp/volatile/` (should be empty)

**Test persistent overlay:**
1. Run `bui -- bash`
2. In Overlays tab, add overlay:
   - Source: `/usr` (or leave empty)
   - Dest: `/home/sandbox`
   - Mode: persistent
   - Write dir: `~/.local/state/bui/overlays/test-overlay`
3. Execute sandbox
4. Create a file: `echo "persistent" > /home/sandbox/myfile`
5. Exit sandbox
6. Re-run and check: `cat /home/sandbox/myfile`

**Expected Result:**
- tmpfs: files exist during session, disappear after exit
- persistent: files survive across sandbox sessions
- Persistent writes stored in specified write_dir on host

---

## 10. Managed Sandbox Lifecycle

**Prerequisites:** bui installed

**Steps:**

**Create sandbox:**
1. Run a command in a named sandbox:
   ```bash
   bui --profile untrusted --sandbox lifecycle-test -- bash -c 'echo "test" > /home/sandbox/marker'
   ```
2. Verify overlay directory created:
   ```bash
   ls ~/.local/state/bui/overlays/lifecycle-test/
   ```

**Install wrapper:**
3. Create a simple script in the sandbox:
   ```bash
   bui --profile untrusted --sandbox lifecycle-test -- bash -c 'mkdir -p /home/sandbox/bin && echo "#!/bin/sh\necho hello from sandbox" > /home/sandbox/bin/hello && chmod +x /home/sandbox/bin/hello'
   ```
4. Install wrapper:
   ```bash
   bui --sandbox lifecycle-test --install
   ```
5. Select `hello` from the executable list
6. Verify wrapper: `cat ~/.local/bin/hello`
7. Test wrapper: `hello`

**List sandboxes:**
8. Run `bui --list-sandboxes`

**Uninstall:**
9. Run `bui --sandbox lifecycle-test --uninstall`
10. Verify wrapper removed: `ls ~/.local/bin/hello` (should not exist)
11. Verify sandbox removed from list: `bui --list-sandboxes`

**Expected Result:**
- Sandbox creates overlay directory automatically
- Wrapper script created and functional
- `--list-sandboxes` shows installed sandbox with metadata
- Uninstall removes wrapper scripts and cleans up metadata
- Overlay data may persist (for manual cleanup if needed)

---

## Quick Reference

| Test | Primary Feature | Key Commands |
|------|-----------------|--------------|
| 1 | TUI Navigation | `bui -- /bin/bash` |
| 2 | Profile Loading | `bui --profile untrusted -- bash` |
| 3 | Profile Save/Load | TUI Save button, `--profile` |
| 4 | Script Execution | `bui -- 'curl ... \| sh'` |
| 5 | Code Agent Setup | `--sandbox`, `--bind`, `--bind-env` |
| 6 | Network Whitelist | Network tab, hostname filter |
| 7 | Network Blacklist | Network tab, blacklist mode |
| 8 | Directory Binding | Directories tab, ro/rw toggle |
| 9 | Overlay Modes | Overlays tab, tmpfs/persistent |
| 10 | Sandbox Lifecycle | `--install`, `--uninstall`, `--list-sandboxes` |
