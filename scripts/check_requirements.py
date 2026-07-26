"""Fail if any import in src/ is missing from requirements.txt.

Written after a deploy crashed on `python-multipart`: it was installed locally for the
upload endpoint but never added to requirements, so the container died at import with
no local symptom. Run before deploying.
"""

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
# import name -> distribution name, where they differ
ALIASES = {"PIL": "pillow", "dotenv": "python-dotenv", "multipart": "python-multipart"}


def main() -> int:
    reqs = {line.split(">=")[0].split("==")[0].split("[")[0].strip().lower()
            for line in (ROOT / "requirements.txt").read_text().splitlines()
            if line.strip() and not line.startswith("#")}
    stdlib = set(sys.stdlib_module_names)
    missing = {}

    for path in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            else:
                continue
            for mod in mods:
                if mod in stdlib or mod == "src":
                    continue
                dist = ALIASES.get(mod, mod).lower()
                if dist not in reqs:
                    missing.setdefault(dist, set()).add(str(path.relative_to(ROOT)))

    if missing:
        print("requirements.txt is missing:")
        for dist, files in sorted(missing.items()):
            print(f"  {dist}  (imported by {', '.join(sorted(files))})")
        return 1
    print(f"all src/ imports are covered by requirements.txt ({len(reqs)} packages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
