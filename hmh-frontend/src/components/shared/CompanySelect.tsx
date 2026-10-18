/**
 * Company picker, driven by the companies table.
 *
 * The group's trading names used to be typed into each form as two literal
 * `<option>` tags. Registering a new company then meant editing every screen
 * that offered the choice, and missing one silently left that form unable to
 * select it. This reads the list instead, so the set of companies is a
 * database question rather than a deployment question.
 *
 * `valueMode` decides what the form stores:
 *   "id"   — the company id. Correct for anything that should follow a
 *            company if it is ever renamed.
 *   "name" — the company name, for the fields that historically stored text
 *            and are still read as text elsewhere.
 */

import { useEffect, useState } from "react";

import { companiesApi, type Company } from "@/api/companies";
import { cn } from "@/lib/utils";

interface CompanySelectProps {
  value: string;
  onChange: (value: string) => void;
  valueMode?: "id" | "name";
  /** Extra fixed options rendered first — legacy keys that predate the table. */
  legacyOptions?: { value: string; label: string }[];
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  id?: string;
  className?: string;
}

export function CompanySelect({
  value,
  onChange,
  valueMode = "name",
  legacyOptions = [],
  placeholder = "— Select company —",
  required,
  disabled,
  id,
  className,
}: CompanySelectProps) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    companiesApi
      .list()
      .then((rows) => live && setCompanies(rows))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  const optionValue = (c: Company) => (valueMode === "id" ? c.id : c.name);

  // A saved value whose company is not in the list — deleted, renamed, or
  // simply not loaded yet. Keep it selectable so opening a form and saving
  // it cannot silently change which company a record belongs to.
  const known = new Set([
    ...legacyOptions.map((o) => o.value),
    ...companies.map(optionValue),
  ]);
  const orphaned = value && !known.has(value) ? value : null;

  return (
    <select
      id={id}
      value={value}
      required={required}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "h-10 w-full rounded-md border border-input bg-background px-3 text-sm",
        className,
      )}
    >
      <option value="">{failed ? "Could not load companies" : placeholder}</option>
      {legacyOptions.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
      {companies.map((c) => (
        <option key={c.id} value={optionValue(c)}>
          {c.name}
        </option>
      ))}
      {orphaned && <option value={orphaned}>{orphaned} (not in company list)</option>}
    </select>
  );
}
