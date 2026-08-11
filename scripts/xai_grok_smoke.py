#!/usr/bin/env python3
"""Layered smoke check for the xAI Grok OAuth integration, with explicit egress routing.

Each layer is independently runnable so a failure points at exactly one seam
instead of "Grok doesn't work". Run the lowest failing layer in isolation while
debugging.

    L0  local credentials    no network; is a token file present at all
    L1  usable access token  exercises the refresh path under the file lock
    L2  subscription proxy   GET cli-chat-proxy.grok.com/v1/models  <- entitlement gate
    L3  chat completion      one trivial turn through XAIGrokProvider
    L4  api.x.ai acceptance  GET api.x.ai/v1/models  <- gate for image/video gen

Layers 2 and 4 hit *different hosts* with the same bearer. That split is the
whole point: chat goes through the subscription proxy, while image and video
generation go to the developer API. Passing L2 says nothing about L4.

ROUTING
-------
Every probe states which egress route it used, because nanobot resolves proxies
from more than one source and httpx will silently fall back to environment
variables when no explicit proxy is configured:

    EXPLICIT  an explicit proxy URL; trust_env=False, env vars ignored
    ENV       no explicit proxy; httpx picks up HTTP(S)_PROXY / ALL_PROXY
    DIRECT    no proxy at all; trust_env=False

By default this script mimics production exactly: config proxy if set, else ENV.
Use --proxy / --no-proxy to pin one route and remove the ambiguity while testing.

Usage:
    .venv/bin/python scripts/xai_grok_smoke.py                     # L0..L3, production routing
    .venv/bin/python scripts/xai_grok_smoke.py --route             # print routing only, no probes
    .venv/bin/python scripts/xai_grok_smoke.py --egress            # confirm exit IP per route
    .venv/bin/python scripts/xai_grok_smoke.py --proxy http://127.0.0.1:7890 --through 4
    .venv/bin/python scripts/xai_grok_smoke.py --no-proxy --layer 2
    .venv/bin/python scripts/xai_grok_smoke.py --layer 4 --api-key sk-...

No credential material is printed.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx

CHAT_PROXY_MODELS_URL = "https://cli-chat-proxy.grok.com/v1/models"
DEVELOPER_API_MODELS_URL = "https://api.x.ai/v1/models"
EGRESS_PROBE_URL = "https://api.ipify.org?format=json"
_PROBE_TIMEOUT_S = 20.0
_PROXY_ENV_VARS = ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")


class LayerError(RuntimeError):
    """A layer failed with an operator-actionable explanation."""


@dataclass(frozen=True)
class ProxyRoute:
    """A resolved egress route, mirroring how nanobot builds its httpx clients."""

    mode: str          # EXPLICIT | ENV | DIRECT
    url: str | None    # only set for EXPLICIT
    trust_env: bool
    source: str        # where the decision came from, for the operator

    def describe(self) -> str:
        if self.mode == "EXPLICIT":
            return f"EXPLICIT via {self.url}  (trust_env=False, env proxies ignored)"
        if self.mode == "ENV":
            active = _active_env_proxies()
            if not active:
                return "ENV (trust_env=True) but no proxy env vars set -> effectively DIRECT"
            joined = ", ".join(f"{key}={value}" for key, value in active.items())
            return f"ENV via {joined}  (trust_env=True)"
        return "DIRECT  (trust_env=False, no proxy)"

    def client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"timeout": _PROBE_TIMEOUT_S, "follow_redirects": False}
        if self.mode == "EXPLICIT":
            kwargs.update(proxy=self.url, trust_env=False)
        elif self.mode == "DIRECT":
            kwargs.update(trust_env=False)
        return kwargs


def _active_env_proxies() -> dict[str, str]:
    found: dict[str, str] = {}
    for name in _PROXY_ENV_VARS:
        value = os.environ.get(name) or os.environ.get(name.lower())
        if value:
            found[name] = value
    return found


def _config_proxy() -> tuple[str | None, str]:
    from nanobot.config.loader import load_config, resolve_config_env_vars

    try:
        value = resolve_config_env_vars(load_config()).providers.xai_grok.proxy or None
    except Exception as exc:
        return None, f"unreadable ({type(exc).__name__})"
    return value, "providers.xaiGrok.proxy"


def resolve_route(forced_proxy: str | None, no_proxy: bool) -> ProxyRoute:
    """Resolve the egress route, defaulting to exactly what production would do."""
    if no_proxy:
        return ProxyRoute(mode="DIRECT", url=None, trust_env=False, source="--no-proxy")
    if forced_proxy:
        return ProxyRoute(
            mode="EXPLICIT", url=forced_proxy, trust_env=False, source="--proxy"
        )
    configured, source = _config_proxy()
    if configured:
        return ProxyRoute(mode="EXPLICIT", url=configured, trust_env=False, source=source)
    return ProxyRoute(
        mode="ENV", url=None, trust_env=True, source="no config proxy; httpx trust_env"
    )


@dataclass(frozen=True)
class CapabilityRoute:
    """Which provider, endpoint and credential a single capability resolves to."""

    capability: str
    provider_name: str
    api_base: str
    auth: str
    model: str
    enabled: bool


def _describe_auth(provider_cfg: Any, provider_name: str) -> str:
    if provider_name == "xai_grok":
        return "OAuth (auth/xai.json), falls back to apiKey"
    api_key = getattr(provider_cfg, "api_key", None) if provider_cfg else None
    if api_key:
        return f"apiKey ({len(api_key)} chars, ...{api_key[-4:]})"
    return "<no credential>"


def _lookup_provider_cfg(providers_cfg: Any, name: str) -> Any:
    return getattr(providers_cfg, name, None)


def resolve_capability_routes() -> list[CapabilityRoute]:
    """Resolve chat / image / video to concrete endpoints, exactly as the tools do."""
    from nanobot.config.loader import load_config, resolve_config_env_vars

    config = resolve_config_env_vars(load_config())
    providers_cfg = config.providers
    routes: list[CapabilityRoute] = []

    chat_provider = config.agents.defaults.provider or "<unset>"
    chat_cfg = _lookup_provider_cfg(providers_cfg, chat_provider)
    routes.append(
        CapabilityRoute(
            capability="chat",
            provider_name=chat_provider,
            api_base=getattr(chat_cfg, "api_base", None) or "<provider default>",
            auth=_describe_auth(chat_cfg, chat_provider),
            model=config.agents.defaults.model or "<unset>",
            enabled=True,
        )
    )

    from nanobot.providers.image_generation import get_image_gen_provider
    from nanobot.providers.video_generation import get_video_gen_provider

    image_cfg_section = config.tools.image_generation
    image_provider = image_cfg_section.provider
    image_cfg = _lookup_provider_cfg(providers_cfg, image_provider)
    image_cls = get_image_gen_provider(image_provider)
    routes.append(
        CapabilityRoute(
            capability="image",
            provider_name=image_provider,
            api_base=(
                getattr(image_cfg, "api_base", None)
                or (image_cls(api_key=None).api_base if image_cls else "<unknown provider>")
            ),
            auth=_describe_auth(image_cfg, image_provider),
            model=image_cfg_section.model,
            enabled=image_cfg_section.enabled,
        )
    )

    video_cfg_section = config.tools.video_generation
    video_provider = video_cfg_section.provider
    # VideoGenerationTool always reads providers.xai_grok.api_key, ignoring the
    # configured provider name (video_generation.py:74).
    video_cfg = _lookup_provider_cfg(providers_cfg, "xai_grok")
    video_cls = get_video_gen_provider(video_provider)
    routes.append(
        CapabilityRoute(
            capability="video",
            provider_name=video_provider,
            api_base=(
                getattr(video_cfg, "api_base", None)
                or (video_cls(api_key=None).api_base if video_cls else "<unknown provider>")
            ),
            auth=_describe_auth(video_cfg, "xai_grok"),
            model=video_cfg_section.model,
            enabled=video_cfg_section.enabled,
        )
    )
    return routes


def print_capability_report() -> None:
    print("=" * 78)
    print("CAPABILITY ROUTING  (which credential set each feature actually uses)")
    print("=" * 78)
    try:
        routes = resolve_capability_routes()
    except Exception as exc:
        print(f"  could not resolve: {type(exc).__name__}: {exc}")
        print("=" * 78 + "\n")
        return

    for route in routes:
        flag = "" if route.enabled else "  [DISABLED]"
        print(f"  {route.capability:<6} provider = {route.provider_name}{flag}")
        print(f"         endpoint = {route.api_base}")
        print(f"         auth     = {route.auth}")
        print(f"         model    = {route.model}")

    bases: dict[str, list[str]] = {}
    for route in routes:
        bases.setdefault(route.api_base, []).append(
            f"{route.capability}({route.provider_name})"
        )
    collisions = {
        base: users
        for base, users in bases.items()
        if len(users) > 1 and len({user.split("(")[1] for user in users}) > 1
    }
    if collisions:
        print()
        print("  ! COLLISION - one endpoint reached through different provider names:")
        for base, users in collisions.items():
            print(f"    {base}  <-  {', '.join(users)}")
        print("    Traffic from these capabilities is indistinguishable at the endpoint.")
        print("    Add a marker via providers.<name>.extraHeaders to tell them apart.")

    insecure = [route for route in routes if route.api_base.startswith("http://")]
    if insecure:
        print()
        print("  ! cleartext endpoint(s); the API key crosses the network unencrypted:")
        for route in insecure:
            print(f"    {route.capability}: {route.api_base}")
    print("=" * 78 + "\n")


def print_routing_report(route: ProxyRoute) -> None:
    configured, config_source = _config_proxy()
    env_proxies = _active_env_proxies()

    print("=" * 72)
    print("EGRESS ROUTING (HTTP proxy, not the relay endpoint)")
    print("=" * 72)
    print(f"  config {config_source}: {configured or '<unset>'}")
    if env_proxies:
        for key, value in env_proxies.items():
            print(f"  env {key}: {value}")
    else:
        print("  env proxy vars: <none set>")
    print(f"  decided by: {route.source}")
    print(f"  THIS RUN USES: {route.describe()}")
    print()
    print("  how the real code paths route:")
    print("    OAuth login/refresh  providers.xaiGrok.proxy, else env   (xai_oauth.py:705)")
    print("    chat + model catalog providers.xaiGrok.proxy, else env   (xai_grok_provider.py:409)")
    print("    image generation     providers.xaiGrok.proxy, else env   (image_generation.py:247)")
    print("    video generation     ENV ONLY - ignores the config proxy (video_generation.py:130)")
    print("=" * 72)
    print()


def _client(route: ProxyRoute) -> httpx.Client:
    return httpx.Client(**route.client_kwargs())


def _body_excerpt(response: httpx.Response, limit: int = 300) -> str:
    text = " ".join(response.text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


def probe_egress(route: ProxyRoute) -> None:
    """Show the exit IP per route so the operator can prove which path traffic took."""
    print("[egress] exit IP per route")
    candidates = [("this run", route)]
    if route.mode != "DIRECT":
        candidates.append(
            ("direct", ProxyRoute(mode="DIRECT", url=None, trust_env=False, source="comparison"))
        )
    for label, candidate in candidates:
        try:
            with _client(candidate) as client:
                response = client.get(EGRESS_PROBE_URL)
            ip = response.json().get("ip") if response.status_code == 200 else None
            print(f"  {label:<10} {candidate.mode:<9} exit IP: {ip or f'HTTP {response.status_code}'}")
        except Exception as exc:
            print(f"  {label:<10} {candidate.mode:<9} FAILED: {type(exc).__name__}: {exc}")
    print("  same IP on both rows => the proxy is not actually being used.\n")


# --------------------------------------------------------------------------
# L0 - local credentials
# --------------------------------------------------------------------------
def layer0_local_credentials() -> None:
    import time

    from nanobot.providers.xai_oauth import (
        get_xai_oauth_login_status,
        get_xai_oauth_storage_path,
    )

    path = get_xai_oauth_storage_path()
    print("  route: n/a (no network)")
    print(f"  store: {path}")
    if not path.exists():
        raise LayerError("no credential file. Run `nanobot provider login xai-grok` first.")

    token = get_xai_oauth_login_status()
    if token is None:
        raise LayerError(
            "credential file exists but could not be parsed. Delete it and log in again."
        )

    remaining_s = int((token.expires - time.time() * 1000) / 1000)
    print(f"  access present: {bool(token.access)}")
    print(f"  refresh present: {bool(token.refresh)}")
    print(f"  account label: {token.account_id or '<none>'}")
    print(f"  access expires in: {remaining_s}s")
    if not token.access:
        raise LayerError("stored record carries no access token.")
    if remaining_s <= 0 and not token.refresh:
        raise LayerError("access token expired and there is no refresh token; log in again.")
    print("  note: this only proves a token exists, NOT that it has a subscription (see L2).")


# --------------------------------------------------------------------------
# L1 - usable access token
# --------------------------------------------------------------------------
def layer1_usable_token(route: ProxyRoute) -> Any:
    from nanobot.providers.xai_grok_provider import _decode_access_token_claims
    from nanobot.providers.xai_oauth import XAIOAuthError, get_xai_oauth_token

    print(f"  route: {route.describe()}")
    try:
        token = get_xai_oauth_token(proxy=route.url)
    except XAIOAuthError as exc:
        raise LayerError(str(exc)) from exc

    claims = _decode_access_token_claims(token.access)
    print(f"  token acquired, length: {len(token.access)}")
    print(f"  claim sub: {'<present>' if claims.get('sub') else '<absent>'}")
    print(f"  claim principal_type: {claims.get('principal_type') or '<absent>'}")
    print(f"  claim email present: {'@' in str(claims.get('email') or '')}")
    if claims.get("exp"):
        print(f"  claim exp: {claims['exp']}")
    return token


# --------------------------------------------------------------------------
# L2 - subscription proxy (the entitlement gate)
# --------------------------------------------------------------------------
def layer2_subscription_proxy(token: Any, route: ProxyRoute) -> None:
    from nanobot.providers.xai_grok_provider import (
        _build_model_headers,
        _parse_xai_model_capabilities,
    )

    headers = _build_model_headers(token)
    print(f"  route: {route.describe()}")
    print(f"  GET {CHAT_PROXY_MODELS_URL}")
    with _client(route) as client:
        response = client.get(CHAT_PROXY_MODELS_URL, headers=headers)

    print(f"  status: {response.status_code}")
    if response.status_code == 403:
        raise LayerError(
            "403 - this account has no eligible X Premium / Grok subscription. "
            "The token is valid; the ACCOUNT is not entitled. Log in with the account "
            "that actually holds the subscription."
        )
    if response.status_code == 401:
        raise LayerError("401 - xAI rejected the token. Log in again.")
    if response.status_code == 426:
        raise LayerError(
            "426 - xAI wants a newer Grok client version. Bump XAI_CLIENT_VERSION "
            "in nanobot/providers/xai_oauth.py."
        )
    if response.status_code != 200:
        raise LayerError(f"HTTP {response.status_code}: {_body_excerpt(response)}")

    capabilities = _parse_xai_model_capabilities(response.json())
    print(f"  models advertised: {len(capabilities)}")
    for model, supports_search in sorted(capabilities.items()):
        print(f"    {model}: supportsBackendSearch={supports_search}")
    if not capabilities:
        print("  ! catalog parsed to zero models; hosted x_search will stay disabled.")
    print("  ENTITLEMENT CONFIRMED: this account can reach the subscription endpoint.")


# --------------------------------------------------------------------------
# L3 - chat completion
# --------------------------------------------------------------------------
def layer3_chat(model: str, route: ProxyRoute) -> None:
    from nanobot.providers.xai_grok_provider import XAIGrokProvider

    provider = XAIGrokProvider(default_model=model, proxy=route.url)
    print(f"  route: {route.describe()}")
    print(f"  model: {model}")

    async def _run() -> Any:
        return await provider.chat(
            messages=[{"role": "user", "content": "Reply with exactly: ok"}],
            tools=None,
            max_tokens=64,
            temperature=0.0,
        )

    response = asyncio.run(_run())
    if response.finish_reason == "error":
        raise LayerError(
            f"{response.content} "
            f"(status={response.error_status_code} kind={response.error_kind} "
            f"retryable={response.error_should_retry})"
        )
    print(f"  finish_reason: {response.finish_reason}")
    print(f"  usage: {response.usage}")
    print(f"  content: {(response.content or '').strip()[:120]!r}")
    if not (response.content or "").strip():
        raise LayerError("empty content; SSE parsing may have regressed.")


# --------------------------------------------------------------------------
# L4 - api.x.ai acceptance (gate for image / video generation)
# --------------------------------------------------------------------------
def layer4_developer_api(token: Any, route: ProxyRoute, api_key: str | None) -> None:
    print(f"  route: {route.describe()}")
    print("  reminder: video generation ignores the config proxy and always uses ENV.")
    print(f"  GET {DEVELOPER_API_MODELS_URL}")
    print("  probing with the OAuth bearer (same shape image/video gen uses)")
    headers = {"Authorization": f"Bearer {token.access}", "Content-Type": "application/json"}
    with _client(route) as client:
        response = client.get(DEVELOPER_API_MODELS_URL, headers=headers)
    print(f"  oauth bearer status: {response.status_code}")

    oauth_ok = response.status_code == 200
    if oauth_ok:
        print("  OAuth token IS accepted by api.x.ai -> image/video gen can run key-free.")
    else:
        print(f"  body: {_body_excerpt(response)}")
        print("  OAuth token is NOT accepted by api.x.ai.")
        print("  -> XAIGrokImageGenerationClient/_get_bearer will silently fall back to")
        print("     self.api_key, so image & video generation REQUIRE an xAI API key.")

    if api_key:
        print("  probing with the supplied API key")
        with _client(route) as client:
            key_response = client.get(
                DEVELOPER_API_MODELS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        print(f"  api key status: {key_response.status_code}")
        if key_response.status_code != 200:
            print(f"  body: {_body_excerpt(key_response)}")
            raise LayerError("the supplied API key was rejected by api.x.ai.")
        print("  API key path works; configure it in Grok image/video settings.")
        return

    if not oauth_ok:
        raise LayerError(
            "api.x.ai rejected the OAuth token and no --api-key was supplied. "
            "Image and video generation cannot work on the subscription login alone."
        )


LAYER_NAMES = {
    0: "local credentials",
    1: "usable access token",
    2: "subscription proxy (entitlement gate)",
    3: "chat completion",
    4: "api.x.ai acceptance (image/video gate)",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", help="comma-separated layers to run, e.g. 2 or 0,1,2")
    parser.add_argument("--through", type=int, default=3, help="run L0 through this layer")
    parser.add_argument("--model", default="xai-grok/grok-4.5", help="model for L3")
    parser.add_argument("--api-key", default=None, help="optional xAI API key to probe in L4")
    parser.add_argument("--proxy", default=None, help="force this proxy URL for every probe")
    parser.add_argument(
        "--no-proxy", action="store_true", help="force direct egress, ignoring config and env"
    )
    parser.add_argument(
        "--route", action="store_true", help="print the routing report and exit without probing"
    )
    parser.add_argument(
        "--egress", action="store_true", help="probe the exit IP to prove which route is live"
    )
    args = parser.parse_args()

    if args.proxy and args.no_proxy:
        print("--proxy and --no-proxy are mutually exclusive", file=sys.stderr)
        return 2

    route = resolve_route(args.proxy, args.no_proxy)
    print_capability_report()
    print_routing_report(route)

    if args.route:
        return 0
    if args.egress:
        probe_egress(route)

    if args.layer:
        try:
            layers = sorted({int(part) for part in args.layer.split(",") if part.strip()})
        except ValueError:
            print("--layer expects comma-separated integers", file=sys.stderr)
            return 2
    else:
        layers = list(range(0, args.through + 1))

    unknown = [layer for layer in layers if layer not in LAYER_NAMES]
    if unknown:
        print(f"unknown layer(s): {unknown}", file=sys.stderr)
        return 2

    token: Any = None
    for layer in layers:
        print(f"[L{layer}] {LAYER_NAMES[layer]}")
        try:
            if layer == 0:
                layer0_local_credentials()
            elif layer == 1:
                token = layer1_usable_token(route)
            elif layer == 2:
                token = token or layer1_usable_token(route)
                layer2_subscription_proxy(token, route)
            elif layer == 3:
                layer3_chat(args.model, route)
            elif layer == 4:
                token = token or layer1_usable_token(route)
                layer4_developer_api(token, route, args.api_key)
        except LayerError as exc:
            print(f"  FAIL: {exc}\n")
            print(f"stopped at L{layer} ({LAYER_NAMES[layer]}) on route {route.mode}")
            return 1
        except Exception as exc:  # noqa: BLE001 - smoke script reports, never swallows
            print(f"  ERROR: {type(exc).__name__}: {exc}\n")
            print(f"stopped at L{layer} ({LAYER_NAMES[layer]}) on route {route.mode}")
            return 1
        print("  PASS\n")

    print(f"all layers passed on route {route.mode}: {['L%d' % layer for layer in layers]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
