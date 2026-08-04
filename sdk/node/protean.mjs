/**
 * Protean Metered Client SDK (Node.js 18+)
 *
 * Minimal dependency-light client for the metered token-licensing API.
 * Uses the built-in global fetch and node:crypto.
 *
 * When the pilot grant is exhausted every paid call returns HTTP 402 with a
 * license offer in the body - the SDK surfaces it as `EntitlementExhausted`.
 */
import { createHmac, timingSafeEqual } from "node:crypto";

const BASE_URL = "https://api.protean.sh";

export class ProteanError extends Error {}
export class EntitlementExhausted extends ProteanError {
  constructor(message, offer, headers = {}) {
    super(message);
    this.offer = offer;
    this.headers = headers;
  }
}

export class ProteanClient {
  constructor(apiKey, baseUrl = BASE_URL, timeoutMs = 120000) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.timeoutMs = timeoutMs;
  }

  /**
   * Full transaction analysis (1 token). Includes ZK proof + OFAC/FATF screening.
   */
  async analyze({
    type = "payment", valueEth = 0, gasPriceGwei = 0, slippageBps = 0,
    poolLiquidityEth = 0, isProtectedUser = 1, mode = "defense", txHash = "",
    parties = [],
  } = {}) {
    return this.#request("POST", "/v1/transactions/analyze", {
      type, value_eth: valueEth, gas_price_gwei: gasPriceGwei,
      slippage_bps: slippageBps, pool_liquidity_eth: poolLiquidityEth,
      is_protected_user: isProtectedUser, mode, tx_hash: txHash, parties,
    });
  }

  /** Screen a party against sanctions/watchlists (1 token). */
  complianceCheck({ name = null, address = null, country = null } = {}) {
    return this.#request("POST", "/v1/compliance/check", { name, address, country });
  }

  /** Token balance / expiry / license offer (0 tokens). */
  entitlement() {
    return this.#request("POST", "/v1/entitlement", {});
  }

  /** Subscribe to signed decision delivery. Returns the HMAC secret. */
  registerWebhook(url, events = ["tx.analyzed", "compliance.checked"]) {
    return this.#request("POST", "/v1/webhooks/register", { url, events });
  }

  listWebhooks() {
    return this.#request("GET", "/v1/webhooks", null);
  }

  async #request(method, path, body) {
    const headers = { "X-API-Key": this.apiKey, Accept: "application/json" };
    let payload;
    if (body !== null) {
      payload = JSON.stringify(body);
      headers["Content-Type"] = "application/json";
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const resp = await fetch(`${this.baseUrl}${path}`, {
        method, headers, body: payload, signal: controller.signal,
      });
      const raw = await resp.text();
      const json = raw ? JSON.parse(raw) : {};
      if (!resp.ok) {
        if (resp.status === 402) {
          const detail = json?.detail;
          const offer = typeof detail === "object" ? detail?.offer : undefined;
          throw new EntitlementExhausted(String(detail ?? json), offer, resp.headers);
        }
        throw new ProteanError(`${method} ${path} -> ${resp.status}: ${JSON.stringify(json)}`);
      }
      return json;
    } finally {
      clearTimeout(timer);
    }
  }
}

/**
 * Verify an X-Protean-Signature header against the raw request body.
 * Signature is `sha256=<hex>` of HMAC-SHA256 over the exact JSON body using the
 * webhook secret. Optional replay protection via X-Protean-Timestamp.
 */
export function verifyWebhookSignature(secret, body, signature, timestamp = null, maxAgeSeconds = 300) {
  if (typeof signature !== "string" || !signature.startsWith("sha256=")) return false;
  if (timestamp !== null && timestamp !== undefined) {
    const age = Math.abs(Math.floor(Date.now() / 1000) - Number(timestamp));
    if (!Number.isFinite(age) || age > maxAgeSeconds) return false;
  }
  const expected = createHmac("sha256", secret).update(body).digest("hex");
  const a = Buffer.from(`sha256=${expected}`, "utf8");
  const b = Buffer.from(signature, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

// Express-style helper for verifying an incoming webhook request.
export function verifyWebhookRequest(secret, req, maxAgeSeconds = 300) {
  const raw = typeof req.body === "string" ? req.body : JSON.stringify(req.body);
  return verifyWebhookSignature(
    secret, Buffer.from(raw, "utf8"),
    req.headers["x-protean-signature"] ?? "",
    req.headers["x-protean-timestamp"] ?? null,
    maxAgeSeconds,
  );
}
