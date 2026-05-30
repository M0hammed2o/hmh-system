import { useEffect, useState } from "react";
import { Plus, UserX, Pencil, ShieldOff, Copy, Check, FolderOpen, X as XIcon } from "lucide-react";
import { usersApi, type User, type UserCreate, type UserRole, type UserProjectAccess, SITE_REQUIRING_ROLES } from "@/api/users";
import { projectsApi, type Project } from "@/api/projects";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/format";
import { useAuthContext, ADMIN_ROLES } from "@/context/AuthContext";

const ROLES: UserRole[] = ["OWNER", "OFFICE_ADMIN", "OFFICE_USER", "SITE_MANAGER", "SITE_MANAGER_VIEW", "SITE_STAFF", "READ_ONLY"];

const roleLabel: Record<UserRole, string> = {
  OWNER:             "Owner",
  OFFICE_ADMIN:      "Office Admin",
  OFFICE_USER:       "Office User",
  SITE_MANAGER:      "Site Manager",
  SITE_MANAGER_VIEW: "Site Manager View Only",
  SITE_STAFF:        "Site Staff",
  READ_ONLY:         "Owner View Only",
};

const roleDescription: Partial<Record<UserRole, string>> = {
  READ_ONLY:         "View dashboards and reports only — cannot create, edit, or approve anything.",
  SITE_MANAGER_VIEW: "Can view site data, reports, and progress — cannot create, edit, or approve anything.",
};

function roleBadgeVariant(role: UserRole) {
  if (role === "OWNER") return "default" as const;
  if (role === "OFFICE_ADMIN") return "secondary" as const;
  return "outline" as const;
}

interface CreateModalProps {
  onClose: () => void;
  onCreated: (user: User, tempPwd: string) => void;
  projects: Project[];
}

function CreateUserModal({ onClose, onCreated, projects }: CreateModalProps) {
  const [form, setForm] = useState<UserCreate>({ full_name: "", email: "", role: "OFFICE_USER" });
  const [selectedProjectIds, setSelectedProjectIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const needsProject = SITE_REQUIRING_ROLES.has(form.role);

  const toggleProject = (id: string) =>
    setSelectedProjectIds(prev => prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (needsProject && selectedProjectIds.length === 0) {
      setError(`Role '${roleLabel[form.role]}' requires at least one assigned project.`);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const { user, temp_password } = await usersApi.create({
        ...form,
        project_ids: selectedProjectIds,
      });
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
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in overflow-y-auto max-h-[90vh]">
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
              onChange={(e) => { setForm({ ...form, role: e.target.value as UserRole }); setSelectedProjectIds([]); }}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {ROLES.map((r) => <option key={r} value={r}>{roleLabel[r]}</option>)}
            </select>
            {roleDescription[form.role] && (
              <p className="text-xs text-muted-foreground">{roleDescription[form.role]}</p>
            )}
          </div>

          {needsProject && (
            <div className="border border-border rounded-lg p-3 space-y-2">
              <p className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                <FolderOpen className="w-3.5 h-3.5" />
                Assigned Projects <span className="text-destructive">*</span>
              </p>
              {projects.length === 0 ? (
                <p className="text-xs text-muted-foreground italic">No projects available.</p>
              ) : (
                <div className="space-y-1 max-h-36 overflow-y-auto">
                  {projects.map(p => (
                    <label key={p.id} className="flex items-center gap-2 cursor-pointer text-sm hover:bg-muted/50 rounded px-1 py-0.5">
                      <input
                        type="checkbox"
                        checked={selectedProjectIds.includes(p.id)}
                        onChange={() => toggleProject(p.id)}
                        className="rounded"
                      />
                      <span className="font-mono text-xs text-muted-foreground">{p.code}</span>
                      <span>{p.name}</span>
                    </label>
                  ))}
                </div>
              )}
              {selectedProjectIds.length > 0 && (
                <p className="text-xs text-primary">{selectedProjectIds.length} project{selectedProjectIds.length !== 1 ? "s" : ""} selected</p>
              )}
            </div>
          )}

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

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {
      // Fallback for older browsers / HTTP
      const el = document.createElement("textarea");
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      onClick={handleCopy}
      className="ml-2 p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
      title="Copy to clipboard"
    >
      {copied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
    </button>
  );
}

function TempPwdBanner({ user, password, onDismiss }: TempPwdBannerProps) {
  return (
    <div className="bg-success/10 border border-success/30 rounded-xl p-4 flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-semibold text-success">User created successfully</p>
        <p className="text-sm text-foreground mt-1">
          Share this temporary password with <strong>{user.full_name}</strong>. It will not be shown again.
        </p>
        <div className="mt-2 flex items-center gap-1">
          <p className="font-mono text-sm bg-card border border-border rounded-md px-3 py-1.5 inline-block tracking-wider">
            {password}
          </p>
          <CopyButton text={password} />
        </div>
        <p className="text-xs text-muted-foreground mt-1.5">
          No special characters — easy to type on any device.
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
  projects: Project[];
}

function EditUserModal({ user, onClose, onSaved, projects }: EditModalProps) {
  const [form, setForm] = useState({ full_name: user.full_name, phone: user.phone ?? "", role: user.role });
  const [loading, setLoading] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const [unlockLoading, setUnlockLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [error, setError] = useState("");
  const [tempPwd, setTempPwd] = useState<string | null>(null);
  const [pin, setPin] = useState("");
  const [pinLoading, setPinLoading] = useState(false);
  const [pinMsg, setPinMsg] = useState("");
  const [projectAccess, setProjectAccess] = useState<UserProjectAccess[]>([]);
  const [projectAccessLoading, setProjectAccessLoading] = useState(false);
  const [addingProject, setAddingProject] = useState("");
  const [projectActionLoading, setProjectActionLoading] = useState(false);
  const isLocked = !!(user.locked_until && new Date(user.locked_until) > new Date());
  const showProjectSection = SITE_REQUIRING_ROLES.has(form.role);

  useEffect(() => {
    setProjectAccessLoading(true);
    usersApi.getProjectAccess(user.id)
      .then(setProjectAccess)
      .catch(() => {})
      .finally(() => setProjectAccessLoading(false));
  }, [user.id]);

  const assignedProjectIds = new Set(projectAccess.map(pa => pa.project_id));
  const unassignedProjects = projects.filter(p => !assignedProjectIds.has(p.id));

  const handleAddProject = async () => {
    if (!addingProject) return;
    setProjectActionLoading(true);
    try {
      const access = await usersApi.grantProjectAccess(user.id, addingProject);
      setProjectAccess(prev => [...prev, access]);
      setAddingProject("");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to add project.";
      setError(msg);
    } finally { setProjectActionLoading(false); }
  };

  const handleRemoveProject = async (projectId: string) => {
    setProjectActionLoading(true);
    try {
      await usersApi.revokeProjectAccess(user.id, projectId);
      setProjectAccess(prev => prev.filter(pa => pa.project_id !== projectId));
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to remove project.";
      setError(msg);
    } finally { setProjectActionLoading(false); }
  };

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

  const handleDeleteUser = async () => {
    const confirmed = window.confirm(
      `PERMANENTLY DELETE "${user.full_name}" (${user.email})?\n\n` +
      `This removes the account entirely. It cannot be undone.\n` +
      `The account can be recreated afterwards with a new password.`
    );
    if (!confirmed) return;
    setDeleteLoading(true);
    setError("");
    try {
      await usersApi.deleteUser(user.id);
      onSaved();  // refreshes the list
      onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string; detail?: string } } })
        ?.response?.data?.message
        || (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Failed to delete account.";
      setError(msg);
    } finally { setDeleteLoading(false); }
  };

  const handleUnlockAccount = async () => {
    setUnlockLoading(true);
    setError("");
    try {
      await usersApi.unlockUser(user.id);
      onSaved();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to unlock account.";
      setError(msg);
    } finally { setUnlockLoading(false); }
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

  const handleSetPin = async () => {
    if (!pin || !/^\d{4,6}$/.test(pin)) {
      setPinMsg("PIN must be 4–6 digits.");
      return;
    }
    setPinLoading(true); setPinMsg("");
    try {
      await usersApi.setPin(user.id, pin);
      setPin("");
      setPinMsg("PIN set successfully. Never stored in plain text.");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string; detail?: string } } })?.response?.data?.message
        || (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Failed to set PIN.";
      setPinMsg(msg);
    } finally { setPinLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in overflow-y-auto max-h-[90vh]">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold">Edit User</h2>
          <div className="flex gap-1.5 flex-wrap justify-end">
            {!user.is_active   && <span className="text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">Inactive</span>}
            {user.must_reset_password && <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">Must Reset PW</span>}
            {isLocked && <span className="text-[10px] px-2 py-0.5 rounded-full bg-destructive/10 text-destructive font-medium">Locked</span>}
            {user.failed_login_attempts > 0 && !isLocked && <span className="text-[10px] px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">{user.failed_login_attempts} failed logins</span>}
          </div>
        </div>
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
                <div className="flex items-center gap-1">
                  <p className="font-mono text-sm bg-muted border border-border rounded-md px-3 py-1.5 inline-block tracking-wider">{tempPwd}</p>
                  <CopyButton text={tempPwd} />
                </div>
                <p className="text-xs text-muted-foreground">User will be required to change it on next login. No special characters.</p>
              </div>
            ) : (
              <div className="flex gap-2 flex-wrap">
                <Button type="button" variant="outline" size="sm" onClick={handleResetPassword} disabled={resetLoading}>
                  {resetLoading ? "Resetting…" : "Reset Password"}
                </Button>
                {(isLocked || user.failed_login_attempts > 0) && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleUnlockAccount}
                    disabled={unlockLoading}
                    className="text-green-700 border-green-300 hover:bg-green-50"
                  >
                    {unlockLoading ? "Unlocking…" : "Unlock Account"}
                  </Button>
                )}
              </div>
            )}
          </div>

          {/* Project assignment section — required for site roles */}
          {showProjectSection && (
            <div className="border border-border rounded-lg p-3 space-y-2">
              <p className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                <FolderOpen className="w-3.5 h-3.5" />
                Assigned Projects
                {projectAccess.length === 0 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium ml-1">No project assigned</span>
                )}
              </p>
              {projectAccessLoading ? (
                <div className="h-6 bg-muted/50 rounded animate-pulse" />
              ) : projectAccess.length === 0 ? (
                <p className="text-xs text-muted-foreground italic">No projects assigned yet.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {projectAccess.map(pa => {
                    const proj = projects.find(p => p.id === pa.project_id);
                    return (
                      <span key={pa.id} className="flex items-center gap-1 text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">
                        <span className="font-mono text-[10px]">{proj?.code ?? "—"}</span>
                        {proj?.name ?? pa.project_id.slice(0, 8)}
                        <button
                          type="button"
                          onClick={() => handleRemoveProject(pa.project_id)}
                          disabled={projectActionLoading}
                          className="hover:text-destructive ml-0.5"
                          title="Remove project"
                        >
                          <XIcon className="w-2.5 h-2.5" />
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}
              {unassignedProjects.length > 0 && (
                <div className="flex gap-2 items-center pt-1">
                  <select
                    value={addingProject}
                    onChange={e => setAddingProject(e.target.value)}
                    className="h-8 flex-1 rounded-md border border-input bg-background px-2 text-xs"
                  >
                    <option value="">Add project…</option>
                    {unassignedProjects.map(p => (
                      <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
                    ))}
                  </select>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleAddProject}
                    disabled={!addingProject || projectActionLoading}
                    className="h-8 text-xs"
                  >
                    Add
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* PIN section */}
          <div className="border border-border rounded-lg p-3 space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Device PIN</p>
            <p className="text-xs text-muted-foreground">Set a 4–6 digit PIN for quick device access. Stored bcrypt-hashed, never in plain text.</p>
            <div className="flex gap-2 items-center">
              <Input
                type="password"
                inputMode="numeric"
                pattern="\d{4,6}"
                maxLength={6}
                placeholder="4–6 digits"
                value={pin}
                onChange={(e) => { setPin(e.target.value.replace(/\D/g, "").slice(0, 6)); setPinMsg(""); }}
                className="w-32 font-mono tracking-widest"
              />
              <Button type="button" variant="outline" size="sm" onClick={handleSetPin} disabled={pinLoading}>
                {pinLoading ? "Setting…" : "Set PIN"}
              </Button>
            </div>
            {pinMsg && (
              <p className={`text-xs ${pinMsg.startsWith("PIN set") ? "text-green-700" : "text-destructive"}`}>{pinMsg}</p>
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

          {/* Danger zone — permanent delete */}
          <div className="border-t border-border pt-3 mt-1">
            <p className="text-xs text-muted-foreground mb-2">
              Forgot password / need to recreate? Delete the account and create a new one.
            </p>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              className="w-full"
              onClick={handleDeleteUser}
              disabled={deleteLoading}
            >
              {deleteLoading ? "Deleting…" : "Delete Account Permanently"}
            </Button>
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
  const [projects, setProjects] = useState<Project[]>([]);

  const [error, setError] = useState("");

  // Don't fetch if the user's role doesn't have permission — avoids the 403
  const canAccess = !authLoading && role !== null && ADMIN_ROLES.includes(role);

  useEffect(() => {
    projectsApi.list(1, 100).then(res => setProjects(res.items)).catch(() => {});
  }, []);

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
    if (!confirm("Deactivate this user? They will not be able to log in until reactivated.")) return;
    await usersApi.deactivate(id);
    fetchUsers();
  };

  const handleReactivate = async (id: string) => {
    await usersApi.reactivateUser(id);
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
                    <div className="flex flex-col gap-1">
                      <Badge variant={roleBadgeVariant(u.role)}>{roleLabel[u.role]}</Badge>
                      {SITE_REQUIRING_ROLES.has(u.role) && u.project_access_count === 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium w-fit">No project assigned</span>
                      )}
                    </div>
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
                      {u.is_active ? (
                        <button
                          onClick={() => handleDeactivate(u.id)}
                          className="p-1.5 rounded-md hover:bg-destructive/10 transition-colors text-muted-foreground hover:text-destructive"
                          title="Deactivate account"
                        >
                          <UserX className="w-3.5 h-3.5" />
                        </button>
                      ) : (
                        <button
                          onClick={() => handleReactivate(u.id)}
                          className="p-1.5 rounded-md hover:bg-green-50 transition-colors text-muted-foreground hover:text-green-700"
                          title="Reactivate account"
                        >
                          <ShieldOff className="w-3.5 h-3.5" />
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
          projects={projects}
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
          projects={projects}
          onClose={() => setEditingUser(null)}
          onSaved={() => fetchUsers()}
        />
      )}
    </div>
  );
}
