"""Google Weather API 어댑터 — 도시명을 위도·경도로 바꿔 현재 날씨를 조회한다."""

import os

import requests

URL = "https://weather.googleapis.com/v1/currentConditions:lookup"

CITY_COORDS = {
    "Seoul": (37.5665, 126.9780),
    "New York": (40.7128, -74.0060),
    "Tokyo": (35.6762, 139.6503),
    "Berlin": (52.5200, 13.4050),
}


def fetch(city: str) -> dict:
    if city not in CITY_COORDS:
        raise ValueError(f"지원하지 않는 도시: {city} (가능: {', '.join(CITY_COORDS)})")
    lat, lon = CITY_COORDS[city]
    try:
        resp = requests.get(
            URL,
            params={
                "key": os.environ["GOOGLE_WEATHER_API_KEY"],
                "location.latitude": lat,
                "location.longitude": lon,
                "languageCode": "ko",
            },
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        # 키가 담긴 URL이 LLM에게 새지 않도록 예외 종류만 남긴다
        raise RuntimeError(f"날씨 API 호출 실패 ({type(e).__name__})") from None
    raw = resp.json()
    return {
        "source": "google_weather",
        "data": {
            "city": city,
            "condition": raw["weatherCondition"]["description"]["text"],
            "temperature_c": raw["temperature"]["degrees"],
            "feels_like_c": raw["feelsLikeTemperature"]["degrees"],
            "humidity_pct": raw["relativeHumidity"],
        },
    }
