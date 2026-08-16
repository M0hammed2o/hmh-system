import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { HardHat, KeyRound } from "lucide-react";
import { authApi } from "@/api/auth";
import { TOKEN_KEY, REFRESH_TOKEN_KEY, ROLE_KEY } from "@/lib/constants";
import { useAuthContext } from "@/context/AuthContext";
import { landingForRole, safeReturnTo } from "@/routes/authNavigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function SetPasswordPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { refresh } = useAuthContext();
  const requestedPath = safeReturnTo(location.search);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await authApi.changePassword(currentPassword, newPassword);

      // Determine where to redirect based on role
      const user = await refresh();
      if (!user) throw new Error("Updated session could not be verified.");
      navigate(landingForRole(user.role, requestedPath), { replace: true });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        "Failed to update password. Check your current password and try again.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(ROLE_KEY);
    window.location.href = "/login";
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm animate-fade-in">

        {/* Logo + branding */}
        <div className="flex flex-col items-center mb-8">
          <div className="flex items-center justify-center w-16 h-16 rounded-3xl bg-primary/10 mb-4">
            <HardHat className="w-8 h-8 text-primary" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">Set Your Password</h1>
          <p className="text-sm text-muted-foreground mt-1 text-center">
            Your account requires a password change before you can continue.
          </p>
        </div>

        {/* Info banner */}
        <div className="mb-5 bg-warning/10 border border-warning/30 rounded-xl p-4 flex gap-3">
          <KeyRound className="w-4 h-4 text-warning shrink-0 mt-0.5" />
          <p className="text-xs text-muted-foreground">
            You were assigned a temporary password. Please set a new permanent password to continue.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="current-password">Temporary Password</Label>
            <Input
              id="current-password"
              type="password"
              placeholder="Enter your temporary password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              autoFocus
              className="h-11 text-base"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-password">New Password</Label>
            <Input
              id="new-password"
              type="password"
              placeholder="At least 8 characters"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              className="h-11 text-base"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm-password">Confirm New Password</Label>
            <Input
              id="confirm-password"
              type="password"
              placeholder="Repeat your new password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="h-11 text-base"
            />
          </div>

          {error && (
            <div className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full h-12 text-base" disabled={loading}>
            {loading ? "Updating…" : "Set New Password"}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          Wrong account?{" "}
          <button
            onClick={handleLogout}
            className="text-primary hover:underline font-medium"
          >
            Sign out
          </button>
        </p>
      </div>
    </div>
  );
}
