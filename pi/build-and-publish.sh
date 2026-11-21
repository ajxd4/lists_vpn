#!/usr/bin/env bash
# Raspberry Pi is the sole builder and publisher; requires a clean fork checkout.
set -Eeuo pipefail
umask 077
export LC_ALL=C
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$repo"
[[ -f ./build-local.sh && -f ./helpers/asn_to_cidr.py ]] || { echo 'ERROR: full upstream repository is required' >&2; exit 1; }
[[ -d .git ]] || { echo 'ERROR: must run inside a clone of your GitHub fork' >&2; exit 1; }
for tool in git python3 perl curl flock; do command -v "$tool" >/dev/null || { echo "ERROR: missing $tool" >&2; exit 1; }; done
[[ "$(git branch --show-current)" == main ]] || { echo 'ERROR: checkout branch main before running' >&2; exit 1; }
remote="$(git remote get-url origin)"
[[ "$remote" == *github.com* && "$remote" != *X4BNet/lists_vpn* ]] || { echo "ERROR: origin must be YOUR fork, not upstream: $remote" >&2; exit 1; }
[[ "$remote" == git@* || "$remote" == ssh://* ]] || { echo 'ERROR: origin must be SSH to allow deploy-key publishing' >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'ERROR: repo has local modifications; commit/stash them first' >&2; exit 1; }
# Exactly one running publisher per checkout, including manual runs.
exec 9>"$repo/.git/pi-publisher.lock"
flock -n 9 || { echo 'Another Pi builder is running' >&2; exit 1; }
key="${PI_DEPLOY_KEY:-$HOME/.ssh/lists_vpn_deploy}"
if [[ -f "$key" ]]; then
    export GIT_SSH_COMMAND="ssh -i $key -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes"
fi
# Only sync with user's own fork. Never fetch X4BNet upstream or prebuilt lists.
git fetch --quiet origin main
git merge --ff-only origin/main >/dev/null
work_root="${PI_WORK_ROOT:-/var/tmp}"
mkdir -p "$work_root"
work="$(mktemp -d "$work_root/lists-vpn-pi.XXXXXXXX")"
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/input" "$work/generated"
cp -a input/. "$work/input/"
if [[ "${PI_REFRESH_PROVIDERS:-1}" == 1 ]]; then
    extra=()
    [[ "${PI_INCLUDE_PROTON:-0}" == 1 ]] && extra+=(--include-proton)
    python3 pi/refresh-sources.py --input-dir "$work/input" "${extra[@]}"
else
    echo 'WARNING: provider refresh disabled, using checked-in snapshot' >&2
fi
build_args=(--database-source "${PI_DATABASE_SOURCE:-iplocate}" --family all --list all --input-dir "$work/input" --output-dir "$work/generated")
if [[ -n "${PI_DATABASE_DIR:-}" ]]; then
    build_args+=(--database-dir "$PI_DATABASE_DIR")
fi
./build-local.sh "${build_args[@]}"
# Same scale validation as upstream GitHub workflow (adjust only after reviewing upstream data changes).
python3 helpers/asn_to_cidr.py validate --family 4 --input "$work/generated/vpn/ipv4.txt" --min-addresses 2000000 --max-addresses 4000000
python3 helpers/asn_to_cidr.py validate --family 4 --input "$work/generated/datacenter/ipv4.txt" --min-addresses 250000000 --max-addresses 425000000
python3 helpers/asn_to_cidr.py validate --family 6 --input "$work/generated/vpn/ipv6.txt" --require-nonempty
python3 helpers/asn_to_cidr.py validate --family 6 --input "$work/generated/datacenter/ipv6.txt" --require-nonempty
python3 pi/convert-unifi.py "$work/generated/vpn/ipv4.txt" "$work/generated/unifi/vpn/ipv4.txt"
if [[ "${PI_DRY_RUN:-0}" == 1 ]]; then
    echo 'DRY RUN: lists generated and validated; no repo files modified or published.'
    wc -l "$work/generated/vpn/ipv4.txt" "$work/generated/unifi/vpn/ipv4.txt" "$work/generated/datacenter/ipv4.txt"
    exit 0
fi
mkdir -p output/vpn output/datacenter output/unifi/vpn
for category in vpn datacenter; do
    for family in ipv4 ipv6; do
        cp "$work/generated/$category/$family.txt" "output/$category/$family.txt"
    done
done
cp "$work/generated/unifi/vpn/ipv4.txt" output/unifi/vpn/ipv4.txt
cp "$work/generated/ipv4.txt" ipv4.txt
if [[ -f "$work/generated/ASN-DATABASE.txt" ]]; then
    cp "$work/generated/ASN-DATABASE.txt" output/ASN-DATABASE.txt
fi
if [[ "${PI_REFRESH_PROVIDERS:-1}" == 1 ]]; then
    for name in mullvadvpn.txt pia.txt apple.txt; do
        cp "$work/input/vpn/ips/$name" "input/vpn/ips/$name"
    done
    if [[ "${PI_INCLUDE_PROTON:-0}" == 1 ]]; then
        cp "$work/input/vpn/ips/protonvpn.txt" input/vpn/ips/protonvpn.txt
    fi
fi
# Explicit paths prevent accidentally committing credentials, scratch files, etc.
git add -- ipv4.txt output/vpn/ipv4.txt output/vpn/ipv6.txt output/datacenter/ipv4.txt output/datacenter/ipv6.txt output/unifi/vpn/ipv4.txt
[[ -f output/ASN-DATABASE.txt ]] && git add -- output/ASN-DATABASE.txt
[[ "${PI_REFRESH_PROVIDERS:-1}" == 1 ]] && git add -- input/vpn/ips/mullvadvpn.txt input/vpn/ips/pia.txt input/vpn/ips/apple.txt
[[ "${PI_INCLUDE_PROTON:-0}" == 1 ]] && git add -- input/vpn/ips/protonvpn.txt
if git diff --cached --quiet; then
    echo 'No changes. Nothing to publish.'
    exit 0
fi
git -c user.name='Pi VPN List Builder' -c user.email='pi-vpn-builder@users.noreply.github.com' commit -m "Refresh Pi-built VPN and datacenter feeds" >/dev/null
git push origin HEAD:main
echo "Published $(date -u +'%Y-%m-%dT%H:%M:%SZ') to $remote"
