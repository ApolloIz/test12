#!/usr/bin/env python3
"""SeatGeek inventory monitor.

Loads the event page in a real browser, captures the listings JSON the page
fetches, and alerts when the configured sections/rows have >= min_seats.

  python monitor.py --once      # check now, then exit
  python monitor.py             # run forever on the configured schedule
  python monitor.py --dump      # check now and save raw listing JSON for debugging
"""
import argparse, json, re, subprocess, sys, time, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SECTION_KEYS = ("s", "section", "section_name", "sectionName")
ROW_KEYS = ("r", "row", "row_name", "rowName")
QTY_KEYS = ("q", "quantity", "qty", "ticket_quantity", "available_quantity")


def load_config(path):
    return json.loads(Path(path).read_text())


def norm(v):
    """'Section 205' -> '205', 'Row 9' -> '9'."""
    s = str(v).strip().upper()
    m = re.search(r"\d+[A-Z]?$", s) or re.search(r"\d+", s)
    return m.group(0) if m else s


def pick(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def extract_listings(obj, out):
    """Walk any JSON shape and collect dicts that look like listings."""
    if isinstance(obj, dict):
        sec, qty = pick(obj, SECTION_KEYS), pick(obj, QTY_KEYS)
        if sec is not None and isinstance(qty, (int, float)):
            out.append({"section": norm(sec), "row": norm(pick(obj, ROW_KEYS) or ""), "qty": int(qty)})
        for v in obj.values():
            extract_listings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            extract_listings(v, out)
    return out


def fetch_listings(url, dump=False):
    from playwright.sync_api import sync_playwright
    payloads = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headful passes bot checks far more often
        page = browser.new_page()

        def on_response(resp):
            if "listing" in resp.url and "json" in resp.headers.get("content-type", ""):
                try:
                    payloads.append(resp.json())
                except Exception:
                    pass

        page.on("response", on_response)
        page.goto(url, timeout=90000)
        page.wait_for_timeout(15000)
        browser.close()
    if dump:
        (HERE / "last_listings.json").write_text(json.dumps(payloads, indent=1))
    if not payloads:
        raise RuntimeError("No listing data captured (page blocked or layout changed). Try --dump.")
    return extract_listings(payloads, [])


def evaluate(cfg, listings):
    """Return list of (label, seats) meeting the threshold."""
    hits = []
    for t in cfg["targets"]:
        for sec in t["sections"]:
            rows = [l for l in listings if l["section"] == norm(sec)
                    and (not cfg.get("match_row", True) or not t.get("row") or l["row"] == norm(t["row"]))]
            if not rows:
                continue
            seats = (sum(l["qty"] for l in rows) if cfg.get("count_mode", "total") == "total"
                     else max(l["qty"] for l in rows))
            if seats >= cfg["min_seats"]:
                label = f"Sec {sec}" + (f" Row {t['row']}" if cfg.get("match_row", True) and t.get("row") else "")
                hits.append((label, seats))
    return hits


def notify(cfg, title, msg):
    print(f"[ALERT] {title}: {msg}")
    n = cfg.get("notify", {})
    if n.get("mac_notification") and sys.platform == "darwin":
        subprocess.run(["osascript", "-e", f'display notification {json.dumps(msg)} with title {json.dumps(title)} sound name "Glass"'])
    if n.get("ntfy_topic"):
        urllib.request.urlopen(urllib.request.Request(
            f"https://ntfy.sh/{n['ntfy_topic']}", data=msg.encode(), headers={"Title": title}), timeout=20)
    if n.get("discord_webhook"):
        urllib.request.urlopen(urllib.request.Request(
            n["discord_webhook"], data=json.dumps({"content": f"**{title}**\n{msg}"}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "seatgeek-monitor"}), timeout=20)


def check(cfg, dump=False):
    listings = fetch_listings(cfg["event_url"], dump)
    hits = evaluate(cfg, listings)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"{stamp}  {len(listings)} listings scanned, {len(hits)} target(s) at >= {cfg['min_seats']} seats")
    if hits:
        notify(cfg, "Monster Jam seats available",
               "; ".join(f"{l}: {s} seats" for l, s in hits) + f"\n{cfg['event_url']}")
    return hits


def checks_per_day(cfg, now):
    event = datetime.fromisoformat(cfg["event_datetime"])
    days_out = (event - now.astimezone(event.tzinfo)).total_seconds() / 86400
    if days_out < 0:
        return 0
    for tier in sorted(cfg["schedule"], key=lambda t: -t["days_out_more_than"]):
        if days_out > tier["days_out_more_than"]:
            return tier["checks_per_day"]
    return cfg["schedule"][-1]["checks_per_day"]


def next_run(cfg, now):
    """Next slot: N checks evenly spaced across the day starting at first_check_hour."""
    n = checks_per_day(cfg, now)
    if n == 0:
        return None
    start = now.replace(hour=cfg.get("first_check_hour", 9), minute=0, second=0, microsecond=0)
    for day in range(3):
        for i in range(n):
            t = start + timedelta(days=day, hours=i * 24 / n)
            if t > now:
                return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dump", action="store_true")
    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.once or a.dump:
        check(cfg, a.dump)
        return
    while True:
        cfg = load_config(a.config)  # pick up edits without restarting
        t = next_run(cfg, datetime.now().astimezone())
        if t is None:
            print("Event has passed; stopping.")
            return
        print(f"Next check at {t:%Y-%m-%d %H:%M} ({checks_per_day(cfg, t)}x/day)")
        time.sleep(max(0, (t - datetime.now().astimezone()).total_seconds()))
        try:
            check(cfg)
        except Exception as e:
            print(f"Check failed: {e}")


if __name__ == "__main__":
    main()
