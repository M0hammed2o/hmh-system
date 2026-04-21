import { useEffect, useState } from "react";
import { Plus, UserX, Pencil, ShieldOff } from "lucide-react";
import { usersApi, type User, type UserCreate, type UserRole } from "@/api/users";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/format";
import { useAuthContext, ADMIN_ROLES } from "@/context/AuthContext";

const ROLES: UserRole[] = ["OWNER", "OFFICE_ADMIN", "OFFICE_USER", "SITE_MANAGER", "SITE_STAFF"];

const roleLabel: Record<UserRole, string> = {
  OWNER: "Owner",
  OFFICE_ADMIN: "Office Admin",
  OFFICE_USER: "Office User",
  SITE_MANAGER: "Site Manager",
  SITE_STAFF: "Site Staff",
};

function roleBadgeVariant(role: UserRole) {
  if (role === "OWNER") return "default" as const;
  if (role === "OFFICE_ADMIN") return "secondary" as const;
  return "outline" as const;
}

interface CreateModalProps {
  onClose: () => void;
  onCreated: (user: User, tempPwd: string) => void;
}

function CreateUserModal({ onClose, onCreated }: CreateModalProps) {
  const [form, setForm] = useState<UserCreate>({ full_name: "", email: "", role: "OFFICE_USER" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { user, temp_password } = await usersApi.create(form);
      onCreated(user, temp_password);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to create user.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-5">Create User</h2>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label>Full Name</Label>
            <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
          </div>
          <div className="space-y-2">
            <Label>Email</Label>
            <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          </div>
          <div className="space-y-2">
            <Label>Phone (optional)</Label>
            <Input value={form.phone ?? ""} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </div>
          <div className="space-y-2">
            <Label>Role</Label>
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {ROLES.map((r) => <option key={r} value={r}>{roleLabel[r]}</option>)}
            </select>
          </div>
          {error && (
            <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>
          )}
          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading} className="flex-1">
              {loading ? "Creating…" : "Create User"}
            </Button>
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface TempPwdBannerProps {
  user: User;
  password: string;
  onDismiss: () => void;
}

function TempPwdBanner({ user, password, onDismiss }: TempPwdBannerProps) {
  return (
    <div className="bg-success/10 border border-success/30 rounded-xl p-4 flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-semibold text-success">User created successfully</p>
        <p className="text-sm text-foreground mt-1">
          Share this temporary password with <strong>{user.full_name}</strong>. It will not be shown again.
        </p>
        <p className="mt-2 font-mono text-sm bg-card border border-border rounded-md px-3 py-1.5 inline-block">
          {password}
        </p>
      </div>
      <button onClick={onDismiss} className="text-muted-foreground hover:text-foreground text-xs shrink-0">Dismiss</button>
    </div>
  );
}

interface EditModalProps {
  user: User;
  onClose: () => void;
  onSaved: () => void;
}

function EditUserModal({ user, onClose, onSaved }: EditModalProps) {
  const [form, setForm] = useState({ full_name: user.full_name, phone: user.phone ?? "", role: user.role });
  const [loading, setLoading] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const [error, setError] = useState("");
  const [tempPwd, setTempPwd] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await usersApi.update(user.id, {
        full_name: form.full_name,
        phone: form.phone || undefined,
        role: form.role,
      });
      onSaved();
      onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to update user.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async () => {
    if (!confirm(`Reset password for ${user.full_name}? They will need to set a new password on next login.`)) return;
    setResetLoading(true);
    setError("");
    try {
      const { temp_password } = await usersApi.resetPassword(user.id);
      setTempPwd(temp_password);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to reset password.";
      setError(msg);
    } finally {
      setResetLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-5">Edit User</h2>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label>Full Name</Label>
            <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
          </div>
          <div className="space-y-2">
            <Label>Email</Label>
            <Input value={user.email} disabled className="opacity-60 cursor-not-allowed" />
          </div>
          <div className="space-y-2">
            <Label>Phone (optional)</Label>
            <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </div>
          <div className="space-y-2">
            <Label>Role</Label>
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as typeof form.role })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {ROLES.map((r) => <option key={r} value={r}>{roleLabel[r]}</option>)}
            </select>
          </div>

          {/* Password reset section */}
          <div className="border border-border rounded-lg p-3 space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Password Reset</p>
            {tempPwd ? (
              <div className="space-y-1">
                <p className="text-xs text-foreground">New temporary password — share with user:</p>
                <p className="font-mono text-sm bg-muted border border-border rounded-md px-3 py-1.5 inline-block">{tempPwd}</p>
                <p className="text-xs text-muted-foreground">User will be required to change it on next login.</p>
              </div>
            ) : (
              <Button type="button" variant="outline" size="sm" onClick={handleResetPassword} disabled={resetLoading}>
                {resetLoading ? "Resetting…" : "Reset Password"}
              </Button>
            )}
          </div>

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>
          )}
          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading} className="flex-1">
              {loading ? "Saving…" : "Save Changes"}
            </Button>
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function UsersPage() {
  const { role, loading: authLoading } = useAuthContext();
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [created, setCreated] = useState<{ user: User; password: string } | null>(null);
  const [editingUser, setEditingUser] = useState<User | null>(null);

  const [error, setError] = useState("");

  // Don't fetch if the user's role doesn't have permission — avoids the 403
  const canAccess = !authLoading && role !== null && ADMIN_ROLES.includes(role);

  useEffect(() => {
    if (!canAccess) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    usersApi.list(page, 20)
      .then((res) => {
        if (cancelled) return;
        setUsers(res.items);
        setTotal(res.total);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const status = (err as { response?: { status?: number } })?.response?.status;
        const msg = status === 403
          ? "You do not have permission to view users."
          : (err as { response?: { data?: { message?: string } } })?.response?.data?.message
            || "Failed to load users.";
        setError(msg);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, canAccess]);

  const fetchUsers = (p?: number) => {
    if (!canAccess) return;
    const target = p ?? page;
    setLoading(true);
    setError("");
    usersApi.list(target, 20)
      .then((res) => { setUsers(res.items); setTotal(res.total); })
      .catch((err: unknown) => {
        const status = (err as { response?: { status?: number } })?.response?.status;
        const msg = status === 403
          ? "You do not have permission to view users."
          : (err as { response?: { data?: { message?: string } } })?.response?.data?.message
            || "Failed to load users.";
        setError(msg);
      })
      .finally(() => setLoading(false));
  };

  const handleDeactivate = async (id: string) => {
    if (!confirm("Deactivate this user?")) return;
    await usersApi.deactivate(id);
    fetchUsers();
  };

  const totalPages = Math.ceil(total / 20) || 1;

  // Show access-denied for roles that can't see users
  if (!authLoading && !canAccess) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
        <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-destructive/10">
          <ShieldOff className="w-7 h-7 text-destructive" />
        </div>
        <div>
          <p className="font-semibold text-base">Access Denied</p>
          <p className="text-sm text-muted-foreground mt-1">
            Your role (<span className="font-mono font-medium">{role ?? "unknown"}</span>) does not have
            permission to view user management. Contact an Owner or Office Admin.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{total} user{total !== 1 ? "s" : ""} registered</p>
        </div>
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4" />
          New User
        </Button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Temp password banner */}
      {created && (
        <TempPwdBanner
          user={created.user}
          password={created.password}
          onDismiss={() => setCreated(null)}
        />
      )}

      {/* Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-10 rounded-lg" />)}
          </div>
        ) : users.length === 0 ? (
          <div className="p-12 text-center text-sm text-muted-foreground">No users found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Name</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Email</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Role</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Created</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 font-medium">{u.full_name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                  <td className="px-4 py-3">
                    <Badge variant={roleBadgeVariant(u.role)}>{roleLabel[u.role]}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={u.is_active ? "success" : "destructive"}>
                      {u.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">{formatDate(u.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1 justify-end">
                      <button
                        onClick={() => setEditingUser(u)}
                        className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                        title="Edit"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      {u.is_active && (
                        <button
                          onClick={() => handleDeactivate(u.id)}
                          className="p-1.5 rounded-md hover:bg-destructive/10 transition-colors text-muted-foreground hover:text-destructive"
                          title="Deactivate"
                        >
                          <UserX className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>Page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
            <Button variant="outline" size="sm" disabled={page === totalPages} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onCreated={(user, password) => {
            setShowCreate(false);
            setCreated({ user, password });
            fetchUsers(1);
            setPage(1);
          }}
        />
      )}

      {editingUser && (
        <EditUserModal
          user={editingUser}
          onClose={() => setEditingUser(null)}
          onSaved={() => fetchUsers()}
        />
      )}
    </div>
  );
}
