#!/usr/bin/env python3
"""
每日 GitHub 精选 — 抓取 Trending、AI 分析
支持本地运行（读 config.py）和 GitHub Actions（读环境变量）
"""
import json
import os
import sys
from datetime import datetime, timedelta, date

import requests

# ─── 配置（环境变量优先，其次 config.py）──────────────────────────────────
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from config import DEEPSEEK_API_KEY, DAILY_COUNT, DATA_DIR
    except ImportError:
        print("错误：找不到 DEEPSEEK_API_KEY，请设置环境变量或 config.py")
        sys.exit(1)
else:
    DAILY_COUNT = int(os.environ.get("DAILY_COUNT", "2"))
    DATA_DIR    = os.path.join(os.path.dirname(__file__), "data")

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL   = "deepseek-chat"


# ─── 1. 抓取 GitHub Trending ─────────────────────────────────────────────

def fetch_trending(limit: int = 15) -> list[dict]:
    since = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    url = (
        f"https://api.github.com/search/repositories"
        f"?q=created:>{since}&sort=stars&order=desc&per_page={limit}"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    repos = []
    for item in resp.json().get("items", []):
        repos.append({
            "full_name":   item["full_name"],
            "url":         item["html_url"],
            "description": item.get("description") or "",
            "language":    item.get("language") or "Unknown",
            "stars":       str(item["stargazers_count"]),
            "stars_today": "",
        })
    return repos


# ─── 2. 加载近期已推送项目（避免重复）───────────────────────────────────

def load_recent_picks(days: int = 3) -> set:
    recent = set()
    today = date.today()
    for i in range(1, days + 1):
        path = os.path.join(DATA_DIR, f"{today - timedelta(days=i)}.json")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    for p in json.load(f).get("picks", []):
                        recent.add(p["full_name"])
            except Exception:
                pass
    return recent


# ─── 3. AI 筛选与讲解 ────────────────────────────────────────────────────

def ai_select_and_explain(repos: list[dict]) -> list[dict]:
    repo_list_text = "\n".join(
        f"{i+1}. [{r['full_name']}]({r['url']})\n"
        f"   语言: {r['language']} | ⭐ {r['stars']} | 今日新增: {r['stars_today']}\n"
        f"   描述: {r['description']}"
        for i, r in enumerate(repos)
    )

    prompt = f"""你是一位资深技术顾问，专门帮开发者发现有价值的开源项目。

以下是今日 GitHub Trending 前 {len(repos)} 个项目：

{repo_list_text}

请从中选出最值得关注的 {DAILY_COUNT} 个项目（优先考虑：实用性强、技术创新、社区活跃、对开发者日常工作有帮助）。

对每个选出的项目，用中文提供以下内容：
1. **项目名称与链接**
2. **一句话概括**（15字以内，说清楚它是什么）
3. **为什么值得关注**（2-3条核心亮点，具体说明技术价值或使用场景）
4. **适合哪些人**（目标用户画像）
5. **快速上手**（如何在5分钟内体验它）

输出格式为 JSON 数组，每个元素包含字段：
full_name, url, summary, highlights(数组), target_users, quick_start

只输出 JSON，不要其他文字。"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=body, timeout=60)
    resp.raise_for_status()

    raw = resp.json()["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ─── 4. 保存数据并更新索引 ───────────────────────────────────────────────

def save_daily(picks: list[dict]) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    # 保存当日数据
    data_path = os.path.join(DATA_DIR, f"{today}.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({"date": today, "picks": picks}, f, ensure_ascii=False, indent=2)

    # 更新日期索引 data/index.json
    index_path = os.path.join(DATA_DIR, "index.json")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {"dates": []}

    if today not in index["dates"]:
        index["dates"].insert(0, today)       # 最新日期排在最前
        index["dates"] = index["dates"][:90]  # 只保留最近 90 天

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return data_path


# ─── 主流程 ──────────────────────────────────────────────────────────────

def main():
    force = "--force" in sys.argv
    today = datetime.now().strftime("%Y-%m-%d")
    saved_path = os.path.join(DATA_DIR, f"{today}.json")

    if os.path.exists(saved_path) and not force:
        print(f"[{today}] 今日数据已存在，跳过（用 --force 强制刷新）。")
        return

    print("正在抓取 GitHub Trending...")
    repos = fetch_trending(limit=15)
    print(f"获取到 {len(repos)} 个项目，过滤近期重复项目...")

    recent = load_recent_picks(days=3)
    if recent:
        before = len(repos)
        repos = [r for r in repos if r["full_name"] not in recent]
        print(f"过滤掉 {before - len(repos)} 个近3天已推送项目，剩余 {len(repos)} 个候选")

    print("正在 AI 分析...")
    picks = ai_select_and_explain(repos)
    path  = save_daily(picks)
    print(f"✅ 已保存到 {path}")
    print(f"   今日精选：{', '.join(p['full_name'] for p in picks)}")


if __name__ == "__main__":
    main()
