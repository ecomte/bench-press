#!/usr/bin/env python3
"""Build the hosted site locally and serve it at http://localhost:8000.

Runs the same build GitHub Actions does, but into test-website/ (git ignores it),
then serves that folder until you press Ctrl+C.

examples:
  python3 test-website.py                  build everyone in batch_users, then serve
  python3 test-website.py -w 8             any extra arguments go to batchbenchpress.py
  python3 test-website.py ryaneorchard     just one person
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = "test-website"
PORT = "8000"


def main():
    os.chdir(HERE)
    build = [sys.executable, "batchbenchpress.py", "--no-open", "--site", OUT, *sys.argv[1:]]
    if subprocess.call(build) != 0:
        sys.exit("Build failed; not starting the server.")
    print(f"\nServing {OUT}/ at http://localhost:{PORT}/  (Ctrl+C to stop)")
    try:
        subprocess.call([sys.executable, "-m", "http.server", PORT, "-d", OUT])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
