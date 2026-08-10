US_EXCHANGES = {"NASDAQ", "NYSE"}


def region_for_exchange(exchange: str) -> str:
    return "us" if exchange in US_EXCHANGES else "india"
