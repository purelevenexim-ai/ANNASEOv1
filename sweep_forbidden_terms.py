#!/usr/bin/env python3
"""Sweep repository for forbidden seed-related terms and optionally clean test files."""
import argparse
import os
import re

FORBIDDEN = [
    "clove", "turmeric", "cinnamon", "ginger", "cardamom", "pepper", "nutmeg", "cumin", "coriander",
    "fenugreek", "anise", "basil"
]
EXTENSIONS = [".py", ".md", ".html", ".js", ".ts", ".json"]


def scan_file(path, forbidden):
    hits = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f, 1):
            low = line.lower()
            for token in forbidden:
                if token in low:
                    hits.append((i, token, line.rstrip("\n")))
    return hits


def replace_terms_in_file(path, forbidden):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    orig = text
    for token in forbidden:
        pattern = re.compile(re.escape(token), re.IGNORECASE)
        text = pattern.sub("<generic>", text)
    if text != orig:
        with open(path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(text)
    return text != orig


def main():
    p = argparse.ArgumentParser(description="Sweep repo for forbidden terms")
    p.add_argument("--root", default=".", help="Repository root path")
    p.add_argument("--apply", action="store_true", help="Replace forbidden terms with <generic> in matching files")
    p.add_argument("--tests-only", action="store_true", help="Only process tests folders (pytests, tests)")
    args = p.parse_args()

    report = {}

    for dirpath, dirnames, filenames in os.walk(args.root):
        if args.tests_only and not any(x in dirpath for x in ["/tests", "/pytests"]):
            continue
        # skip hidden and virtual env directories
        if any(part.startswith(".") for part in dirpath.split(os.sep)):
            continue
        if "node_modules" in dirpath or "__pycache__" in dirpath:
            continue

        for fn in filenames:
            if not any(fn.endswith(ext) for ext in EXTENSIONS):
                continue
            path = os.path.join(dirpath, fn)
            hits = scan_file(path, FORBIDDEN)
            if hits:
                report[path] = hits
                if args.apply and ("/tests/" in path or "/pytests/" in path):
                    replaced = replace_terms_in_file(path, FORBIDDEN)
                    if replaced:
                        print(f"[APPLIED] {path}")

    if not report:
        print("No forbidden terms found.")
        return

    for path, hits in report.items():
        print(f"\n{path} - {len(hits)} hits")
        for line_no, token, line in hits[:10]:
            print(f"  {line_no}: {token} -> {line}")

    total = sum(len(hits) for hits in report.values())
    print(f"\nTotal forbidden hits: {total}")


if __name__ == "__main__":
    main()
