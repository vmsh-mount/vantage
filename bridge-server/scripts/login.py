"""Unified login: runs PaytmMoney's browser-login flow and INDmoney's
TOTP+MPIN flow back-to-back, then restarts bridge-server and verifies both
brokers healthy exactly once — instead of running each broker's own script
separately, which works fine but restarts (and re-verifies) the server
twice for no benefit. Each broker's own script (paytmmoney_login.py,
indmoney_login.py) still works standalone for refreshing just one."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._bridge_control import LOG_PATH, restart_bridge_server, verify_all_healthy  # noqa: E402
from scripts.indmoney_login import perform_login as perform_indmoney_login  # noqa: E402
from scripts.paytmmoney_login import perform_login as perform_paytmmoney_login  # noqa: E402


def main() -> None:
    print("=== PaytmMoney ===")
    perform_paytmmoney_login()

    print("\n=== INDmoney ===")
    perform_indmoney_login()

    print(f"\nRestarting bridge-server once for both (logs: {LOG_PATH})...")
    restart_bridge_server()

    print("Verifying both against a real GET /api/status call...")
    results = verify_all_healthy(["paytmmoney", "indmoney"])
    for broker, healthy in results.items():
        mark = "✅" if healthy else "⚠️ "
        print(f"{mark} {broker}: {'healthy' if healthy else 'NOT healthy — check ' + str(LOG_PATH)}")


if __name__ == "__main__":
    main()
