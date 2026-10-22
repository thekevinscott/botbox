import ipaddress


def authority(host: str) -> str:
    """The host as a request URL writes it: an IPv6 literal in brackets."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    return f"[{host}]" if isinstance(address, ipaddress.IPv6Address) else host
