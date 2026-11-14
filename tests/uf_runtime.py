"""Offline executable stand-in for Node/Chrome, at the external process boundary.

It replays saved source documents; it is NOT a collector or runtime qualification.
Only tests install this script as PERITO_NODE in a private temporary directory.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys


def main():
    if sys.argv[1:] == ['--version']:
        print('offline-process-stand-in (NOT a Node runtime proof)')
        return
    # Node argv: immutable browser script, new absolute owned run, Chrome executable.
    resource, run, chrome = map(Path, sys.argv[1:])
    if not resource.is_file() or not chrome.is_file() or not run.is_absolute() or run.exists():
        raise SystemExit(2)
    item = {}
    sequence = os.environ.get('PERITO_TEST_EXPORT_SEQUENCE')
    if sequence:
        sequence = Path(sequence)
        count = sequence.with_suffix('.count')
        index = int(count.read_text()) if count.exists() else 0
        count.write_text(str(index + 1))
        with sequence.with_suffix('.runs').open('a') as log:
            log.write(json.dumps({'run': str(run), 'pid': os.getpid()}) + '\n')
        item = json.loads(sequence.read_text())[index]
        content = Path(item['workbook']).read_bytes()
        evidence = json.loads(Path(item['evidence']).read_text())
    else:
        raise SystemExit('OFFLINE stand-in requires explicit document sequence')
    snapshot = evidence['snapshot']
    snapshot['availablePeriods'] = evidence['available_periods']
    run.mkdir()
    (run / 'downloads').mkdir()
    begin = next(t for t in evidence['trace'] if t['kind'] == 'Browser.downloadWillBegin')
    (run / 'downloads' / begin['guid']).write_bytes(content)
    (run / 'trace.jsonl').write_text(''.join(json.dumps(t) + '\n' for t in evidence['trace']))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.headers.get('Authorization') != 'Bearer controlled-test-token':
                self.send_error(403)
                return
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if request['op'] == 'stop':
                (run / 'end.json').write_text(json.dumps(item.get('cleanup', {
                    'fatal': None, 'browser_stopped': True, 'clean_profile_removed': True})))
                result = {'closing': True}
            else:
                # The saved export is returned for the ordinary FVM preparation;
                # readiness and installed-button gestures return true.
                value = snapshot if 'const cargos=' in request['expression'] else True
                result = {'result': {'value': value}}
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            if request['op'] == 'stop':
                self.server.finished = True

    with HTTPServer(('127.0.0.1', 0), Handler) as server:
        server.finished = False
        (run / 'control.json').write_text(json.dumps({'port': server.server_port, 'token': 'controlled-test-token'}))
        while not server.finished:
            server.handle_request()


if __name__ == '__main__':
    main()
