#!/usr/bin/env python3
"""Fail the build unless every imported ProtonVPN entry address is covered by VPN output."""
import argparse
import bisect
import ipaddress
from pathlib import Path


def uncovered(expected_lines, combined_lines):
    expected = [line.strip() for line in expected_lines if line.strip()]
    if not expected:
        raise ValueError('expected ProtonVPN entry feed is empty')
    version = ipaddress.ip_address(expected[0]).version
    ranges = []
    for line in combined_lines:
        value = line.strip()
        if value and not value.startswith('#'):
            network = ipaddress.ip_network(value, strict=True)
            if network.version != version:
                raise ValueError('mixed address families in combined VPN output')
            ranges.append((int(network.network_address), int(network.broadcast_address)))
    if not ranges:
        raise ValueError('combined VPN list is empty')
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
    for value in expected:
        addr = ipaddress.ip_address(value)
        if addr.version != version:
            raise ValueError('mixed address families in ProtonVPN entry input')
        expected_count += 1
        num = int(addr)
        index = bisect.bisect_right(starts, num) - 1
        if index < 0 or max_end[index] < num:
            missing.append(value)
    return missing, expected_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('proton', type=Path)
    parser.add_argument('combined', type=Path)
    args = parser.parse_args()
    missing, total = uncovered(args.proton.read_text(encoding='utf-8').splitlines(),
                               args.combined.read_text(encoding='utf-8').splitlines())
    if missing:
        raise SystemExit(f'ERROR: {len(missing)} of {total} ProtonVPN entry addresses missing from combined VPN feed; first examples: {", ".join(missing[:8])}')
    print(f'ProtonVPN entry integration verified: all {total} addresses covered by combined VPN feed')


if __name__ == '__main__':
    main()
