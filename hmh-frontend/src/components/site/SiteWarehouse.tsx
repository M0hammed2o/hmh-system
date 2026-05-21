/**
 * SiteWarehouse — backward-compatibility re-export.
 *
 * Phase 3B: The warehouse concept has moved from Site → Project.
 * All new code should import from ProjectWarehouse.tsx.
 * This file exists so existing imports still resolve.
 *
 * @deprecated Import ProjectWarehouse directly.
 */
export { ProjectWarehouse as SiteWarehouse, ProjectWarehouse } from "./ProjectWarehouse";
