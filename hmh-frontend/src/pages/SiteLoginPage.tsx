import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { HardHat, ArrowRight } from "lucide-react";
import { authApi } from "@/api/auth";
import { usersApi } from "@/api/users";
import { TOKEN_KEY, REFRESH_TOKEN_KEY } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SITE_ROLES } from "@/routes/SiteRoute";

export default function SiteLoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [accessDenied, setAccessDenied] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setAccessDenied(false);
    setLoading(true);
    try {
      // 1. Authenticate with the shared backend
      const tokens = await authApi.login({ email, password });
      localStorage.setItem(TOKEN_KEY, tokens.access_token);
      localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);

      // 2. Check if password reset is required first
      if (tokens.must_reset_password) {
        navigate("/set-password", { replace: true });
        return;
      }

      // 3. Fetch the user's role to decide where to send them
      const user = await usersApi.me();

      if (SITE_ROLES.includes(user.role)) {
        // Site manager or site staff → site dashboard
        navigate("/site", { replace: true });
      } else {
        // Office / owner role tried to log in via the site portal
        // Keep their token (it's valid) but tell them to use the right portal
        setAccessDenied(true);
      }
    } catch (err: unknown) {
      // Clear any partial token on auth failure
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        "Login failed. Check your credentials.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm animate-fade-in">

        {/* Logo + branding */}
        <div className="flex flex-col items-center mb-8">
          <div className="flex items-center justify-center w-16 h-16 rounded-3xl bg-warning/15 mb-4">
            <HardHat className="w-8 h-8 text-warning" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">HMH Site Portal</h1>
          <p className="text-sm text-muted-foreground mt-1 text-center">
            For site managers and site staff only
          </p>
        </div>

        {/* Access denied — wrong role */}
        {accessDenied && (
          <div className="mb-5 bg-warning/10 border border-warning/30 rounded-xl p-4 space-y-3">
            <p className="text-sm font-semibold text-warning">Site portal access only</p>
            <p className="text-xs text-muted-foreground">
              Your account is set up for office or management access. This portal is reserved
              for site managers and site staff.
            </p>
            <Link
              to="/"
              className="flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
            >
              Go to the office dashboard
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        )}

        {/* Login form */}
        {!accessDenied && (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="site-email">Email address</Label>
              <Input
                id="site-email"
                type="email"
                placeholder="site.manager@hmhgroup.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                className="h-11 text-base"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="site-password">Password</Label>
              <Input
                id="site-password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
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
              {loading ? "Signing in…" : "Sign in to Site Portal"}
            </Button>
          </form>
        )}

        {/* Link to office portal */}
        <p className="mt-6 text-center text-xs text-muted-foreground">
          Office or management access?{" "}
          <Link to="/login" className="text-primary hover:underline font-medium">
            Use the office portal
          </Link>
        </p>
      </div>
    </div>
  );
}
