# -*- coding: utf-8 -*-
r"""天气查询 + 26度穿衣建议（免 API Key，Open-Meteo）。

按"26度穿衣法"给建议：气温 + 衣服保暖值之和 ≈ 26℃，并给出逐件加总算式。
可用于给孩子/宝宝生成穿衣播报，称呼可通过 --baby 或环境变量配置。

用法：
  python weather_outfit.py [城市] [--baby 宝宝称呼]
    python weather_outfit.py 成都 --baby 妹妹
    python weather_outfit.py 北京                 # 默认称呼"宝宝"
输出：一段中文，含实时天气 + 按26度穿衣法的穿衣建议（带加总算式）。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

DEFAULT_CITY = os.environ.get("WEATHER_CITY", "成都")   # 可用环境变量设默认城市
DEFAULT_BABY = os.environ.get("BABY_NAME", "宝宝")      # 可用环境变量设默认称呼
_CACHE = {}
_TTL = 600

WMO = {
    0: "晴", 1: "少云", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    80: "阵雨", 81: "强阵雨", 82: "暴雨",
    95: "雷阵雨", 96: "雷雨冰雹", 99: "强雷雨冰雹",
}


def _fetch(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "wechat-automation-tools/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _geocode(city):
    q = urllib.parse.quote(city)
    url = ("https://geocoding-api.open-meteo.com/v1/search"
           f"?name={q}&count=1&language=zh&format=json")
    try:
        data = _fetch(url)
        item = (data.get("results") or [None])[0]
        if item:
            return float(item["latitude"]), float(item["longitude"]), item.get("name") or city
    except Exception:
        pass
    return 30.5728, 104.0668, city   # 成都兜底


def get_weather(city=DEFAULT_CITY):
    key = city or DEFAULT_CITY
    now = time.time()
    if key in _CACHE and now - _CACHE[key][0] < _TTL:
        return _CACHE[key][1]
    lat, lon, name = _geocode(key)
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&timezone=Asia%2FShanghai&forecast_days=1"
    )
    data = _fetch(url)
    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    code = int(cur.get("weather_code") or 0)
    result = {
        "city": name,
        "temp": cur.get("temperature_2m"),
        "feels": cur.get("apparent_temperature"),
        "humidity": cur.get("relative_humidity_2m"),
        "desc": WMO.get(code, "天气代码%d" % code),
        "high": (daily.get("temperature_2m_max") or [None])[0],
        "low": (daily.get("temperature_2m_min") or [None])[0],
        "rain": (daily.get("precipitation_probability_max") or [None])[0],
    }
    _CACHE[key] = (now, result)
    return result


# 26度穿衣法：衣服保暖值参考
CLOTHES = [
    ("厚羽绒服", 10), ("羽绒服", 10), ("厚外套", 6), ("厚毛衣", 5),
    ("棉马甲", 3), ("薄外套", 3), ("卫衣", 3), ("薄毛衣", 3),
    ("纯棉连体衣", 2), ("秋衣秋裤", 2), ("袜子", 1), ("薄内衣", 1),
]


def outfit_advice(temp, rain=None, baby=DEFAULT_BABY):
    """按 26度穿衣法给一套可操作的建议。"""
    try:
        t = float(temp)
    except Exception:
        return "温度数据没拿到，先按大人穿法给孩子穿，再摸摸颈背调整。"
    need = 26 - t
    if need <= 0:
        base = f"今天 {t:g}℃，挺暖和，{baby}一件薄连体衣或秋衣就行，别捂。"
    else:
        picked, left = [], need
        for name, val in CLOTHES:
            if left <= 0:
                break
            if val <= left + 1:
                picked.append((name, val))
                left -= val
        if not picked:
            picked = [("厚羽绒服", 10)]
        detail = " + ".join("%s%d℃" % (n, v) for n, v in picked)
        total = sum(v for _, v in picked)
        base = (f"今天 {t:g}℃，按26度穿衣法要补约 {need:g}℃，"
                f"{baby}穿：{detail} = {total:g}℃，加上气温 {t:g}℃ 约等于 26℃。")
    tips = []
    if rain is not None:
        try:
            if float(rain) >= 50:
                tips.append("下雨概率高，记得带伞、穿防水外套")
            elif float(rain) >= 30:
                tips.append("可能飘雨，带把伞稳妥")
        except Exception:
            pass
    tips.append("摸颈背判断：温热无汗刚好，潮湿是穿多了，发凉就加衣")
    tips.append("%s好动，比大人少穿一件，别捂" % baby)
    tips.append("适用于 1-3 岁幼儿，具体请结合孩子体质调整")
    return base + " ".join(tips) + "。"


def report(city=DEFAULT_CITY, baby=DEFAULT_BABY):
    try:
        w = get_weather(city)
    except Exception as e:
        return "我这边没查到天气（%s），请大人自己看一眼天气再给孩子穿。" % type(e).__name__
    parts = [f"{w['city']}现在 {w['temp']}℃，{w['desc']}"]
    if w.get("feels") is not None:
        parts.append(f"体感 {w['feels']}℃")
    if w.get("high") is not None and w.get("low") is not None:
        parts.append(f"今天 {w['low']:g}~{w['high']:g}℃")
    head = "，".join(parts) + "。"
    return head + "\n" + outfit_advice(w.get("temp"), w.get("rain"), baby)


if __name__ == "__main__":
    args = sys.argv[1:]
    baby = DEFAULT_BABY
    if "--baby" in args:
        i = args.index("--baby")
        if i + 1 < len(args):
            baby = args[i + 1]
        args = args[:i] + args[i + 2:]
    city = args[0] if args else DEFAULT_CITY
    print(report(city, baby))
