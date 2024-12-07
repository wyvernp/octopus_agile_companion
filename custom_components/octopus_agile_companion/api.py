import aiohttp
import logging
from aiohttp.client_exceptions import ClientError

_LOGGER = logging.getLogger(__name__)

class OctopusAgileAPI:
    """Wrapper for Octopus Agile API calls using Bearer token."""

    def __init__(self, api_key, product_code, tariff_code):
        self.api_key = api_key
        self.product_code = product_code
        self.tariff_code = tariff_code

    async def fetch_rates(self, session):
        url = f"https://api.octopus.energy/v1/products/{self.product_code}/electricity-tariffs/{self.tariff_code}/standard-unit-rates/"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
                results = data.get("results", [])
                return results
        except ClientError as e:
            _LOGGER.error("Failed to fetch rates from Octopus API: %s", e)
            raise
        except Exception as e:
            _LOGGER.error("Unexpected error fetching rates: %s", e)
            raise
