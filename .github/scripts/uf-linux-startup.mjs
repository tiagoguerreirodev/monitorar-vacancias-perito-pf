// [DEBUG-uf-linux] Temporary pre-navigation diagnostic; no navigation/source APIs.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {pathToFileURL} from 'node:url';

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const classes = [
  ['sandbox_refusal', /no usable sandbox|running as root without --no-sandbox|failed to move to new namespace|operation not permitted.*sandbox/i],
  ['missing_library', /error while loading shared libraries|cannot open shared object file/i],
  ['permission_denied', /permission denied/i],
  ['crash', /segmentation fault|trace\/breakpoint trap|received signal|fatal:/i],
];
function groupAlive(pid) {
  try { process.kill(-pid, 0); return true; } catch (error) {
    if (error.code === 'ESRCH') return false;
    if (error.code === 'EPERM') return true;
    throw error;
  }
}
function killGroup(pid, signal) {
  try { process.kill(-pid, signal); } catch (error) {
    if (!['ESRCH', 'EPERM'].includes(error.code)) throw error;
  }
}
function localJSON(port, endpoint, onAlive) {
  return new Promise((resolve, reject) => {
    const request = http.get({host: '127.0.0.1', port, path: endpoint, agent: false,
      signal: AbortSignal.timeout(500)}, response => {
      onAlive();
      let text = '';
      response.on('data', chunk => {
        text += chunk;
        if (text.length > 65536) response.destroy(new Error('bound'));
      });
      response.on('error', reject);
      response.on('end', () => {
        try {
          if (response.statusCode !== 200) throw new Error('status');
          resolve(JSON.parse(text));
        } catch { reject(new Error('invalid readiness')); }
      });
    });
    request.on('socket', socket => socket.once('connect', onAlive));
    request.setTimeout(500, () => request.destroy(new Error('timeout')));
    request.on('error', reject);
  });
}

// Public process seam: tests supply an external executable, never a source override.
export async function observeStartup(chrome, expectedVersion, startupMs = 15000) {
  const owned = fs.mkdtempSync(path.join(os.tmpdir(), 'uf-linux-startup-'));
  const profile = path.join(owned, 'clean-profile');
  fs.mkdirSync(profile, {mode: 0o700});
  const record = {
    outcome: 'startup_timeout', launched: false, port_file_seen: false,
    port_alive: false, readiness: false, stderr_classes: [], stderr_truncated: false,
    exit_code: null, signal: null,
    cleanup: {process_group_stopped: false, owned_directory_removed: false},
  };
  let browser, stderr = '', interrupted = false, spawnFailed = false;
  const interrupt = () => { interrupted = true; };
  process.on('SIGTERM', interrupt);
  process.on('SIGINT', interrupt);
  try {
    // Exact production browser-probe.mjs launch recipe; about:blank is the ONLY target.
    browser = spawn(chrome, ['--headless=new', '--user-data-dir=' + profile,
      '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
      '--no-first-run', '--no-default-browser-check', 'about:blank'],
    {detached: true, stdio: ['ignore', 'pipe', 'pipe']});
    browser.on('error', () => { spawnFailed = true; });
    browser.on('spawn', () => { record.launched = true; });
    // Drain both pipes, but retain only a bounded private stderr prefix in memory.
    browser.stdout.resume();
    browser.stderr.on('data', chunk => {
      const remaining = 65536 - Buffer.byteLength(stderr);
      if (chunk.length > remaining) record.stderr_truncated = true;
      if (remaining > 0) stderr += chunk.subarray(0, remaining).toString('utf8');
    });
    const deadline = performance.now() + startupMs;
    while (performance.now() < deadline && !interrupted) {
      if (spawnFailed) { record.outcome = 'spawn_failed'; break; }
      if (browser.exitCode !== null || browser.signalCode !== null) {
        record.outcome = 'early_exit'; break;
      }
      try {
        const portPath = path.join(profile, 'DevToolsActivePort');
        if (fs.statSync(portPath).size > 4096) { record.outcome = 'invalid_port_file'; break; }
        const portFile = fs.readFileSync(portPath, 'utf8');
        record.port_file_seen = true;
        const first = portFile.split('\n')[0];
        if (!/^[0-9]{1,5}$/.test(first) || +first < 1 || +first > 65535) {
          record.outcome = 'invalid_port_file'; break;
        }
        const alive = () => { record.port_alive = true; };
        const version = await localJSON(+first, '/json/version', alive);
        const targets = await localJSON(+first, '/json/list', alive);
        if (version.Browser !== 'Chrome/' + expectedVersion || !Array.isArray(targets) ||
            !targets.some(target => target.type === 'page' && target.url === 'about:blank') ||
            targets.some(target => target.type === 'page' && target.url !== 'about:blank')) {
          record.outcome = 'invalid_readiness'; break;
        }
        record.readiness = true;
        record.outcome = 'ready'; break;
      } catch { /* Only owned loopback readiness is polled; never navigate/retry a source. */ }
      await pause(50);
    }
    if (interrupted) record.outcome = 'owner_interrupted';
  } catch { record.outcome = 'helper_failed'; }
  finally {
    if (browser?.pid) {
      // Kill the entire fresh owned group even if its leader has already exited.
      killGroup(browser.pid, 'SIGTERM');
      for (let i = 0; i < 20 && groupAlive(browser.pid); i++) await pause(50);
      if (groupAlive(browser.pid)) killGroup(browser.pid, 'SIGKILL');
      for (let i = 0; i < 40 && groupAlive(browser.pid); i++) await pause(50);
      record.cleanup.process_group_stopped = !groupAlive(browser.pid);
    } else record.cleanup.process_group_stopped = true;
    record.exit_code = browser?.exitCode ?? null;
    const signal = browser?.signalCode;
    record.signal = ['SIGTERM', 'SIGKILL', 'SIGABRT', 'SIGSEGV', 'SIGTRAP', 'SIGILL', 'SIGBUS'].includes(signal)
      ? signal : signal ? 'other' : null;
    record.stderr_classes = classes.filter(([, pattern]) => pattern.test(stderr)).map(([name]) => name);
    if (!record.stderr_classes.length) record.stderr_classes = [stderr.length ? 'other' : 'none'];
    stderr = '';
    if (record.cleanup.process_group_stopped) {
      try { fs.rmSync(owned, {recursive: true, force: true}); } catch { /* Report failed removal below. */ }
    }
    record.cleanup.owned_directory_removed = !fs.existsSync(owned);
    if (interrupted) record.outcome = 'owner_interrupted';
    process.removeListener('SIGTERM', interrupt);
    process.removeListener('SIGINT', interrupt);
  }
  return record;
}

async function main() {
  const [chrome, version, ...extra] = process.argv.slice(2);
  if (!chrome || !path.isAbsolute(chrome) || !/^\d+\.\d+\.\d+\.\d+$/.test(version) || extra.length)
    throw new Error('invalid invocation');
  const observations = [];
  for (let i = 0; i < 3; i++) {
    const observation = await observeStartup(chrome, version);
    observations.push(observation);
    if (!Object.values(observation.cleanup).every(Boolean) || observation.outcome === 'owner_interrupted') break;
  }
  process.stdout.write(JSON.stringify(observations));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  main().catch(() => { process.stderr.write('[DEBUG-uf-linux] diagnostic helper failed\n'); process.exitCode = 1; });
