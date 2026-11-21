# Raspberry Pi autonomous X4BNet-compatible list builder

**Run this inside a FULL clone of your OWN fork of** `X4BNet/lists_vpn`. The ZIP contains Pi-specific additions, **not** a bundled copy of the upstream repository. Clone your fork normally; this retains all upstream source, curated ASN/keyword rules, helper scripts, and manual lists.

## What builds the data?

The fork's `build-local.sh` and `helpers/asn_to_cidr.py` implement the original builder, not just a list reformatter. The Pi calls the upstream builder locally, using `--database-source iplocate --family all --list all --input-dir` and publishes original VPN/datacenter IPv4/IPv6 lists, plus a UniFi-compatible mixed IPv4 list. The Pi downloads IPLocate's live IP-to-ASN database (or IPtoASN with an env override) directly; it **does not fetch X4BNet's generated output**. Provider fetchers run locally.

Sources:

- ASN/keywords: your fork's `input/vpn/ASN.txt`, `input/datacenter/ASN.txt`, `input/*/Keywords.txt`, plus manual `input/*/ips/*.txt`. These are maintained by YOU after forking and do not auto-sync upstream.
- BGP-derived IP-to-ASN mapping: IPLocate (`media.githubusercontent.com/media/iplocate/...`) or optional IPtoASN, fetched by the original `build-local.sh` itself.
- Mullvad: `api.mullvad.net/www/relays/all/` (direct relay IPs).
- PIA: `serverlist.piaservers.net/vpninfo/servers/v6` (direct provider catalog; JSON first line of signed response, server `ip` fields).
- Apple Private Relay: `mask-api.icloud.com/egress-ip-ranges.csv` (IPv4 CIDRs).
- ProtonVPN: **disabled by default**, matching upstream's disabled automated workflow. Set `PI_INCLUDE_PROTON=1` to refresh its logical server exits via `api.protonmail.ch/vpn/logicals`. This is opt-in and may fail if API changes.
- `input/vpn/ips/Manual.txt` and legacy provider snapshots are preserved from the fork.

PIA is fetched directly rather than using the separate third-party PIA CSV that upstream's GitHub workflow uses, so the data may differ somewhat. Direct provider catalogs and IP-to-ASN databases remain external dependencies; independence means **your Pi performs the build and your fork controls the rules and output**, not that the Pi magically discovers VPN addresses without third-party feeds.

## Prerequisites on Debian 13 Raspberry Pi 5

All commands below are one-line Bash commands. Replace `YOUR_USERNAME` with your GitHub account username. Before starting, use GitHub's **Fork** control to create `YOUR_USERNAME/lists_vpn`. Do **not** make `X4BNet/lists_vpn` the origin of a writable checkout.

Install dependencies:

`sudo apt-get update && sudo apt-get install -y git python3 perl curl openssh-client util-linux unzip`

Clone entire fork into home directory:

`git clone https://github.com/YOUR_USERNAME/lists_vpn.git "$HOME/lists_vpn" && git -C "$HOME/lists_vpn" remote set-url origin git@github.com:YOUR_USERNAME/lists_vpn.git`

Copy `pi-vpn-builder-overlay.zip` to the Pi's home directory, and extract:

`unzip -o "$HOME/pi-vpn-builder-overlay.zip" -d "$HOME/lists_vpn" && chmod +x "$HOME/lists_vpn"/pi/*.sh "$HOME/lists_vpn"/pi/*.py`

**Disable upstream GitHub Actions in your fork** in Settings > Actions > General (disable Actions for the repository). Upstream workflows include scheduled builders and provider fetchers that would otherwise compete with the Pi. Your Pi doesn't require Actions. Do this before pushing the Pi additions.

## GitHub authentication using a scoped write deploy key

Generate a key specifically for this fork (only on Pi):

`mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh" && ssh-keygen -t ed25519 -C 'pi-lists-vpn' -f "$HOME/.ssh/lists_vpn_deploy" -N '' && chmod 600 "$HOME/.ssh/lists_vpn_deploy" && cat "$HOME/.ssh/lists_vpn_deploy.pub"`

On GitHub open YOUR fork → Settings → Deploy keys → Add deploy key, paste the displayed PUBLIC key, and select **Allow write access**. GitHub deploy keys are scoped to one repository. Never put the private key in the fork or ZIP.

Verify GitHub's SSH host key fingerprint against https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints and manually accept only if it matches:

`ssh -i "$HOME/.ssh/lists_vpn_deploy" -o IdentitiesOnly=yes -T git@github.com`

Test the checkout and Python scripts, then commit overlay additions:

`cd "$HOME/lists_vpn" && for f in pi/*.sh; do bash -n "$f" || exit 1; done && python3 -m unittest discover -s pi/tests -v && git add pi README-PI.md && git -c user.name='Pi VPN List Builder' -c user.email='pi-vpn-builder@users.noreply.github.com' commit -m 'Add Raspberry Pi independent builder' && GIT_SSH_COMMAND="ssh -i $HOME/.ssh/lists_vpn_deploy -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes" git push origin main`

Note: `README-PI.md` is at the root of the overlay ZIP and is included above. If the fork is protected, allow this deploy key to push to main or use a separate publish branch.

## First run / timer

Initial cautious run without committing or pushing: 

`cd "$HOME/lists_vpn" && PI_DRY_RUN=1 bash pi/build-and-publish.sh`

First live publication (only after successful dry run):

`cd "$HOME/lists_vpn" && bash pi/build-and-publish.sh`

Create a per-user systemd timer every 6 hours (the script assumes a clone without whitespace in its path):

`cd "$HOME/lists_vpn" && bash pi/install-user-timer.sh && sudo loginctl enable-linger "$USER"`

Check timer and service logs:

`systemctl --user list-timers pi-vpn-builder.timer && journalctl --user -u pi-vpn-builder.service -n 100 --no-pager`

To start a scheduled job immediately:

`systemctl --user start pi-vpn-builder.service`

## UniFi URL

Set `vpnv4` Dynamic Network List URL to:

`https://raw.githubusercontent.com/YOUR_USERNAME/lists_vpn/main/output/unifi/vpn/ipv4.txt`

The converter strips **only** terminal `/32` suffixes, leaving subnet ranges intact and no additional IPs blocked. UniFi should show the individual hosts plus subnet entries. Verify by testing a small sample on your firmware before enabling blanket blocking.

## Optional settings

Set environment variables in the `pi-vpn-builder.service` unit, then run `systemctl --user daemon-reload`:

- `PI_WORK_ROOT=/mnt/storage/...` — stage large downloads on the Pi's external SSD instead of `/var/tmp`. The directory must already exist and be writable.
- `PI_DATABASE_SOURCE=iptoasn` — use the public IPtoASN alternative; **does not support keyword matching**, unlike IPLocate, so changes the generated list.
- `PI_DATABASE_DIR=/path/to/databases` — select local database snapshots rather than fetching current source; needs source-specific files per `build-local.sh --help`.
- `PI_REFRESH_PROVIDERS=0` — emergency diagnostic offline test with cloned provider snapshots, not recommended for scheduled updates.
- `PI_INCLUDE_PROTON=1` — optional live Proton refresh; default off.
- `PI_DRY_RUN=1` — validate without publishing; no files are changed in the repo by the builder.

If database/provider API, validation, git authentication, or push fails, **no broken update is published**. Failed pushes may leave a local commit; investigate using `git status`, `git log`, and `git push` rather than force-resetting blindly. If a successful validation changed staged files but an error happened before commit, the repo may need manual recovery. There is no automatic upstream pull, force-push, or automatic change to curated ASNs.

## Publication and attribution

The repository software, curated input and original generated lists are MIT licensed. IPLocate ASN database is CC BY-SA 4.0; the Pi also publishes the original builder's `output/ASN-DATABASE.txt` attribution. Consult upstream database redistribution terms before distributing these derived data products. The provider APIs may have separate terms. Keep original project credits and copyright/license notices in your fork.

The original X4BNet workflow validates VPN IPv4 coverage between 2M and 4M addresses and datacenter between 250M and 425M, which this builder replicates. Those are **address coverage thresholds**, not line counts. When upstream classification or current data change significantly, the builder may intentionally stop until you review the limits.
