import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { TOKEN_KEY, REFRESH_TOKEN_KEY, ROLE_KEY } from "@/lib/constants";
import { useAuthContext } from "@/context/AuthContext";
import { landingForRole, safeReturnTo } from "@/routes/authNavigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { HMHLogo } from "@/components/HMHLogo";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user: currentUser, loading: sessionLoading, refresh } = useAuthContext();
  const requestedPath = safeReturnTo(location.search);
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  useEffect(() => {
    if (!sessionLoading && currentUser) {
      navigate(landingForRole(currentUser.role, requestedPath), { replace: true });
    }
  }, [currentUser, navigate, requestedPath, sessionLoading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await authApi.login({ email, password });
      localStorage.setItem(TOKEN_KEY, res.access_token);
      localStorage.setItem(REFRESH_TOKEN_KEY, res.refresh_token);

      if (res.must_reset_password) {
        const query = requestedPath ? `?returnTo=${encodeURIComponent(requestedPath)}` : "";
        navigate(`/set-password${query}`, { replace: true });
        return;
      }

      const user = await refresh();
      if (!user) throw new Error("Authenticated session could not be verified.");
      navigate(landingForRole(user.role, requestedPath), { replace: true });
    } catch {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(ROLE_KEY);
      setError("Invalid email or password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="flex flex-col items-center mb-8">
          <HMHLogo size="lg" className="mb-4" />
          <p className="text-sm text-muted-foreground mt-1">Sign in to the management portal</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email address</Label>
            <Input
              id="email"
              type="email"
              placeholder="admin@hmhgroup.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              disabled={loading}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={loading}
            />
          </div>

          {error && (
            <div className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <div className="mt-6 text-center">
          <Link to="/site-login" className="text-sm text-muted-foreground hover:text-primary underline underline-offset-2">
            Go to Site Dashboard →
          </Link>
        </div>
      </div>
    </div>
  );
}
