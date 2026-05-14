import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { authApi } from "@/api/auth";
import { usersApi } from "@/api/users";
import { TOKEN_KEY, REFRESH_TOKEN_KEY, ROLE_KEY, SITE_ROLE_SET } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { HMHLogo } from "@/components/HMHLogo";

export default function SiteLoginPage() {
  const navigate = useNavigate();
  const [loginMode, setLoginMode]       = useState<"email" | "phone">("email");
  const [email, setEmail]               = useState("");
  const [password, setPassword]         = useState("");
  const [phone, setPhone]               = useState("");
  const [pin, setPin]                   = useState("");
  const [error, setError]               = useState("");
  const [accessDenied, setAccessDenied] = useState(false);
  const [loading, setLoading]           = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setAccessDenied(false);
    setLoading(true);
    // For phone mode, send phone number as the "email" field — backend checks both
    const loginEmail    = loginMode === "phone" ? phone.trim() : email.trim();
    const loginPassword = loginMode === "phone" ? pin.trim()   : password;
    try {
      const tokens = await authApi.login({ email: loginEmail, password: loginPassword });
      localStorage.setItem(TOKEN_KEY, tokens.access_token);
      localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);

      if (tokens.must_reset_password) {
        navigate("/set-password", { replace: true });
        return;
      }

      const user = await usersApi.me();
      localStorage.setItem(ROLE_KEY, user.role);

      if (SITE_ROLE_SET.has(user.role)) {
        navigate("/site", { replace: true });
      } else {
        // Office/owner tried the site portal — keep their valid token but show the message
        setAccessDenied(true);
      }
    } catch {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(ROLE_KEY);
      setError(loginMode === "phone" ? "Invalid phone number or PIN." : "Invalid email or password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm animate-fade-in">

        {/* Logo + branding */}
        <div className="flex flex-col items-center mb-8">
          <HMHLogo size="lg" className="mb-3" />
          <p className="text-base font-semibold tracking-tight text-foreground">Site Portal</p>
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
            {/* Mode tabs */}
            <div className="flex gap-1 bg-muted/50 p-1 rounded-lg text-sm">
              <button type="button" onClick={() => { setLoginMode("email"); setError(""); }}
                className={`flex-1 py-1.5 rounded-md font-medium transition-colors ${loginMode === "email" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                Email / Password
              </button>
              <button type="button" onClick={() => { setLoginMode("phone"); setError(""); }}
                className={`flex-1 py-1.5 rounded-md font-medium transition-colors ${loginMode === "phone" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                Phone / PIN
              </button>
            </div>
            {loginMode === "email" ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="site-email">Email address</Label>
                  <Input id="site-email" type="email" placeholder="site.manager@hmhgroup.com"
                    value={email} onChange={(e) => setEmail(e.target.value)}
                    required autoFocus disabled={loading} className="h-11 text-base" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="site-password">Password</Label>
                  <Input id="site-password" type="password" placeholder="••••••••"
                    value={password} onChange={(e) => setPassword(e.target.value)}
                    required disabled={loading} className="h-11 text-base" />
                </div>
              </>
            ) : (
              <>
                <div className="space-y-2">
                  <Label htmlFor="site-phone">Phone number</Label>
                  <Input id="site-phone" type="tel" placeholder="0831234567"
                    value={phone} onChange={(e) => setPhone(e.target.value)}
                    required autoFocus disabled={loading} className="h-11 text-base" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="site-pin">PIN</Label>
                  <Input id="site-pin" type="password" placeholder="••••" maxLength={12}
                    value={pin} onChange={(e) => setPin(e.target.value)}
                    required disabled={loading} className="h-11 text-base tracking-widest" />
                  <p className="text-xs text-muted-foreground">Enter your site access PIN.</p>
                </div>
              </>
            )}

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
