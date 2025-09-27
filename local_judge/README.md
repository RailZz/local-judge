Local Judge Desktop App

Features
- Choose solution file (Python, C, C++ supported)
- Choose tests directory and specify input/output filename patterns using a simple template with {num}
- Optional custom checker executable with argument template
- Set time limit (seconds) and memory limit (MB)
- Run tests and see per-test verdict, time, and memory usage

Patterns
- Use {num} placeholder for test index, for example:
  - Input pattern: {num}.in, Output pattern: {num}.out
  - Input pattern: {num}, Output pattern: {num}.a
  - Input pattern: test{num}.txt, Output pattern: test{num}.ans
- The app scans the directory and matches inputs by converting {num} to (\d+).
  The exact matched number string (with leading zeros preserved) is used to find the expected output.

Checker
- Optional path to a checker executable or script.
- Argument template supports tokens: {in}, {ans}, {out}
  - {in}: path to input file
  - {ans}: path to expected output file (if available)
  - {out}: path to contestant output file (program output)
- Exit code 0 is considered Accepted; non-zero is Wrong Answer. Stdout/stderr are captured in Details.

Limits
- Time limit uses wall-clock timeout (TLE) and CPU/memory resource limits where supported.
- Memory limit enforced using RLIMIT_AS (address space) and live RSS sampling; exceeding triggers MLE.

Development
1) Install dependencies:
   pip install -r requirements.txt
2) Run the app:
   python3 main.py
3) Optional: run headless smoke test:
   python3 tools/smoke.py

Notes
- Requires gcc/g++ for C/C++ compilation.
- Python solutions run with the system's python3 interpreter.
