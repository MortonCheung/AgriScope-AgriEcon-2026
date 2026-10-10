"""全量下载索引中的全部文章正文（后台任务入口）。"""
from pathlib import Path
import sys

sys.path.insert(0, str(next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())))

import yaml
from crawler import PROJECT_ROOT, get_logger
from crawler.article import append_articles, fetch_article, load_fetched, read_index
from crawler.client import HttpClient

log = get_logger("download_all")

cfg = yaml.safe_load((PROJECT_ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
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

rows = read_index()
done = load_fetched()
todo = [r for r in rows if r["url"].split("/")[-2] not in done]
print(f"索引 {len(rows)} 篇，已下载 {len(done)} 篇，待下载 {len(todo)} 篇", flush=True)

ok, fail = 0, 0
buffer = []
for i, r in enumerate(todo, 1):
    rec = fetch_article(client, r["url"], r["category"], r["category_key"], r["list_date"], r["title"])
    if rec is None:
        fail += 1
    else:
        ok += 1
        buffer.append(rec)
        if i % 50 == 0:
            print(f"  进度 {i}/{len(todo)}  成功 {ok}  失败 {fail}", flush=True)
            log.info("进度 %d/%d 成功 %d 失败 %d", i, len(todo), ok, fail)
    if len(buffer) >= 100:
        append_articles(buffer)
        buffer.clear()

if buffer:
    append_articles(buffer)

print(f"下载完成：成功 {ok}，失败 {fail}", flush=True)
