# WhatsApp Cloud API Integration — HMH Construction OS

## Setup

### 1. Set environment variables in `.env`

```
WHATSAPP_ENABLED=true
WHATSAPP_PHONE_NUMBER_ID=1056675287538133
WHATSAPP_BUSINESS_ACCOUNT_ID=1304422375236768
WHATSAPP_ACCESS_TOKEN=<your permanent token from Meta Developer Console>
WHATSAPP_VERIFY_TOKEN=hmh-whatsapp-verify-token
WHATSAPP_API_VERSION=v25.0
WHATSAPP_TEST_TO=27837866021
```

**Never commit the `WHATSAPP_ACCESS_TOKEN` to git.**  
The `.env` file is already in `.gitignore`.

---

## Message Types

### Plain Text Messages
```
POST https://graph.facebook.com/v25.0/{phone_number_id}/messages
{ "type": "text", "text": { "body": "..." } }
```

**Important limitations:**
- Plain text messages only work when the recipient has **first messaged your business** number OR you are within an active **24-hour conversation window**.
- If the recipient has not messaged you recently, the API will return an error like `130472: Template message required`.

### Template Messages
- Use `send_template_message(to, template_name)` for proactive outbound messages outside the 24-hour window.
- Templates must be **pre-approved** in [Meta Business Manager](https://business.facebook.com).
- Approval typically takes 1–24 hours.

### ⚠️ Do NOT use `hello_world` template for real numbers
The `hello_world` template only works with Meta's **public test numbers**. For your real business phone number, you need to create and submit your own templates for approval.

**Recommended templates to create in Meta Business Manager:**
- `hmh_overrun_alert` — for BOQ overuse notifications
- `hmh_approval_request` — for pending approval notifications
- `hmh_daily_summary` — for daily business summaries

---

## Webhook Setup

### Register the webhook in Meta Developer Console:
1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Open your App → WhatsApp → Configuration
3. Set Callback URL: `https://your-domain.com/api/v1/whatsapp/webhook`
4. Set Verify Token: `hmh-whatsapp-verify-token` (or whatever `WHATSAPP_VERIFY_TOKEN` is set to)
5. Subscribe to: `messages`, `message_status`

### Verification endpoint:
```
GET /api/v1/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=hmh-whatsapp-verify-token&hub.challenge=CHALLENGE
```
Returns the challenge string on success.

---

## Inbound Commands

Users can reply to WhatsApp notifications with these commands:

| Command | Effect |
|---------|--------|
| `ACK` / `OK` / `SEEN` | Acknowledge open alerts for this number |
| `APPROVE MR-002` | Approve material request MR-002 |
| `REJECT MR-002 reason here` | Reject MR-002 with a reason |

---

## Test the Integration

```cmd
cd hmh-backend
python scripts/test_whatsapp.py
```

This sends a plain-text message to `WHATSAPP_TEST_TO`.  
The access token is **never printed** by this script.

---

## Demo Mode (WHATSAPP_ENABLED=false)

Set `WHATSAPP_ENABLED=false` to run in mock mode:
- No real HTTP calls are made
- Messages are stored in the `notification_queue` table as `MOCK_SENT`
- Viewable on the WhatsApp Queue page in the frontend (`/whatsapp-queue`)

---

## Alert → WhatsApp Mapping

| Alert Type | Severity | Sends WhatsApp? |
|------------|----------|-----------------|
| MATERIAL_OVERUSE | HIGH | ✓ (to `receives_material_alerts` recipients) |
| BOQ_ALLOCATION_EXCEEDED | HIGH | ✓ |
| INVOICE_MISMATCH | MEDIUM | ✓ (to `receives_invoice_alerts`) |
| DELIVERY_DISCREPANCY | MEDIUM | ✓ (to `receives_delivery_alerts`) |
| SITE_DELAY | MEDIUM | ✓ |
| VEHICLE_REPAIR_LOGGED | MEDIUM | ✓ (to `receives_vehicle_alerts`) |
| DAILY_SUMMARY | LOW | ✓ (to `receives_daily_summary`) |

Recipients are managed on the **Alerts → Recipients** page.
