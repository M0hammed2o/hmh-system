"""
AI OCR Service — Claude-powered invoice field extraction (Phase 6A).

Wraps raw OCR text with a Claude Haiku prompt that returns:
  - 8 invoice header fields (Supplier, Invoice Number, Invoice Date, PO Number,
    VAT Number, Net Amount, VAT Amount, Gross Amount) each with a confidence score
  - Line items (Description, Quantity, Unit Rate, Total)
  - Overall extraction confidence

Per-field confidence thresholds:
  ≥ 0.80 → high    (green)
  ≥ 0.50 → medium  (amber)
  <  0.50 → low     (red)

Output shape (ai_extraction_json stored as JSON string):
{
  "header": {
    "supplier_name":    { "value": "...", "confidence": 0.95 },
    "invoice_number":   { "value": "...", "confidence": 0.90 },
    "invoice_date":     { "value": "...", "confidence": 0.85 },
    "po_number":        { "value": "...", "confidence": 0.80 },
    "vat_number":       { "value": "...", "confidence": 0.70 },
    "net_amount":       { "value": 8625.00, "confidence": 0.95 },
    "vat_amount":       { "value": 1293.75, "confidence": 0.90 },
    "gross_amount":     { "value": 9918.75, "confidence": 0.95 }
  },
  "line_items": [
    { "description": "...", "quantity": 10, "unit_rate": 862.50, "total": 8625.00, "confidence": 0.80 }
  ],
  "overall_confidence": 0.88,
  "model":   "claude-haiku-4-5-20251001",
  "low_confidence_fields": ["vat_number"],
  "warnings": []
}

Never raises — always returns a structured result. Sets status to NEEDS_REVIEW
when API key is missing or extraction fails.
"""

import json
import logging
import re
from typing import Any

from app.core.logging_config import get_logger

logger = get_logger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024

# Fields considered "key" for determining overall quality
_HEADER_FIELDS = [
    "supplier_name",
    "invoice_number",
    "invoice_date",
    "po_number",
    "vat_number",
    "net_amount",
    "vat_amount",
    "gross_amount",
]

_LOW_CONF_THRESHOLD = 0.50
_HIGH_CONF_THRESHOLD = 0.80

_SYSTEM_PROMPT = """You are a precise invoice data extraction assistant for a South African construction procurement system.

Extract invoice fields from the provided text and return ONLY a JSON object with no extra commentary.

Rules:
- Amounts must be numeric floats (no currency symbols, no commas). Use null if not found.
- Dates must be in ISO format YYYY-MM-DD. Use null if not found.
- confidence is a float 0.0–1.0: 1.0 = very certain, 0.5 = uncertain, 0.0 = guessed.
- If a field is not present in the text, set value to null and confidence to 0.0.
- vat_number is the supplier's VAT registration number (format: 4XXXXXXXXX in SA).
- net_amount = amount before VAT; vat_amount = VAT portion; gross_amount = total including VAT.
- Do not invent values. Only extract what is explicitly present in the text.

Return ONLY this JSON structure (no markdown, no explanation):
{
  "header": {
    "supplier_name":  { "value": "...",   "confidence": 0.0 },
    "invoice_number": { "value": "...",   "confidence": 0.0 },
    "invoice_date":   { "value": "...",   "confidence": 0.0 },
    "po_number":      { "value": "...",   "confidence": 0.0 },
    "vat_number":     { "value": "...",   "confidence": 0.0 },
    "net_amount":     { "value": null,    "confidence": 0.0 },
    "vat_amount":     { "value": null,    "confidence": 0.0 },
    "gross_amount":   { "value": null,    "confidence": 0.0 }
  },
  "line_items": [
    { "description": "...", "quantity": null, "unit_rate": null, "total": null, "confidence": 0.0 }
  ]
}"""


def _build_user_prompt(raw_text: str) -> str:
    truncated = raw_text[:6000]  # stay well within Haiku context limit
    return f"Extract invoice fields from this document text:\n\n{truncated}"


def _parse_claude_response(content: str) -> dict:
    """
    Parse Claude's JSON response. Handles markdown code fences if present.
    Returns the parsed dict or raises ValueError on parse failure.
    """
    text = content.strip()
    # Strip markdown fences
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fenced:
        text = fenced.group(1).strip()
    # Find the outermost JSON object
    start = text.find("{")
    if start != -1:
        text = text[start:]
    return json.loads(text)


def _normalise_header_field(raw: Any) -> dict:
    """Ensure each header field has {value, confidence} shape."""
    if not isinstance(raw, dict):
        return {"value": None, "confidence": 0.0}
    value = raw.get("value")
    conf = float(raw.get("confidence", 0.0))
    conf = max(0.0, min(1.0, conf))
    return {"value": value, "confidence": conf}


def _normalise_line_item(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {"description": "", "quantity": None, "unit_rate": None, "total": None, "confidence": 0.0}
    return {
        "description": str(raw.get("description") or ""),
        "quantity":    _to_float(raw.get("quantity")),
        "unit_rate":   _to_float(raw.get("unit_rate")),
        "total":       _to_float(raw.get("total")),
        "confidence":  max(0.0, min(1.0, float(raw.get("confidence", 0.0)))),
    }


def _to_float(v: Any) -> Any:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _compute_overall_confidence(header: dict) -> float:
    """Average confidence across the 8 header fields."""
    scores = [header[f]["confidence"] for f in _HEADER_FIELDS if f in header]
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 3)


def _find_low_confidence_fields(header: dict) -> list[str]:
    return [f for f in _HEADER_FIELDS if header.get(f, {}).get("confidence", 0.0) < _LOW_CONF_THRESHOLD]


def extract_invoice_fields_with_ai(raw_text: str) -> dict:
    """
    Send raw OCR text to Claude Haiku and return structured extraction with per-field confidence.

    Returns a dict in the ai_extraction_json shape. Never raises — status field
    indicates success ("AI_EXTRACTED"), partial success ("NEEDS_REVIEW"), or failure ("FAILED").
    """
    result: dict = {
        "status": "FAILED",
        "model": _MODEL,
        "header": {f: {"value": None, "confidence": 0.0} for f in _HEADER_FIELDS},
        "line_items": [],
        "overall_confidence": 0.0,
        "low_confidence_fields": list(_HEADER_FIELDS),
        "warnings": [],
    }

    if not raw_text or not raw_text.strip():
        result["warnings"].append("No text to extract — raw_text is empty.")
        result["status"] = "NEEDS_REVIEW"
        return result

    from app.core.config import settings
    api_key = settings.ANTHROPIC_API_KEY
    if not api_key:
        result["warnings"].append(
            "ANTHROPIC_API_KEY is not set — AI extraction unavailable. "
            "Set this in your .env or Render environment variables."
        )
        result["status"] = "NEEDS_REVIEW"
        return result

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_prompt(raw_text)}],
        )

        response_text = message.content[0].text if message.content else ""
        logger.debug("Claude response chars=%d", len(response_text))

        parsed = _parse_claude_response(response_text)

        # Normalise header fields
        raw_header = parsed.get("header", {})
        header: dict = {}
        for field in _HEADER_FIELDS:
            header[field] = _normalise_header_field(raw_header.get(field, {}))

        # Normalise line items
        raw_items = parsed.get("line_items", [])
        if not isinstance(raw_items, list):
            raw_items = []
        line_items = [_normalise_line_item(item) for item in raw_items[:50]]  # cap at 50 items

        overall = _compute_overall_confidence(header)
        low_fields = _find_low_confidence_fields(header)

        result.update({
            "status": "AI_EXTRACTED" if overall >= _LOW_CONF_THRESHOLD else "NEEDS_REVIEW",
            "header": header,
            "line_items": line_items,
            "overall_confidence": overall,
            "low_confidence_fields": low_fields,
            "warnings": [],
        })

        if low_fields:
            result["warnings"].append(
                f"Low confidence on: {', '.join(f.replace('_', ' ') for f in low_fields)}. "
                "Human review required."
            )

        logger.info(
            "AI OCR extraction complete overall_confidence=%.2f low_fields=%s",
            overall, low_fields,
        )

    except json.JSONDecodeError as exc:
        logger.warning("Claude returned invalid JSON: %s", exc)
        result["warnings"].append(f"Claude response could not be parsed as JSON: {exc}")
        result["status"] = "NEEDS_REVIEW"

    except Exception as exc:
        logger.exception("AI OCR extraction failed: %s", exc)
        result["warnings"].append(f"AI extraction error: {exc}")
        result["status"] = "FAILED"

    return result


def merge_ai_with_regex(regex_result: dict, ai_result: dict) -> dict:
    """
    Merge Claude AI extraction into the existing regex-based result dict.
    Regex fields are kept as fallback when AI confidence is low.
    Returns the enriched result dict (in-place modification of regex_result).
    """
    if ai_result.get("status") not in ("AI_EXTRACTED", "NEEDS_REVIEW"):
        return regex_result

    header = ai_result.get("header", {})
    fields = regex_result.setdefault("fields", {})

    # Map AI header fields → regex fields dict keys
    field_map = {
        "supplier_name":  "supplier_name",
        "invoice_number": "invoice_number",
        "invoice_date":   "date",
        "po_number":      "po_number",
        "vat_number":     "vat_number",
        "net_amount":     "subtotal",
        "vat_amount":     "vat_amount",
        "gross_amount":   "total_amount",
    }

    for ai_key, regex_key in field_map.items():
        ai_field = header.get(ai_key, {})
        ai_value = ai_field.get("value")
        ai_conf  = ai_field.get("confidence", 0.0)
        # Use AI value if confidence ≥ 0.50 and value is non-empty
        if ai_value is not None and ai_conf >= _LOW_CONF_THRESHOLD:
            fields[regex_key] = ai_value

    # Replace line items if AI found some
    if ai_result.get("line_items"):
        regex_result["items"] = [
            {
                "description": item["description"],
                "unit":        None,
                "quantity":    item["quantity"],
                "unit_price":  item["unit_rate"],
                "line_total":  item["total"],
                "confidence":  item["confidence"],
            }
            for item in ai_result["line_items"]
        ]

    # Attach AI metadata to result
    regex_result["ai_extraction"] = ai_result
    regex_result["confidence_score"] = ai_result.get("overall_confidence", 0.0)

    return regex_result
