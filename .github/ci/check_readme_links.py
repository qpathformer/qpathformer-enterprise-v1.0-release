#!/usr/bin/env python3
"""Check tracked README Markdown links without accessing the network."""

import argparse
from html import unescape
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import posixpath
import subprocess
import sys
import unicodedata
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt


class HTMLReferences(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.anchors = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("id", "name" if tag == "a" else "id"):
            if attrs.get(key):
                self.anchors.add(attrs[key])
        key = "href" if tag == "a" else "src" if tag == "img" else None
        if key and key in attrs:
            self.links.append(attrs[key])

    handle_startendtag = handle_starttag


def heading_text(tokens):
    """Visible inline text, excluding Markdown formatting and HTML tags."""
    parts = []
    for token in tokens:
        if token.type in ("text", "code_inline"):
            parts.append(token.content)
        elif token.type in ("softbreak", "hardbreak"):
            parts.append(" ")
        elif token.type == "image":
            parts.append(heading_text(token.children or []))
    return unescape("".join(parts))


def heading_slug(text):
    # GitHub-style heading IDs: lowercase, retain hyphens/underscores, remove
    # punctuation and symbols, and replace whitespace with hyphens.
    cleaned = "".join(
        ch for ch in text.lower()
        if ch in "-_" or not unicodedata.category(ch).startswith(("P", "S", "C"))
    )
    return "".join("-" if ch.isspace() else ch for ch in cleaned)


def markdown_references(text):
    parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    # Inspect even non-renderable destinations (such as file: URLs) so the
    # checker can report them. Nothing is rendered, executed or fetched.
    parser.validateLink = lambda _url: True
    tokens = parser.parse(text)
    links, anchors, generated = [], set(), set()
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            base = heading_slug(heading_text(tokens[i + 1].children or []))
            slug, suffix = base, 0
            while slug in generated:
                suffix += 1
                slug = f"{base}-{suffix}"
            generated.add(slug)
            anchors.add(slug)
        line = token.map[0] + 1 if token.map else 1
        for child in [token, *(token.children or [])]:
            if child.type == "link_open":
                links.append((child.attrGet("href"), line))
            elif child.type == "image":
                links.append((child.attrGet("src"), line))
            elif child.type in ("html_inline", "html_block"):
                html = HTMLReferences()
                html.feed(child.content)
                anchors.update(html.anchors)
                links.extend((target, line) for target in html.links)
    return links, anchors


def tracked_files(root):
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) - {""}


def check(root):
    files = tracked_files(root)
    readmes = sorted(path for path in files if
                     "readme" in PurePosixPath(path).name.lower()
                     and path.lower().endswith(".md"))
    if "README.md" not in files:
        return ["README.md: root README is missing or untracked"], 0, 0, 0
    directories = {"."}
    for name in files:
        directories.update(str(p) for p in PurePosixPath(name).parents)
    cache = {}

    def parsed(name):
        if name not in cache:
            path = root / name
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("linked Markdown resolves outside the repository")
            cache[name] = markdown_references(path.read_text(encoding="utf-8-sig"))
        return cache[name]

    failures, local_count, external_count = [], 0, 0
    for readme in readmes:
        try:
            links, _ = parsed(readme)
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{readme}: {exc}")
            continue
        for target, line in links:
            location = f"{readme}:{line}: {target!r}"
            try:
                url = urlsplit(target)
                if url.scheme or url.netloc:
                    if url.scheme.lower() == "file":
                        raise ValueError("file URLs are not portable repository links")
                    external_count += 1
                    continue
                local_count += 1
                path = unquote(url.path)
                if "\\" in path:
                    raise ValueError("use forward slashes in repository links")
                if path.startswith("/"):
                    raise ValueError("use a relative repository path, not a site-root path")
                resolved = (posixpath.normpath(posixpath.join(posixpath.dirname(readme), path))
                            if path else readme)
                if resolved == ".." or resolved.startswith("../"):
                    raise ValueError("link escapes the repository")
                if resolved not in files and resolved not in directories:
                    raise ValueError("target is missing, untracked or has different letter case")
                if not (root / resolved).resolve().is_relative_to(root.resolve()):
                    raise ValueError("target resolves outside the repository")
                if path.endswith("/") and resolved not in directories:
                    raise ValueError("link treats a file as a directory")
                fragment = unquote(url.fragment)
                if fragment:
                    anchor_file = resolved
                    if resolved in directories:
                        prefix = "" if resolved == "." else resolved + "/"
                        candidates = sorted(f for f in files if
                            posixpath.dirname(f) == prefix.rstrip("/")
                            and PurePosixPath(f).name.lower() == "readme.md")
                        if not candidates:
                            raise ValueError("directory fragment has no README.md target")
                        anchor_file = candidates[0]
                    if anchor_file.lower().endswith(".md") and fragment not in parsed(anchor_file)[1]:
                        raise ValueError(f"heading or HTML anchor #{fragment} is missing")
            except (OSError, UnicodeError, ValueError) as exc:
                failures.append(f"{location}: {exc}")
    return failures, len(readmes), local_count, external_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        failures, readmes, local, external = check(args.root)
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        print(f"Cannot inspect tracked files: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("README link checks failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(f"PASS: {local} local links across {readmes} README files; "
          f"{external} external links excluded from this offline check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
