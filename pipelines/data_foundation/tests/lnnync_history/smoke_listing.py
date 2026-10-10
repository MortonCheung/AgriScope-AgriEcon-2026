"""冒烟测试：验证列表发现能真实遍历全部分页（不是只抓第一页）。"""
from pathlib import Path
import sys

sys.path.insert(0, str(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())))

import yaml
from crawler import PROJECT_ROOT
from crawler.client import HttpClient
from crawler.listing import discover_category, load_known_urls, write_index

cfg = yaml.safe_load((PROJECT_ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
base = cfg["site"]["base_url"]
req = cfg["request"]

client = HttpClient(
    min_interval=req["min_interval_sec"],
    max_interval=req["max_interval_sec"],
    connect_timeout=req["connect_timeout"],
    read_timeout=req["read_timeout"],
    max_retries=req["max_retries"],
    backoff=req["backoff_sec"],
    retry_on_status=req["retry_on_status"],
    user_agent=req["user_agent"],
)

all_refs = []
for cat in cfg["categories"]:
    if not cat.get("enabled"):
        continue
    refs = discover_category(client, cat["key"], cat["name"], cat["path"], base)
    print(f"[结果] {cat['name']}: {len(refs)} 篇", flush=True)
    if refs:
        print(f"        最新 {refs[0].list_date} | {refs[0].title[:40]}")
        print(f"        最老 {refs[-1].list_date} | {refs[-1].title[:40]}")
    all_refs.extend(refs)

print(f"\n合计发现 {len(all_refs)} 篇")
write_index(all_refs)
