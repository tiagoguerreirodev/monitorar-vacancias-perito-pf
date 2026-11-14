"""Bounded anonymous frontend transport using owned processes/profile/output only."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen

from ._uf import UFExport


class UFBlocked(ValueError):
    """A required collector runtime is absent; no source observation is available."""


def _runtime(variable, candidates):
    configured = os.environ.get(variable)
    for name in ([configured] if configured else candidates):
        path = shutil.which(name)
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            return str(Path(path).resolve())
    raise UFBlocked(f'UF collector requires executable {variable}')


class OfficialUF:
    """No workbook, URL, session or user-profile inputs; every call exports afresh."""
    def latest_export(self):
        node = _runtime('PERITO_NODE', ['node'])
        chrome = _runtime('PERITO_CHROME', ['google-chrome', 'chromium', 'chromium-browser',
                          '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'])
        resources = Path(__file__).resolve().with_name('collector')
        with tempfile.TemporaryDirectory(prefix='perito-uf-') as directory:
            root, proc, control = Path(directory), None, None
            run = root / 'run'
            deadline = time.monotonic() + 180

            def alive():
                if time.monotonic() > deadline:
                    raise ValueError('UF collector exceeded bounded deadline')
                if (run / 'STOP.json').exists() or proc.poll() is not None:
                    raise ValueError('UF ordinary collector stopped; no export accepted')

            def command(op, **kwargs):
                alive()
                request = Request('http://127.0.0.1:' + str(control['port']) + '/',
                                  json.dumps(dict(op=op, **kwargs)).encode(),
                                  {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + control['token']})
                with urlopen(request, timeout=min(50, max(1, deadline-time.monotonic()))) as response:
                    payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise ValueError('UF control response exceeded bound')
                return json.loads(payload)

            def evaluate(expression, user_gesture=False):
                response = command('eval', expression=expression, userGesture=user_gesture)
                if response.get('exceptionDetails'):
                    raise ValueError('UF ordinary frontend contract failed')
                return response.get('result', {}).get('value')

            def wait(expression, seconds=60):
                end = min(deadline, time.monotonic() + seconds)
                while time.monotonic() < end:
                    if evaluate(expression):
                        return
                    time.sleep(.25)
                raise ValueError('UF ordinary frontend readiness timeout')

            try:
                with (root / 'launch.log').open('wb') as log:
                    proc = subprocess.Popen([node, str(resources / 'browser-probe.mjs'), str(run), chrome],
                                            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                            start_new_session=True)
                    end = time.monotonic() + 20
                    while not (run / 'control.json').exists():
                        alive()
                        if time.monotonic() > end:
                            raise ValueError('UF browser startup timeout')
                        time.sleep(.1)
                    control = json.loads((run / 'control.json').read_text())
                    wait('!!window.PEP_SERVICES?.qlik?.isInitialized()')
                    wait('window.PEP_APP?.getStatus().currentPage==="home" && window.PEP_APP?.getStatus().loadedPages.includes("home") && !window.PEP_APP?.getStatus().navigationStats.isNavigating')
                    evaluate('document.querySelector(\'a[href="#fvm"]\').click(); true')
                    wait('window.PEP_APP?.getStatus().currentPage==="fvm" && window.PEP_APP?.getStatus().loadedPages.includes("fvm") && !window.PEP_APP?.getStatus().navigationStats.isNavigating')
                    snapshot = evaluate((resources / 'collect-flow.js').read_text())
                    evaluate('(()=>{const b=document.querySelector("#download-csv-btn");if(!b||b.disabled||!b.closest("#page-fvm.active")||getComputedStyle(b).visibility!=="visible"||!b.offsetWidth)throw new Error("Public export not ready");b.click();return true;})()', user_gesture=True)
                    end = time.monotonic() + 45
                    while time.monotonic() < end:
                        alive()
                        trace = [json.loads(line) for line in (run / 'trace.jsonl').read_text().splitlines()]
                        completed = [t for t in trace if t['kind'] == 'Browser.downloadProgress' and t['state'] == 'completed']
                        if completed:
                            break
                        time.sleep(.25)
                    else:
                        raise ValueError('UF fresh download timeout')
                    if len(completed) != 1 or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', completed[0]['guid']):
                        raise ValueError('UF download identity mismatch')
                    path = run / 'downloads' / completed[0]['guid']
                    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
                        raise ValueError('UF owned workbook path/size invalid')
                    content = path.read_bytes()
                    if len(content) != completed[0]['receivedBytes']:
                        raise ValueError('UF download size mismatch')
                    command('stop')
                    proc.wait(timeout=10)
                    receipt = json.loads((run / 'end.json').read_text())
                    if proc.returncode or receipt['fatal'] or not receipt['browser_stopped'] or not receipt['clean_profile_removed']:
                        raise ValueError('UF collector cleanup failed')
                    return UFExport(content, {'snapshot': snapshot, 'trace': trace,
                                             'available_periods': snapshot['availablePeriods']})
            except (OSError, subprocess.SubprocessError, KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError(f'UF collector transport failed ({type(exc).__name__})') from exc
            finally:
                # The Node and Chrome descendants share our newly owned process group.
                # Kill any survivor even if Node exited before its own cleanup receipt.
                if proc is not None:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        pass
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait(timeout=3)
