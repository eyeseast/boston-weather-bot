import json
import re
from pytz import timezone
from datetime import datetime

import httpx
import llm

PROMPT = """
Review these two images and assess the weather, looking for where any fog is, the clarity of the day, and more. Both images are views of Boston and the surrounding area, taken from the Blue Hill Observatory.

Considering the weather forecast and the images, please write a weather report for Boston capturing the current conditions; the expected weather for the day; how pleasant or unpleasant it looks; how one might best dress for the weather; and what one might do given the conditions, day, and time. Remember: you will generate this report many times a day, your recommended activities should be relatively mundane and not too cliche or stereotypical.

Do not use headers or other formatting in your response. Just write one to two single paragraphs that are elegant, don't use bullet points or exclamation marks, don't mention the images as input, and use emotive words more often than numbers and figures – but don't be flowery You write like a novelist describing the scene, producing a work suitable for someone calmly reading it on a classical radio station between songs. With a style somewhere between Jack Kerouac and J. Peterman.

Remember to keep the response under 500 words.

After the weather report, please put an HTML color code that best represents the weather forecast, time of day, and the images.
"""

# coordinates
LAT = 42.287
LON = -71.133

TIMEZONE = timezone("America/New_York")


class WeatherGov:
    def __init__(self):
        self.base_url = "https://api.weather.gov"
        self.headers = {
            "User-Agent": "(WeatherDataScript, your@email.com)",
            "Accept": "application/json",
        }

    def get_weather_data(self, latitude: float, longitude: float) -> dict:
        """
        Fetches weather data from weather.gov for a specific latitude/longitude

        Args:
            latitude (float): Latitude coordinate
            longitude (float): Longitude coordinate

        Returns:
            dict: Dictionary containing weather data and forecast
        """
        try:
            # First, get the grid endpoint for the provided coordinates
            point_url = f"{self.base_url}/points/{latitude},{longitude}"
            response = httpx.get(point_url, headers=self.headers)
            response.raise_for_status()

            point_data = response.json()

            # Extract the forecast and observation station URLs
            forecast_url = point_data["properties"]["forecast"]
            station_url = point_data["properties"]["observationStations"]

            # Get the forecast
            forecast_response = httpx.get(forecast_url, headers=self.headers)
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()

            # Get the nearest observation station
            stations_response = httpx.get(station_url, headers=self.headers)
            stations_response.raise_for_status()
            stations_data = stations_response.json()

            # Get the latest observation from the nearest station
            nearest_station_url = (
                stations_data["features"][0]["id"] + "/observations/latest"
            )
            observation_response = httpx.get(nearest_station_url, headers=self.headers)
            observation_response.raise_for_status()
            observation_data = observation_response.json()

            # Format the response
            weather_data = {
                "location": {
                    "name": point_data["properties"]["relativeLocation"]["properties"][
                        "city"
                    ],
                    "state": point_data["properties"]["relativeLocation"]["properties"][
                        "state"
                    ],
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "current_conditions": {
                    "timestamp": observation_data["properties"]["timestamp"],
                    "temperature_f": self._celsius_to_fahrenheit(
                        observation_data["properties"]["temperature"]["value"]
                    ),
                    "temperature_c": observation_data["properties"]["temperature"][
                        "value"
                    ],
                    "humidity": observation_data["properties"]["relativeHumidity"][
                        "value"
                    ],
                    "wind_speed_mph": self._ms_to_mph(
                        observation_data["properties"]["windSpeed"]["value"]
                    ),
                    "wind_direction": observation_data["properties"]["windDirection"][
                        "value"
                    ],
                    "description": observation_data["properties"]["textDescription"],
                },
                "forecast": forecast_data["properties"]["periods"][
                    :2
                ],  # Today and tonight's forecast
            }

            return weather_data

        except httpx.exceptions.RequestException as e:
            print(f"Error fetching weather data: {e}")
            return None
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            print(f"Error parsing weather data: {e}")
            return None

    def _celsius_to_fahrenheit(self, celsius):
        """Convert Celsius to Fahrenheit"""
        return None if celsius is None else (celsius * 9 / 5) + 32

    def _ms_to_mph(self, meters_per_second):
        """Convert meters per second to miles per hour"""
        return None if meters_per_second is None else meters_per_second * 2.237


if __name__ == "__main__":

    weather = WeatherGov()
    data = weather.get_weather_data(LAT, LON)

    if data:
        forecasts = "Below is the weather forecast for Boston, Massachusetts: \n"
        for period in data["forecast"]:
            forecasts = (
                forecasts + "\n - " + period["name"] + ": " + period["detailedForecast"]
            )

        # Convert the current time to Boston time
        local_time = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

        forecasts += f"\n\nCurrent local time: {local_time}"
        forecasts += PROMPT

        model = llm.get_model("gpt-4o-mini")
        response = model.prompt(
            forecasts,
            attachments=[
                llm.Attachment(url="https://hazecam.net/images/main/bluehill_left.jpg"),
                llm.Attachment(
                    url="https://hazecam.net/images/main/bluehill_right.jpg"
                ),
            ],
        )

        response = response.__str__()
        # Extract the HTML color code from the response
        color_code_match = re.search(r"#(?:[0-9a-fA-F]{3}){1,2}\b", response)
        color_code = color_code_match.group(0) if color_code_match else None

        # Trim any trailing whitespace from the response
        if color_code:
            response = response.replace(color_code, "")
        response = response.strip()

        result = {
            "forecast_data": data,
            "weather_report": response,
            "color_code": color_code,
            "timestamp": local_time,
        }

        with open("weather_report.json", "w") as f:
            json.dump(result, f, indent=4)
