import { useEffect, useState } from "react";
import { Plus, Building2, Trash2, Users, ChevronRight, X } from "lucide-react";
import { WriteGuard } from "@/components/shared/WriteGuard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { Modal } from "@/components/shared/Modal";
import { companiesApi, type Company, type CompanyWithSuppliers } from "@/api/companies";
import { suppliersApi, type Supplier } from "@/api/suppliers";

// ── Create company modal ──────────────────────────────────────────────────────

function CreateCompanyModal({ onClose, onCreated }: { onClose: () => void; onCreated: (c: Company) => void }) {
  const [name, setName] = useState("");
  const [regNo, setRegNo] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const company = await companiesApi.create({
        name,
        registration_number: regNo || null,
        contact_email: email || null,
        contact_phone: phone || null,
        address: address || null,
      });
      onCreated(company);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string; detail?: string } } })?.response?.data;
      setError(msg?.message || msg?.detail || "Failed to create company.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open title="New Company" onClose={onClose} size="md">
      <form onSubmit={submit} className="p-6 space-y-4">
        <div className="space-y-2">
          <Label>Company Name *</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="e.g. Acme Construction (Pty) Ltd" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Registration Number</Label>
            <Input value={regNo} onChange={(e) => setRegNo(e.target.value)} placeholder="e.g. 2020/123456/07" />
          </div>
          <div className="space-y-2">
            <Label>Contact Phone</Label>
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+27 11 000 0000" />
          </div>
        </div>
        <div className="space-y-2">
          <Label>Contact Email</Label>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="procurement@company.co.za" />
        </div>
        <div className="space-y-2">
          <Label>Address</Label>
          <textarea
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            rows={2}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
            placeholder="Physical address"
          />
        </div>
        {error && (
          <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>
        )}
        <div className="flex gap-2 pt-1">
          <Button type="submit" disabled={loading} className="flex-1">{loading ? "Creating…" : "Create Company"}</Button>
          <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Manage company suppliers modal ────────────────────────────────────────────

function ManageSuppliersModal({ company, onClose }: { company: Company; onClose: () => void }) {
  const [detail, setDetail] = useState<CompanyWithSuppliers | null>(null);
  const [allSuppliers, setAllSuppliers] = useState<Supplier[]>([]);
  const [linking, setLinking] = useState<string | null>(null);
  const [unlinking, setUnlinking] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = () => {
    companiesApi.get(company.id).then(setDetail);
  };

  useEffect(() => {
    load();
    suppliersApi.list().then(setAllSuppliers).catch(() => {});
  }, []);

  const linkedIds = new Set(detail?.suppliers.map((s) => s.id) ?? []);
  const available = allSuppliers.filter((s) => !linkedIds.has(s.id));

  const link = async (supplierId: string) => {
    setLinking(supplierId);
    setError("");
    try {
      await companiesApi.linkSupplier(company.id, supplierId);
      load();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string; detail?: string } } })?.response?.data;
      setError(msg?.message || msg?.detail || "Failed to link supplier.");
    } finally {
      setLinking(null);
    }
  };

  const unlink = async (supplierId: string) => {
    setUnlinking(supplierId);
    setError("");
    try {
      await companiesApi.unlinkSupplier(company.id, supplierId);
      load();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string; detail?: string } } })?.response?.data;
      setError(msg?.message || msg?.detail || "Failed to unlink supplier.");
    } finally {
      setUnlinking(null);
    }
  };

  return (
    <Modal open title={`Suppliers — ${company.name}`} onClose={onClose} size="lg">
      <div className="p-6 space-y-5">
        {error && (
          <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>
        )}

        {/* Linked suppliers */}
        <div>
          <p className="text-sm font-semibold mb-2">Linked Suppliers ({detail?.suppliers.length ?? 0})</p>
          {!detail ? (
            <Skeleton className="h-20 rounded-lg" />
          ) : detail.suppliers.length === 0 ? (
            <p className="text-sm text-muted-foreground bg-muted rounded-lg p-3">
              No suppliers linked yet. Add suppliers below so procurement is restricted to these.
            </p>
          ) : (
            <div className="space-y-1.5">
              {detail.suppliers.map((s) => (
                <div key={s.id} className="flex items-center justify-between bg-muted/50 rounded-lg px-3 py-2 text-sm">
                  <span>{s.name}</span>
                  <WriteGuard>
                    <button
                      onClick={() => unlink(s.id)}
                      disabled={unlinking === s.id}
                      className="text-muted-foreground hover:text-destructive transition-colors"
                      title="Remove supplier"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </WriteGuard>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Available to add */}
        <WriteGuard>
          <div>
            <p className="text-sm font-semibold mb-2">Add Supplier</p>
            {available.length === 0 ? (
              <p className="text-sm text-muted-foreground">All active suppliers are already linked.</p>
            ) : (
              <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
                {available.map((s) => (
                  <div key={s.id} className="flex items-center justify-between bg-card border border-border rounded-lg px-3 py-2 text-sm">
                    <span>{s.name}</span>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => link(s.id)}
                      disabled={linking === s.id}
                    >
                      {linking === s.id ? "Linking…" : "Add"}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </WriteGuard>

        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>Close</Button>
        </div>
      </div>
    </Modal>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [managing, setManaging] = useState<Company | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchCompanies = () => {
    setLoading(true);
    companiesApi.list().then(setCompanies).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { fetchCompanies(); }, []);

  const handleDelete = async (company: Company, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Delete company "${company.name}"?\n\nProjects linked to this company will have their company cleared but will not be deleted.`)) return;
    setDeleting(company.id);
    try {
      await companiesApi.delete(company.id);
      setCompanies((prev) => prev.filter((c) => c.id !== company.id));
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string; message?: string } } })?.response?.data;
      alert(d?.detail || d?.message || "Delete failed.");
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Companies"
        description="Manage companies and their approved supplier lists. Link a company to a project to restrict procurement to that company's suppliers."
        meta={loading ? undefined : `${companies.length} compan${companies.length !== 1 ? "ies" : "y"}`}
        actions={
          <WriteGuard>
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="w-4 h-4" />
              New Company
            </Button>
          </WriteGuard>
        }
      />

      <div className="grid grid-cols-1 gap-3">
        {loading ? (
          [1, 2, 3].map((i) => <Skeleton key={i} className="h-20 rounded-xl" />)
        ) : companies.length === 0 ? (
          <div className="bg-card border border-border rounded-xl p-12 text-center text-sm text-muted-foreground">
            No companies yet. Create a company, link its approved suppliers, then assign it to a project.
          </div>
        ) : (
          companies.map((company) => (
            <div
              key={company.id}
              className="bg-card border border-border rounded-xl p-5 flex items-center justify-between gap-4 group"
            >
              <div className="flex items-center gap-4 min-w-0">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg shrink-0 bg-primary/10 text-primary">
                  <Building2 className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <p className="font-semibold">{company.name}</p>
                  <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground flex-wrap">
                    {company.registration_number && <span>Reg: {company.registration_number}</span>}
                    {company.contact_email && <span>{company.contact_email}</span>}
                    {company.contact_phone && <span>{company.contact_phone}</span>}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setManaging(company)}
                  className="flex items-center gap-1.5"
                >
                  <Users className="w-3.5 h-3.5" />
                  Suppliers
                </Button>
                <WriteGuard>
                  <button
                    onClick={(e) => handleDelete(company, e)}
                    disabled={deleting === company.id}
                    className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors opacity-0 group-hover:opacity-100"
                    title="Delete company"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </WriteGuard>
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              </div>
            </div>
          ))
        )}
      </div>

      {showCreate && (
        <CreateCompanyModal
          onClose={() => setShowCreate(false)}
          onCreated={(company) => {
            setShowCreate(false);
            setCompanies((prev) => [company, ...prev]);
          }}
        />
      )}

      {managing && (
        <ManageSuppliersModal
          company={managing}
          onClose={() => setManaging(null)}
        />
      )}
    </div>
  );
}
