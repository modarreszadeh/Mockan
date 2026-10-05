# Mockan OIDC Authentication — Agent Context

## Decision

Mockan Panel will use the organization's existing **Keycloak** instance as its OIDC Identity Provider.

The users of the Mockan Panel are internal developers.

All internal developers already have accounts in the organization's existing AD/SSO infrastructure, which is exposed through Keycloak as the OIDC provider.

Therefore:

```text
Developer
    |
    v
Mockan Panel
    |
    v
Keycloak
    |
    v
Organization AD
```

There is no need to evaluate Azure AD, Entra ID, or another Identity Provider for this project.

---

# OQ-04 Status

OQ-04:

> Which OIDC provider should Mockan use?

Decision:

```text
Provider = Keycloak
```

Status:

```text
DECIDED
```

This is no longer an architecture decision.

The remaining work is only **Keycloak client registration and real integration validation**.

---

# What the implementation should support

Mockan Panel uses the standard OIDC Authorization Code Flow with PKCE (S256).

Expected login flow:

```text
Developer
    |
    | Open Mockan Panel
    v
Mockan
    |
    | Authorization Code + PKCE
    v
Keycloak
    |
    | Developer authenticates using existing organization account
    v
Keycloak
    |
    | Authorization Code
    v
Mockan Callback
    |
    | Token Exchange
    v
Mockan
    |
    | Create authenticated session
    v
Mockan Panel
```

The developer should not need a separate Mockan username/password.

Mockan authentication should rely on the organization's existing Keycloak/AD identity.

---

# What DevOps needs to provide

The only remaining infrastructure dependency is a Keycloak client registration for Mockan.

Ask DevOps for:

```text
OIDC Issuer URL
Keycloak Client ID
Keycloak Client Secret
Registered Redirect URI
```

The expected configuration will look conceptually like:

```text
MOCKAN_OIDC_ISSUER=https://<keycloak-host>/...
MOCKAN_OIDC_CLIENT_ID=<client-id>
MOCKAN_OIDC_CLIENT_SECRET=<client-secret>
MOCKAN_SESSION_SECRET=<32+ character secret>
```

Do not invent or hard-code these values.

The actual values must come from the organization's Keycloak/DevOps configuration.

---

# Keycloak Client Requirements

The Keycloak client should be configured as a confidential OIDC client.

Required capabilities:

```text
Protocol:
    OpenID Connect

Client authentication:
    Enabled

Client type:
    Confidential

Authorization Code Flow:
    Enabled

PKCE:
    S256

Scopes:
    openid
    profile
    email
```

The exact Keycloak terminology/version may differ, so the Agent should inspect the actual Keycloak configuration rather than assuming UI field names.

---

# Redirect URI

The exact Mockan callback endpoint must be registered in Keycloak.

Expected pattern:

```text
https://<mockan-admin-host>/api/v1/auth/callback
```

The Agent must verify the actual callback path in the Mockan source/documentation before asking DevOps to register it.

Do not guess the callback path.

---

# User Identity

Mockan currently uses the OIDC `sub` claim as the internal SSO identity:

```text
Keycloak
    |
    | sub
    v
Mockan User
    |
    +-- sso_subject
```

The first developer/admin's `sub` should not be manually guessed.

Instead:

1. Register the Keycloak client.
2. Perform a real login.
3. Inspect the authenticated user's `sub`.
4. Use that value for the Mockan admin configuration.

The display name resolution currently follows:

```text
name
  -> preferred_username
      -> email
```

---

# Admin Bootstrap

Mockan uses:

```text
MOCKAN_ADMIN_SSO_SUBJECTS
```

to identify users who should have administrator privileges.

The initial admin subject should be obtained from a real Keycloak login.

Do not assume that the user's email or username is the value of `sub`.

For Keycloak, the `sub` is normally the user's Keycloak subject/UUID.

---

# Important Scope Boundary

This OQ is primarily about:

> Authentication of developers into the Mockan Panel.

It is NOT about creating a separate authentication system for Mockan developers.

The desired model is:

```text
Existing Organization Identity
            |
            v
         Keycloak
            |
            v
       Mockan Panel
```

Mockan should trust the organization's existing SSO identity rather than maintaining passwords for developers.

---

# Admin API Bearer Tokens

The existing Mockan implementation also validates JWT Bearer Tokens for API clients.

That is a related but separate concern from Panel Login.

Do not block the Panel OIDC integration on unrelated API token semantics unless the implementation actually requires it.

For the initial OQ-04 validation, prioritize:

1. Keycloak Discovery
2. Authorization Code Flow
3. PKCE
4. Callback
5. Token exchange
6. User identity extraction
7. Mockan session creation
8. Panel access

After that, validate Admin API Bearer Token behavior separately if required.

---

# Logout

Current Mockan logout only terminates the Mockan session.

It does not necessarily terminate the user's Keycloak SSO session.

Therefore:

```text
Mockan Logout
    !=
Keycloak Logout
```

This is acceptable unless the product explicitly requires RP-Initiated Logout.

Do not make Keycloak SSO logout a blocker for the initial OQ-04 implementation unless it is a stated product requirement.

---

# Agent Tasks

The Agent should now proceed with the following tasks.

## 1. Inspect existing implementation

Verify:

```text
server/src/mockan/admin/oidc.py
```

and related configuration/documentation.

Confirm:

* Authorization Code Flow
* PKCE S256
* Discovery
* ID Token validation
* `sub` handling
* session creation
* callback path
* logout behavior

Do not rewrite the OIDC implementation without identifying an actual incompatibility.

---

## 2. Verify Keycloak compatibility

Check the existing implementation against standard Keycloak OIDC behavior.

Verify:

```text
/.well-known/openid-configuration
authorization_endpoint
token_endpoint
jwks_uri
issuer
```

The Agent should not assume a specific Keycloak URL structure.

Use the actual issuer supplied by DevOps.

---

## 3. Prepare configuration

Document the required environment variables:

```text
MOCKAN_OIDC_ISSUER
MOCKAN_OIDC_CLIENT_ID
MOCKAN_OIDC_CLIENT_SECRET
MOCKAN_SESSION_SECRET
MOCKAN_ADMIN_SSO_SUBJECTS
```

Never commit real credentials or secrets to Git.

---

## 4. Request DevOps configuration

The Agent should tell the team that the remaining external dependency is:

```text
"Please provide/register a confidential OIDC client in the organization's Keycloak for Mockan."
```

Required information:

```text
Issuer URL
Client ID
Client Secret
Allowed Redirect URI
```

---

## 5. Perform one real login

After DevOps provides the configuration:

```text
Developer
    |
    v
Mockan
    |
    v
Keycloak
    |
    v
AD authentication
    |
    v
Mockan callback
    |
    v
Authenticated Panel session
```

A successful real login closes the main OQ-04 integration risk.

---

# Acceptance Criteria

OQ-04 is considered resolved when all of the following are true:

```text
[ ] Keycloak is confirmed as the OIDC Provider
[ ] Confidential Mockan client is registered in Keycloak
[ ] Correct issuer is configured
[ ] Client ID is configured
[ ] Client secret is configured securely
[ ] Correct redirect URI is registered
[ ] Mockan can reach Keycloak discovery endpoint
[ ] Authorization Code Flow works
[ ] PKCE S256 works
[ ] Token exchange succeeds
[ ] ID Token validation succeeds
[ ] Developer identity is resolved from `sub`
[ ] Mockan session is created
[ ] Developer can access the Panel
[ ] Initial admin `sub` is configured
```

---

# Final Architectural Decision

Use the organization's existing Keycloak as the sole OIDC Identity Provider for Mockan Panel authentication.

Do not introduce:

* Azure AD integration
* A separate Mockan username/password system
* A second Identity Provider
* Custom authentication logic

unless a concrete requirement appears later.

The immediate next step is **not code development**.

The immediate next step is:

```text
DevOps
   |
   +-- Keycloak Issuer
   +-- Client ID
   +-- Client Secret
   +-- Redirect URI registration
             |
             v
       Real Login Test
             |
             v
        OQ-04 CLOSED
```
