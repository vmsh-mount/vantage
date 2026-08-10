"""Contract smoke-test for bridge-server's INDmoney MCP client (task 24).
Uses tool shapes verified live in a real session, not guessed — if
INDmoney changes a tool's name or response shape, this fails loudly and
specifically instead of task 25's fact tools silently computing wrong
numbers from a shape mismatch.

Run after scripts/indmoney_mcp_login.py has completed once — this script
does not do interactive consent itself; it uses whatever tokens are
already persisted, which is the point (confirms token *reuse*, not just
initial consent, actually works)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations.indmoney_mcp import call_tool  # noqa: E402


class SmokeTestFailure(AssertionError):
    pass


def _unwrap(e: BaseException) -> BaseException:
    """anyio wraps task-group failures in ExceptionGroup — unwrap to the
    real underlying cause so failures are actually readable instead of
    'unhandled errors in a TaskGroup (1 sub-exception)'."""
    while isinstance(e, BaseExceptionGroup) and len(e.exceptions) == 1:
        e = e.exceptions[0]
    return e


async def check_lookup_ind_keys() -> None:
    result = await call_tool("lookup_ind_keys", {"names": ["RELIANCE"], "filter_type": "IN_STOCKS"})
    if not isinstance(result, list) or not result:
        raise SmokeTestFailure(f"lookup_ind_keys: expected a non-empty list, got {result!r}")
    first = result[0]
    for field in ("ind_key", "name"):
        if field not in first:
            raise SmokeTestFailure(f"lookup_ind_keys: item missing {field!r} — {first!r}")
    print(f"✅ lookup_ind_keys — {first['name']} → {first['ind_key']}")


async def check_networth_snapshot() -> None:
    result = await call_tool("networth_snapshot", {})
    if "total_networth" not in result or not isinstance(result["total_networth"], (int, float)):
        raise SmokeTestFailure(f"networth_snapshot: missing/non-numeric total_networth — {result!r}")
    if "investments" not in result or not isinstance(result["investments"], list):
        raise SmokeTestFailure(f"networth_snapshot: missing/non-list investments — {result!r}")
    print(f"✅ networth_snapshot — total_networth={result['total_networth']}, {len(result['investments'])} investment rows")


async def check_ohlc() -> None:
    # RELIANCE's ind_key, resolved via lookup_ind_keys earlier this session —
    # stable enough for a smoke test; not the point being verified here.
    result = await call_tool("get_indian_stocks_ohlc", {"ind_key": "INDS01052", "interval": "1day", "lookback": "7d"})
    if "candles" not in result or not isinstance(result["candles"], list) or not result["candles"]:
        raise SmokeTestFailure(f"get_indian_stocks_ohlc: missing/empty candles — {result!r}")
    candle = result["candles"][0]
    for field in ("close", "datetime_ist"):
        if field not in candle:
            raise SmokeTestFailure(f"get_indian_stocks_ohlc: candle missing {field!r} — {candle!r}")
    print(f"✅ get_indian_stocks_ohlc — {len(result['candles'])} candles, first close={candle['close']}")


async def main() -> None:
    checks = [check_lookup_ind_keys, check_networth_snapshot, check_ohlc]
    failures = []
    for check in checks:
        try:
            await check()
        except SmokeTestFailure as e:
            print(f"❌ {check.__name__}: {e}")
            failures.append(check.__name__)
        except Exception as e:
            cause = _unwrap(e)
            print(f"❌ {check.__name__}: {type(cause).__name__}: {cause}")
            failures.append(check.__name__)

    if failures:
        print(f"\n{len(failures)}/{len(checks)} checks failed: {', '.join(failures)}")
        sys.exit(1)
    print(f"\nAll {len(checks)} checks passed — no reauthorization was needed.")


if __name__ == "__main__":
    asyncio.run(main())
