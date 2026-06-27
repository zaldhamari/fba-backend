"""
Supabase service-role client for backend use.
Uses SUPABASE_SERVICE_ROLE_KEY — bypasses RLS and is for server-side only.
Never expose this key to the client app.
"""
import os
import logging

log = logging.getLogger("siftly.supabase")

SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_client = None


def get_supabase():
    """
    Return a cached Supabase client (initialised once per process).
    Raises RuntimeError if required env vars are missing.
    """
    global _client
    if _client is not None:
        return _client

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set for backend Supabase access."
        )

    from supabase import create_client
    _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    log.info("Supabase service client initialised (project: %s)", SUPABASE_URL.split(".")[0].split("//")[-1])
    return _client
