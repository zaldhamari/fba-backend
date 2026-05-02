import asyncio
from pytrends.request import TrendReq


async def get_trends(keyword: str) -> dict:
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fetch_trends, keyword)
        return result
    except Exception as e:
        return {"error": str(e), "interest_score": None, "trend_direction": "Unknown", "related_queries": []}


def _fetch_trends(keyword: str) -> dict:
    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload([keyword], cat=0, timeframe="today 12-m", geo="US")

    interest_df = pytrends.interest_over_time()
    related = pytrends.related_queries()

    if interest_df.empty:
        return {
            "interest_score": None,
            "trend_direction": "No data",
            "related_queries": [],
            "monthly_interest": [],
        }

    values = interest_df[keyword].tolist()
    avg = sum(values) / len(values) if values else 0
    recent_avg = sum(values[-4:]) / 4 if len(values) >= 4 else avg
    old_avg = sum(values[:4]) / 4 if len(values) >= 4 else avg

    if recent_avg > old_avg * 1.1:
        direction = "Rising"
    elif recent_avg < old_avg * 0.9:
        direction = "Declining"
    else:
        direction = "Stable"

    top_queries = []
    if keyword in related and related[keyword].get("top") is not None:
        top_df = related[keyword]["top"]
        top_queries = top_df["query"].head(5).tolist() if not top_df.empty else []

    return {
        "interest_score": round(avg, 1),
        "trend_direction": direction,
        "related_queries": top_queries,
        "monthly_interest": [{"month": str(d.date()), "value": int(v)} for d, v in zip(interest_df.index[-12:], values[-12:])],
    }
