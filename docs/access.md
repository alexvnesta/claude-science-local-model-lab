# Claude Science Access Notes

Verified against official Anthropic pages on 2026-07-01.

Claude Science is currently a beta desktop app. This lab assumes you already
have legitimate access to Claude Science, can download the official app, and
can sign in with a `claude.ai` account that has the required entitlement.

Official availability:

- Pro and Max: Claude Science app access is on, with no admin action needed.
- Team and Enterprise: Claude Science is off by default and must be enabled in
  Organization settings by an Owner or Primary Owner.
- Free: Claude Science is not available.
- Once enabled and entitled, members can download Claude Science and sign in
  with their `claude.ai` account.

Practical implications for this repo:

- The proxy does not remove the need for official Claude Science beta access.
- The first launch and local app URL flow still depend on Claude Science's own
  account/session model.
- This repo does not redistribute the app or any Anthropic proprietary files.
- If you are on a Team or Enterprise organization and the app appears
  unavailable, check organization capability enablement and role entitlement
  before debugging the proxy.

Official references:

- [Enable Claude Science](https://claude.com/docs/claude-science/enable-claude-science)
- [Claude Science product page](https://claude.com/product/claude-science)
- [Claude Science overview](https://claude.com/docs/claude-science/overview)
