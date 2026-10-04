# SeatGeek inventory monitor

Watches one SeatGeek event and alerts you when any of the target section/row combos has at least `min_seats` seats listed.

**Run it on your own Mac.** SeatGeek's bot protection blocks cloud and datacenter IPs, including GitHub Actions.

## Setup
```bash
pip3 install playwright
python3 -m playwright install chromium
python3 monitor.py --dump   # one test check; also saves the raw data to last_listings.json
python3 monitor.py          # keep running; leave the terminal open
```

## Settings (`config.json`, re-read before every check)
| key | meaning |
|---|---|
| `targets` | sections plus the row to watch for each (copied from your screenshot) |
| `min_seats` | alert threshold (10) |
| `count_mode` | `total` adds up all listings in that section/row; `single` needs one listing with ≥ min_seats |
| `match_row` | `false` = any row in the section counts |
| `schedule` | tiers: more than 14 days out → 1 check/day, otherwise 3/day. Change these numbers or add tiers as you like |
| `first_check_hour` | hour of the first daily check; the rest are spaced evenly (3/day = 9:00, 17:00, 01:00) |
| `notify` | Mac pop-up, plus an optional [ntfy.sh](https://ntfy.sh) topic (phone push) or Discord webhook |

## Run in the background (recommended)
```bash
./install_mac.sh            # installs dependencies, starts at every login, runs a test check
tail -f monitor.log         # see what it's doing
./install_mac.sh uninstall  # stop and remove
```
Your Mac must be awake at check times; a check missed during sleep runs at the next slot.
