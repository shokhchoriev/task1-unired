"""
Tron Nile testnet helpers.

All network calls go to nile.trongrid.io (the default api.nileex.io endpoint
uses a TLS version incompatible with LibreSSL on older Python builds).
"""
import re
from decimal import Decimal
from typing import Optional

import httpx

_NILE_NODE = "https://nile.trongrid.io"
_TRON_ADDR_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")


def _client():
    from tronpy import Tron
    from tronpy.providers import HTTPProvider
    return Tron(provider=HTTPProvider(_NILE_NODE))


def is_valid_address(address: str) -> bool:
    return bool(_TRON_ADDR_RE.match(address))


def generate_wallet() -> tuple[str, str]:
    """Return (base58-address, private-key-hex) for a fresh Tron keypair."""
    from tronpy.keys import PrivateKey
    key = PrivateKey.random()
    return key.public_key.to_base58check_address(), key.hex()


def get_balance(address: str) -> Decimal:
    """TRX balance for *address*. Returns 0 for accounts not yet on-chain."""
    from tronpy.exceptions import AddressNotFound
    try:
        return Decimal(str(_client().get_account_balance(address)))
    except AddressNotFound:
        return Decimal("0")


def send_trx(private_key_hex: str, to_address: str, amount_trx: Decimal) -> tuple[str, Optional[str]]:
    """
    Broadcast a TRX transfer on Nile testnet.
    Returns (txid, error_message). On success error_message is None.
    """
    from tronpy.keys import PrivateKey
    try:
        client = _client()
        priv_key = PrivateKey(bytes.fromhex(private_key_hex))
        from_address = priv_key.public_key.to_base58check_address()
        amount_sun = int(amount_trx * 1_000_000)

        txb = (
            client.trx.transfer(from_address, to_address, amount_sun)
            .build()
            .sign(priv_key)
        )
        txid = txb.txid
        txb.broadcast()
        return txid, None
    except Exception as exc:
        return "", str(exc)


def _hex_to_base58(hex_addr: str) -> str:
    """Convert a hex Tron address (41...) to base58check (T...)."""
    try:
        from tronpy.keys import to_base58check_address
        return to_base58check_address(hex_addr)
    except Exception:
        return hex_addr


def send_trx_from_platform(to_address: str, amount_trx: Decimal) -> tuple[str, Optional[str]]:
    """Send TRX from the platform hot wallet to *to_address*."""
    from django.conf import settings
    priv_key = getattr(settings, "TRON_PLATFORM_PRIVATE_KEY", "")
    if not priv_key:
        return "", "TRON_PLATFORM_PRIVATE_KEY sozlanmagan"
    return send_trx(priv_key, to_address, amount_trx)


def get_transactions(address: str, limit: int = 10) -> list[dict]:
    """
    Return the last *limit* transactions for *address* from Nile TronGrid.
    Each dict contains: txid, timestamp_ms, type, amount_trx, from_addr,
    to_addr, status.
    """
    url = f"{_NILE_NODE}/v1/accounts/{address}/transactions"
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, params={"limit": limit, "order_by": "block_timestamp,desc"})
            resp.raise_for_status()
            raw_txs = resp.json().get("data", [])
    except Exception:
        return []

    result = []
    for tx in raw_txs:
        contracts = tx.get("raw_data", {}).get("contract", [])
        if not contracts:
            continue
        contract = contracts[0]
        ctype = contract.get("type", "Unknown")
        value = contract.get("parameter", {}).get("value", {})

        amount_trx = Decimal(str(value.get("amount", 0))) / 1_000_000
        from_addr = _hex_to_base58(value.get("owner_address", ""))
        to_addr = _hex_to_base58(value.get("to_address", ""))
        status = tx.get("ret", [{}])[0].get("contractRet", "UNKNOWN")

        result.append({
            "txid": tx.get("txID", ""),
            "timestamp_ms": tx.get("block_timestamp", 0),
            "type": ctype,
            "amount_trx": amount_trx,
            "from_addr": from_addr,
            "to_addr": to_addr,
            "status": status,
        })
    return result
