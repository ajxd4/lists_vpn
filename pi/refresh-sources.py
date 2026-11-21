#!/usr/bin/env python3
"""Refresh provider feeds directly on the Pi into a staging copy of input/vpn/ips.

No X4BNet finished outputs or scheduled GitHub Actions are consulted.
On any source validation or download failure this process exits nonzero.
"""
import argparse
import csv
import io
import ipaddress
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

MULLVAD = 'https://api.mullvad.net/www/relays/all/'
PIA = 'https://serverlist.piaservers.net/vpninfo/servers/v6'
APPLE = 'https://mask-api.icloud.com/egress-ip-ranges.csv'
PROTON = 'https://raw.githubusercontent.com/tn3w/ProtonVPN-IPs/refs/heads/master/protonvpn_ips.txt'  # Third-party, advertised exit IPs
MAX_BYTES = 25_000_000


def download(url):
    last_error = None
    for attempt in range(3):
        try:
            request = Request(url, headers={'User-Agent': 'pi-vpn-builder/1.0 (+https://github.com/X4BNet/lists_vpn)', 'Accept': 'application/json,text/csv,*/*'})
            with urlopen(request, timeout=45) as response:
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError(f'provider response exceeds {MAX_BYTES} bytes: {url}')
                if not data:
                    raise ValueError(f'empty response from: {url}')
                return data.decode('utf-8-sig')
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f'could not retrieve {url}: {last_error}')


def public_v4(value):
    try:
        ip = ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None
    return str(ip) if ip.version == 4 and ip.is_global else None


def mullvad():
    data = json.loads(download(MULLVAD))
    if not isinstance(data, list):
        raise ValueError('Mullvad API structure is not an array')
    return [entry['ipv4_addr_in'] for entry in data if isinstance(entry, dict) and entry.get('ipv4_addr_in')]


def pia():
    # PIA returns newline-delimited signed response; first line is JSON.
    data = json.loads(download(PIA).splitlines()[0])
    if not isinstance(data, dict) or not isinstance(data.get('regions'), list):
        raise ValueError('PIA API schema changed: regions array missing')
    found = []
    def scan(value):
        if isinstance(value, dict):
            if 'ip' in value and isinstance(value['ip'], str):
                found.append(value['ip'])
            for child in value.values():
                scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)
    for region in data['regions']:
        if isinstance(region, dict):
            scan(region.get('servers', {}))
    return found


def apple():
    data = csv.reader(io.StringIO(download(APPLE)))
    found = []
    for row in data:
        if not row:
            continue
        val = row[0].strip()
        if ':' in val or val.lower() in ('ip prefix', 'ip prefix/length', 'ip prefix/length (cidr)'):
            continue
        try:
            net = ipaddress.IPv4Network(val, strict=False)
        except ValueError as exc:
            raise ValueError(f'Apple API invalid IPv4 prefix: {val!r}') from exc
        if net.is_global:
            found.append(str(net))
    return found


def proton():
    """Parse the independent tn3w ProtonVPN exit-address feed.

    Ignore comments and blank lines, but fail closed on malformed data. The
    normalized output is plain bare IPv4 addresses, never /24 expansions.
    """
    addresses = []
    for line_no, raw in enumerate(download(PROTON).splitlines(), 1):
        token = raw.split('#', 1)[0].strip()
        if not token:
            continue
        try:
            address = ipaddress.IPv4Address(token)
        except ValueError as exc:
            raise ValueError(f'ProtonVPN feed line {line_no}: invalid IPv4 address {token!r}') from exc
        if not address.is_global:
            raise ValueError(f'ProtonVPN feed line {line_no}: non-public IPv4 address {token!r}')
        addresses.append(str(address))
    return addresses


def normalize(name, candidates, minimum, maximum, allow_cidr=False):
    found = set()
    for token in candidates:
        if allow_cidr:
            value = str(ipaddress.IPv4Network(str(token).strip(), strict=False))
            if not ipaddress.IPv4Network(value).is_global:
                continue
        else:
            value = public_v4(token)
            if value is None:
                continue
        found.add(value)
    if not (minimum <= len(found) <= maximum):
        raise ValueError(f'{name}: unexpected entry count {len(found)} (expected {minimum}..{maximum}); refusing update')
    return sorted(found, key=lambda entry: (int(ipaddress.IPv4Network(entry, strict=False).network_address),
                                             ipaddress.IPv4Network(entry, strict=False).prefixlen))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True, help='STAGING input directory (not live repo)')
    args = parser.parse_args()
    targets = [
        ('mullvadvpn.txt', mullvad, 150, 20000, False),
        ('pia.txt', pia, 100, 50000, False),
        ('apple.txt', apple, 25, 50000, True),
        ('protonvpn.txt', proton, 100, 50000, False),
    ]
    # No files are changed until ALL fetches and validations succeed.
    prepared = {}
    for name, getter, minimum, maximum, cidr in targets:
        values = normalize(name, getter(), minimum, maximum, cidr)
        prepared[name] = '\n'.join(values) + '\n'
        print(f'{name}: validated {len(values)} records', file=sys.stderr)
    destination = args.input_dir / 'vpn' / 'ips'
    if not destination.is_dir():
        raise FileNotFoundError(f'missing source input directory: {destination}')
    for name, contents in prepared.items():
        (destination / name).write_text(contents, encoding='utf-8')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f'ERROR: provider refresh failed: {exc}', file=sys.stderr)
        sys.exit(1)
