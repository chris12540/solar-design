"""Isolated source-case store for browser checks; real imagery is read-only."""
import tempfile,threading
from pathlib import Path
import server
from source_case_store import SourceCases
with tempfile.TemporaryDirectory(prefix='roof-source-case-check-') as directory:
    server.SOURCE_CASES=SourceCases(Path(directory),server.google_manifest,server.EXPECTED)
    threading.Thread(target=server.expiry_watch,daemon=True).start()
    print('Source-case verification server ready',flush=True)
    server.ThreadingHTTPServer(('127.0.0.1',server.PORT),server.Handler).serve_forever()
