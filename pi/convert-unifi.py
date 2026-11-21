#!/usr/bin/env python3
"""Produce mixed bare IPv4 host / CIDR input for UniFi, preserving exact coverage."""
import argparse
import ipaddress
from pathlib import Path


def convert(lines):
    result = []
    for line_no, raw in enumerate(lines, 1):
        raw = raw.strip()
        if not raw or raw.startswith('#'):
            continue
        try:
            prefix = ipaddress.IPv4Network(raw, strict=True)
        except ValueError as exc:
            raise ValueError(f'line {line_no}: invalid canonical IPv4 network: {raw!r}') from exc
        result.append(str(prefix.network_address) if prefix.prefixlen == 32 else str(prefix))
    if not result:
        raise ValueError('source feed is empty')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    original = args.source.read_text(encoding='utf-8').splitlines()
    output = convert(original)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text('\n'.join(output) + '\n', encoding='utf-8')
    hosts = sum('/' not in entry for entry in output)
    print(f'UniFi list: {len(output)} total entries, {hosts} bare IPv4 host addresses, {len(output)-hosts} CIDRs')


if __name__ == '__main__':
    main()
