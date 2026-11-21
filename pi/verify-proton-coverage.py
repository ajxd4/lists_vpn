#!/usr/bin/env python3
"""Fail the build unless every imported ProtonVPN IPv4 address is covered by the combined VPN output."""
import argparse
import bisect
import ipaddress
from pathlib import Path


def uncovered(expected_lines, combined_lines):
    ranges = []
    for line in combined_lines:
        value = line.strip()
        if value and not value.startswith('#'):
            network = ipaddress.IPv4Network(value, strict=True)
            ranges.append((int(network.network_address), int(network.broadcast_address)))
    if not ranges:
        raise ValueError('combined VPN IPv4 list is empty')
    ranges.sort()
    starts = [start for start, _ in ranges]
    # Even overlapping CIDRs are handled correctly: the rightmost network
    # start may be narrower than an earlier range with the same coverage.
    max_end = []
    highest = -1
    for _, end in ranges:
        highest = max(highest, end)
        max_end.append(highest)
    missing = []
    expected_count = 0
    for line in expected_lines:
        value = line.strip()
        if not value:
            continue
        addr = ipaddress.IPv4Address(value)
        expected_count += 1
        num = int(addr)
        index = bisect.bisect_right(starts, num) - 1
        if index < 0 or max_end[index] < num:
            missing.append(value)
    if not expected_count:
        raise ValueError('expected ProtonVPN feed is empty')
    return missing, expected_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('proton', type=Path)
    parser.add_argument('combined', type=Path)
    args = parser.parse_args()
    missing, total = uncovered(args.proton.read_text(encoding='utf-8').splitlines(),
                               args.combined.read_text(encoding='utf-8').splitlines())
    if missing:
        raise SystemExit(f'ERROR: {len(missing)} of {total} ProtonVPN addresses missing from combined VPN feed; first examples: {", ".join(missing[:8])}')
    print(f'ProtonVPN integration verified: all {total} addresses covered by combined VPN IPv4 feed')


if __name__ == '__main__':
    main()
