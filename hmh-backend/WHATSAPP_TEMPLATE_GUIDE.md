# WhatsApp Template Guide — HMH Construction OS

## Overview

WhatsApp Cloud API enforces a **24-hour conversation window** rule. A business can send free-form
messages only if the recipient sent the business a message within the last 24 hours. Outside that
window, only **pre-approved template messages** can be used.

HMH uses templates for all proactive alert notifications to ensure reliable delivery regardless of
the conversation window state.

---

## Template Categories

Meta classifies templates into three categories that determine when they can be sent and what they
cost:

| Category | Use case | Cost |
|---|---|---|
| **UTILITY** | Transactional updates the user opted into (delivery status, payment confirmation) | Low |
| **AUTHENTICATION** | OTP / login codes | Low |
| **MARKETING** | Promotional, upsell, or engagement messages | High |

**Always create HMH alert templates as UTILITY**, not MARKETING. Marketing templates cost ~3× more
and are subject to stricter delivery limits. Meta will try to auto-reclassify — always manually
verify the category in Business Manager after approval.

---

## Required Templates

### 1. Alert Template (`hmh_alert_notification`)

Used for: LOW_STOCK, DELIVERY_MISMATCH, INVOICE_MISMATCH, OVERDUE_PAYMENT, and all other
operational alerts.

**Recommended body (submitted to Meta):**
```
{{1}} — HMH Construction alert for your attention.
Reply OK to acknowledge.
```

- `{{1}}` will be filled with the alert title at send time.
- Language code: `en_US`

### 2. Daily Summary Template (`hmh_daily_summary`)

Used for: DAILY_SUMMARY and WEEKLY_SUMMARY alert types.

**Recommended body (submitted to Meta):**
```
HMH Daily Summary — {{1}}. Open alerts: {{2}}. Pending invoices: {{3}}.
```

- `{{1}}` = date, `{{2}}` = open alert count, `{{3}}` = pending invoice count.
- Language code: `en_US`

---

## Environment Variables

```env
# Template names — must match Meta Business Manager exactly (lowercase, underscores)
WHATSAPP_ALERT_TEMPLATE_NAME=hmh_alert_notification
WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME=hmh_daily_summary
WHATSAPP_ALERT_TEMPLATE_LANGUAGE=en_US

# Cost optimization
WHATSAPP_COST_OPTIMIZATION_ENABLED=true
WHATSAPP_SUMMARY_INTERVAL_MINUTES=60      # delay MEDIUM/LOW alerts this many minutes
WHATSAPP_QUIET_HOURS_ENABLED=false        # set true to suppress non-critical alerts at night
WHATSAPP_QUIET_HOURS_START=20:00          # UTC; wrap-midnight supported
WHATSAPP_QUIET_HOURS_END=07:00
WHATSAPP_MAX_ALERTS_PER_HOUR_PER_RECIPIENT=10

# For running scripts/test_whatsapp_template.py
WHATSAPP_TEST_PHONE_NUMBER=27821234567
```

---

## Cost-Saving Rules

The system applies the following optimizations automatically when
`WHATSAPP_COST_OPTIMIZATION_ENABLED=true`:

### 1. Severity-Based Sending

| Severity | Behavior |
|---|---|
| **CRITICAL** | Sent immediately, no throttle, no quiet-hours delay |
| **HIGH** | Sent immediately, no throttle, no quiet-hours delay |
| **MEDIUM** | Delayed by `WHATSAPP_SUMMARY_INTERVAL_MINUTES` (default 60 min) |
| **LOW** | Delayed by `WHATSAPP_SUMMARY_INTERVAL_MINUTES` (default 60 min) |

Batching medium/low alerts reduces per-message charges by avoiding one-at-a-time sends throughout
the day.

### 2. Quiet Hours

When `WHATSAPP_QUIET_HOURS_ENABLED=true`, **non-critical** alert delivery is postponed until quiet
hours end. Critical/High alerts are never suppressed.

Configure via `WHATSAPP_QUIET_HOURS_START` and `WHATSAPP_QUIET_HOURS_END` in 24-hour UTC format.
Wrap-midnight ranges (e.g., `20:00`–`07:00`) are supported.

### 3. Hourly Cap

`WHATSAPP_MAX_ALERTS_PER_HOUR_PER_RECIPIENT` limits total sends per recipient per hour. Once the
cap is hit, additional queue entries are skipped until the next hour window opens. This prevents
alert storms from generating a large Meta bill.

### 4. Deduplication

`enqueue_for_alert()` skips creating a new queue entry if a PENDING/SENT/ACKNOWLEDGED entry already
exists for the same alert + recipient. This prevents duplicate sends when an alert is re-triggered
within the same event loop.

---

## Three-Tier Send Strategy

Every queue entry goes through this decision tree at send time:

```
1. Template configured → send_template_message()  (works any time)
        ↓ no template
2. Recipient in 24h window → send_text()           (free-form, in-window only)
        ↓ no window
3. FAILED — log error, do not crash               (check template config)
```

---

## Submitting a New Template

1. Go to **Meta Business Suite → WhatsApp Manager → Message Templates**
2. Click **Create Template**
3. Set:
   - Category: **Utility**
   - Language: **English (US)**
   - Name: lowercase with underscores only (e.g. `hmh_alert_notification`)
   - Body: plain text with `{{1}}` placeholders as needed
4. Submit for review — approval usually takes < 24 hours
5. Update `WHATSAPP_ALERT_TEMPLATE_NAME` or `WHATSAPP_DAILY_SUMMARY_TEMPLATE_NAME` in `.env`
6. Run `python scripts/test_whatsapp_template.py` to verify

---

## Troubleshooting

### "Template name does not exist"

- The name in `.env` does not match the approved name in Meta Business Manager exactly.
- Names are **case-sensitive, lowercase, underscores only**.
- Check for trailing spaces in the `.env` value.
- Verify the template status is **APPROVED** (not Pending/Rejected).

### "Template is paused"

- Meta automatically pauses templates with high user block rates.
- Review the template body for anything that might prompt users to block.
- Resume the template in Business Manager.

### Free-form message outside 24h window

- The recipient has not sent the business a WhatsApp message in the last 24 hours.
- Configure `WHATSAPP_ALERT_TEMPLATE_NAME` to use templates instead.
- Run `python scripts/test_whatsapp_template.py` to verify the template works.

### Access token expired (401)

- Meta user access tokens expire after 60 days. System access tokens for business APIs don't.
- Rotate `WHATSAPP_ACCESS_TOKEN` in Render env vars.
- The system logs `WA_TOKEN_EXPIRED` when this happens.
