import { useEffect, useState } from "react";
import { Package, Layers, Activity, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Modal } from "@/components/shared/Modal";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { Tabs } from "@/components/shared/Tabs";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import { stockApi, type StockBalance, type StockLedgerEntry, type UsageLogCreate } from "@/api/stock";
import { formatDateTime } from "@/lib/format";

const MOVEMENT_LABEL: Record<string, string> = {
  OPENING_BALANCE: "Opening",
  DELIVERY_RECEIVED: "Delivery",
  USAGE: "Usage",
  ADJUSTMENT_ADD: "Adj +",
  ADJUSTMENT_SUBTRACT: "Adj −",
  RETURN_TO_STORE: "Return",
  TRANSFER_IN: "Transfer In",
  TRANSFER_OUT: "Transfer Out",
};

const PAGE_TABS = [
  { key: "balances", label: "Stock Balances" },
  { key: "ledger", label: "Ledger" },
];

// ─── Record Usage Modal ────────────────────────────────────────────────────────
function RecordUsageModal({
  open,
  onClose,
  sites,
  balances,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  sites: Site[];
  balances: StockBalance[];
  onSubmit: (data: UsageLogCreate) => Promise<void>;
}) {
  const [siteId, setSiteId] = useState(sites[0]?.id ?? "");
  const [itemId, setItemId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [usedBy, setUsedBy] = useState("");
  const [usageDate, setUsageDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [comments, setComments] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (sites.length > 0 && !siteId) setSiteId(sites[0].id);
  }, [sites, siteId]);

  // Items available in selected site
  const siteBalances = balances.filter((b) => b.site_id === siteId && b.balance > 0);

  useEffect(() => {
    setItemId(siteBalances[0]?.item_id ?? "");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId]);

  const selectedBalance = siteBalances.find((b) => b.item_id === itemId);

  const handleSubmit = async () => {
    if (!siteId || !itemId || !quantity) return;
    setSaving(true);
    try {
      await onSubmit({
        site_id: siteId,
        item_id: itemId,
        quantity_used: parseFloat(quantity),
        used_by_person_name: usedBy.trim() || null,
        usage_date: usageDate ? new Date(usageDate).toISOString() : null,
        comments: comments.trim() || null,
      });
      setQuantity(""); setUsedBy(""); setComments("");
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title="Record Material Usage" onClose={onClose} size="sm">
      <div className="p-6 space-y-4">
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Site *</label>
          <select
            value={siteId}
            onChange={(e) => setSiteId(e.target.value)}
            className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">— Select site —</option>
            {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Material *</label>
          <select
            value={itemId}
            onChange={(e) => setItemId(e.target.value)}
            className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">— Select material —</option>
            {siteBalances.map((b) => (
              <option key={b.item_id} value={b.item_id}>
                {b.item_name ?? b.item_id.slice(0, 8)} (balance: {b.balance.toLocaleString("en-ZA")} {b.item_unit ?? ""})
              </option>
            ))}
          </select>
          {selectedBalance && (
            <p className="text-xs text-muted-foreground mt-1">
              Available: <span className="font-medium">{selectedBalance.balance.toLocaleString("en-ZA")} {selectedBalance.item_unit ?? ""}</span>
            </p>
          )}
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Quantity Used *</label>
            <input
              type="number"
              min="0.01"
              step="any"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Usage Date *</label>
            <input
              type="date"
              value={usageDate}
              onChange={(e) => setUsageDate(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Used By</label>
          <input
            type="text"
            value={usedBy}
            onChange={(e) => setUsedBy(e.target.value)}
            placeholder="Person or team name"
            className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Comments</label>
          <textarea
            value={comments}
            onChange={(e) => setComments(e.target.value)}
            rows={2}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
          />
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={handleSubmit} disabled={saving || !siteId || !itemId || !quantity}>
            {saving ? "Recording…" : "Record Usage"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────────
export default function StockPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [sites, setSites] = useState<Site[]>([]);
  const [filterSiteId, setFilterSiteId] = useState<string>("all");
  const [tab, setTab] = useState("balances");
  const [showUsage, setShowUsage] = useState(false);

  const [balances, setBalances] = useState<StockBalance[]>([]);
  const [ledger, setLedger] = useState<StockLedgerEntry[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    projectsApi
      .list(1, 100)
      .then((res) => {
        setProjects(res.items);
        if (res.items.length > 0) setSelectedProjectId(res.items[0].id);
      })
      .catch(() => {})
      .finally(() => setLoadingProjects(false));
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    setFilterSiteId("all");
    sitesApi
      .list(selectedProjectId)
      .then(setSites)
      .catch(() => setSites([]));
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) return;
    setLoadingData(true);
    const siteParam = filterSiteId !== "all" ? filterSiteId : undefined;

    if (tab === "balances") {
      stockApi
        .getBalances(selectedProjectId, siteParam)
        .then(setBalances)
        .catch(() => setBalances([]))
        .finally(() => setLoadingData(false));
    } else {
      stockApi
        .getLedger(selectedProjectId, { site_id: siteParam, limit: 200 })
        .then(setLedger)
        .catch(() => setLedger([]))
        .finally(() => setLoadingData(false));
    }
  }, [selectedProjectId, filterSiteId, tab]);

  const siteMap = Object.fromEntries(sites.map((s) => [s.id, s]));
  const filteredBalances = filterSiteId === "all"
    ? balances
    : balances.filter((b) => b.site_id === filterSiteId);

  const uniqueItems = new Set(filteredBalances.map((b) => b.item_id)).size;
  const sitesWithStock = new Set(filteredBalances.map((b) => b.site_id)).size;

  const handleRecordUsage = async (data: UsageLogCreate) => {
    await stockApi.recordUsage(selectedProjectId, data);
    const siteParam = filterSiteId !== "all" ? filterSiteId : undefined;
    const updated = await stockApi.getBalances(selectedProjectId, siteParam);
    setBalances(updated);
  };

  const handleRefresh = async () => {
    if (!selectedProjectId) return;
    setRefreshing(true);
    const siteParam = filterSiteId !== "all" ? filterSiteId : undefined;
    try {
      if (tab === "balances") {
        const updated = await stockApi.getBalances(selectedProjectId, siteParam);
        setBalances(updated);
      } else {
        const updated = await stockApi.getLedger(selectedProjectId, { site_id: siteParam, limit: 200 });
        setLedger(updated);
      }
    } finally {
      setRefreshing(false);
    }
  };

  if (loadingProjects) {
    return (
      <div className="space-y-5 animate-fade-in">
        <Skeleton className="h-12 rounded-xl" />
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Stock Balances"
        description="Current on-site material stock derived from the delivery ledger."
        actions={
          selectedProjectId ? (
            <Button size="sm" onClick={() => setShowUsage(true)}>
              <Plus className="w-4 h-4" />
              Record Usage
            </Button>
          ) : undefined
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Project</label>
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[220px]"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Site</label>
          <select
            value={filterSiteId}
            onChange={(e) => setFilterSiteId(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[180px]"
          >
            <option value="all">All Sites</option>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
        <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing} title="Refresh stock data">
          <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard title="Stock Lines" value={filteredBalances.length} icon={Package} color="bg-primary/10 text-primary" />
        <StatCard title="Unique Materials" value={uniqueItems} icon={Layers} color="bg-warning/10 text-warning" />
        <StatCard title="Sites with Stock" value={sitesWithStock} icon={Activity} color="bg-success/10 text-success" />
      </div>

      <Tabs tabs={PAGE_TABS} active={tab} onChange={setTab} />

      {loadingData ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12 rounded-xl" />)}
        </div>
      ) : tab === "balances" ? (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {filteredBalances.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted-foreground">No stock balances found.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Material</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Site</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">Balance</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">Unit</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Last Movement</th>
                </tr>
              </thead>
              <tbody>
                {filteredBalances.map((sb) => (
                  <tr
                    key={`${sb.item_id}-${sb.site_id}-${sb.lot_id ?? "null"}`}
                    className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-4 py-3 font-medium">{sb.item_name ?? sb.item_id.slice(0, 8)}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs" title={siteMap[sb.site_id]?.name ?? sb.site_id}>
                        {siteMap[sb.site_id]?.code ?? sb.site_id.slice(0, 8)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold">
                      <span className={sb.balance <= 0 ? "text-destructive" : sb.balance < 50 ? "text-warning" : ""}>
                        {sb.balance.toLocaleString("en-ZA")}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-muted-foreground">{sb.item_unit ?? "—"}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {sb.last_movement_date ? formatDateTime(sb.last_movement_date) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {ledger.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted-foreground">No ledger entries found.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Movement</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Item</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Site</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">In</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">Out</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Notes</th>
                </tr>
              </thead>
              <tbody>
                {ledger.map((entry) => (
                  <tr key={entry.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 text-xs text-muted-foreground">{formatDateTime(entry.movement_date)}</td>
                    <td className="px-4 py-3 text-xs font-medium">
                      {MOVEMENT_LABEL[entry.movement_type] ?? entry.movement_type}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{entry.item_id.slice(0, 8)}</td>
                    <td className="px-4 py-3 text-xs">
                      {siteMap[entry.site_id]?.code ?? entry.site_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-success">
                      {entry.quantity_in > 0 ? `+${entry.quantity_in.toLocaleString("en-ZA")}` : "—"}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-destructive">
                      {entry.quantity_out > 0 ? `-${entry.quantity_out.toLocaleString("en-ZA")}` : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground max-w-[160px] truncate" title={entry.notes ?? ""}>
                      {entry.notes ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <RecordUsageModal
        open={showUsage}
        onClose={() => setShowUsage(false)}
        sites={sites}
        balances={balances}
        onSubmit={handleRecordUsage}
      />
    </div>
  );
}
