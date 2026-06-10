# Request Signing

Every mutating request (`POST`, `PUT`, `PATCH`) must include a `request-sign` header containing an HMAC-SHA256 signature of the raw request body. Requests without a valid signature are rejected with `403 Forbidden`.

---

## How it works

1. The server holds a **secret** for each user (stored in `UserProfile.secret`). Anonymous service clients use the `SIGNATURE_SECRET` environment variable.
2. The client computes `HMAC-SHA256(body_string, secret)` and sends the hex digest as the `request-sign` header.
3. The server recomputes the same digest and compares it with `hmac.compare_digest` (timing-safe).

---

## Computing the signature in JavaScript

### Using `crypto.subtle` (browser / modern environments)

```js
async function signRequest(bodyString, secret) {
  const encoder = new TextEncoder();
  const keyData = encoder.encode(secret);
  const msgData = encoder.encode(bodyString);

  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const signature = await crypto.subtle.sign("HMAC", cryptoKey, msgData);

  // Convert ArrayBuffer to hex string
  return Array.from(new Uint8Array(signature))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
```

### Using Node.js `crypto` module (backend / React Native)

```js
const crypto = require("crypto");

function signRequest(bodyString, secret) {
  return crypto
    .createHmac("sha256", secret)
    .update(bodyString)
    .digest("hex");
}
```

---

## Full fetch() example

```js
const API_URL = "https://yourapi.example.com/task2/";
const USER_SECRET = "<your-user-secret-from-server>";   // keep this safe

async function rpcCall(method, params) {
  const body = JSON.stringify({
    jsonrpc: "2.0",
    id: Date.now(),
    method,
    params,
  });

  const signature = await signRequest(body, USER_SECRET);

  const response = await fetch(API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "request-sign": signature,          // ← required header
    },
    body,
  });

  if (response.status === 403) {
    const err = await response.json();
    throw new Error(`Signature rejected: ${err.error}`);
  }

  return response.json();
}

// Usage
const result = await rpcCall("transfer.state", { ext_id: "tr-001" });
console.log(result);
```

---

## Step-by-step summary

| Step | What happens |
|------|-------------|
| 1 | Serialize the request body to a string (usually `JSON.stringify(payload)`) |
| 2 | Obtain your secret key from your account settings or the `SIGNATURE_SECRET` env var |
| 3 | Compute `HMAC-SHA256(body_string, secret)` → hex string |
| 4 | Add the hex string as the `request-sign` HTTP header |
| 5 | Send the request normally |

---

## Error responses

| Status | Body | Cause |
|--------|------|-------|
| `403` | `{"error": "Missing signature"}` | `request-sign` header absent |
| `403` | `{"error": "Invalid signature"}` | Header present but digest does not match |
| `403` | `{"error": "Signature secret not configured"}` | Server has no secret for this user/client |

---

## Getting your secret

Authenticated users: your secret is stored in `UserProfile.secret` and visible (masked) in Django Admin → Accounts → User Profiles.

Service clients: set `SIGNATURE_SECRET` in the server's `.env` file and share the value securely with the client.
