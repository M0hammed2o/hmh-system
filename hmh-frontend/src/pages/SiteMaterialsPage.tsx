/**
 * Site dashboard material view — shows allocated vs used per lot.
 * Designed for phones. Site managers use this to see what's available.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle, Package, ChevronRight } from "lucide-react";
import { allocationApi, type LotAllocation } from "@/api/allocation";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import client from "@/api/client";

interface LotSummary {
  lot_id: string;
  lot_number: string;
  site_id: string;
  project_id: string;
  allocations: LotAllocation[];
  overrun_count: number;
}

function LotCard({ lot }: { lot: LotSummary }) {
  return (
    <Link to={`/lots/${lot.lot_id}`} className="block">
      <div className={cn(
        "bg-card border rounded-xl p-4 flex items-center gap-4 active:scale-95 transition-transform",
        lot.overrun_count > 0 ? "border-destructive/40" : "border-border"
      )}>
        <div className={cn(
          "flex items-center justify-center w-10 h-10 rounded-xl shrink-0",
          lot.overrun_count > 0 ? "bg-destructive/10" : "bg-green-500/10"
        )}>
          {lot.overrun_count > 0
            ? <AlertTriangle className="w-5 h-5 text-destructive" />
            : <CheckCircle className="w-5 h-5 text-green-500" />
          }
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold">Lot {lot.lot_number}</p>
          <p className="text-xs text-muted-foreground">
            {lot.allocations.length} material{lot.allocations.length !== 1 ? "s" : ""}
            {lot.overrun_count > 0 && (
              <span className="text-destructive font-medium"> · {lot.overrun_count} overrun{lot.overrun_count !== 1 ? "s" : ""}</span>
            )}
          </p>
        </div>
        <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
      </div>
    </Link>
  );
}

interface LotsResponse {
  items: Array<{ id: string; lot_number: string; site_id: string | null; project_id: string }>;
}

export default function SiteMaterialsPage() {
  const [lots, setLots] = useState<LotSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [projectId, setProjectId] = useState<string>("");

  useEffect(() => {
    // Get first active project then its lots
    async function load() {
      try {
        const projRes = await client.get<{ data: Array<{ id: string }> }>("/projects/", { params: { status: "ACTIVE", limit: 1 } });
        const projects = projRes.data.data;
        if (!projects || projects.length === 0) { setLoading(false); return; }
        const pid = projects[0].id;
        setProjectId(pid);

        const lotsRes = await client.get<{ data: LotsResponse }>(`/projects/${pid}/lots/`, { params: { limit: 50 } });
        const lotList = lotsRes.data.data?.items || [];

        // Load allocations for each lot in parallel
        const summaries = await Promise.all(
          lotList.map(async (lot) => {
            try {
              const allocs = await allocationApi.getLotAllocations(lot.id);
              return {
                lot_id: lot.id,
                lot_number: lot.lot_number,
                site_id: lot.site_id || "",
                project_id: pid,
                allocations: allocs,
                overrun_count: allocs.filter((a) => a.is_over).length,
              };
            } catch {
              return {
                lot_id: lot.id,
                lot_number: lot.lot_number,
                site_id: lot.site_id || "",
                project_id: pid,
                allocations: [],
                overrun_count: 0,
              };
            }
          })
        );

        // Sort: overruns first
        summaries.sort((a, b) => b.overrun_count - a.overrun_count);
        setLots(summaries);
      } catch {
        setError("Failed to load site materials.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const totalOverruns = lots.reduce((sum, l) => sum + l.overrun_count, 0);

  return (
    <div className="space-y-4 animate-fade-in">
      <div>
        <h1 className="text-lg font-bold">Site Materials</h1>
        <p className="text-sm text-muted-foreground">
          {lots.length} lots · {totalOverruns > 0 ? (
            <span className="text-destructive font-medium">{totalOverruns} overrun{totalOverruns !== 1 ? "s" : ""}</span>
          ) : "all on track"}
        </p>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">{error}</div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
        </div>
      ) : lots.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-10 text-center">
          <Package className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No lots with allocations found.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {lots.map((lot) => <LotCard key={lot.lot_id} lot={lot} />)}
        </div>
      )}
    </div>
  );
}
