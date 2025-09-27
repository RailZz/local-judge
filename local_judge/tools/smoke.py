import os
import sys
from judge.runner import JudgeRunner, JudgeConfig


def main() -> int:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sol = os.path.join(root, "samples", "solutions", "echo.py")
    tests = os.path.join(root, "samples", "tests")
    cfg = JudgeConfig(
        solution_path=sol,
        language="Python",
        tests_dir=tests,
        input_pattern="{num}.in",
        ans_pattern="{num}.out",
        checker_path=None,
        checker_args_template=None,
        time_limit_s=1.0,
        memory_limit_mb=128,
        ignore_whitespace=True,
    )
    runner = JudgeRunner()
    err = runner.prepare(cfg)
    if err:
        print("Compile error:")
        print(err)
        return 1
    results = list(runner.run_all(cfg))
    for r in results:
        print(r)
    if not results or any(r.verdict != "AC" for r in results):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

