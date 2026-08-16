import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { alertsApi } from "@/api/alerts";
import { Button } from "@/components/ui/button";

export default function NotificationDeepLinkPage() {
  const { notificationId } = useParams();
  const navigate = useNavigate();
  const [denied, setDenied] = useState(false);
  const [message, setMessage] = useState("Opening notification…");

  useEffect(() => {
    if (!notificationId) { navigate("/alerts", { replace: true }); return; }
    let active = true;
    void (async () => {
      try {
        const alert = await alertsApi.open(notificationId);
        await alertsApi.markRead(notificationId);
        if (active) navigate(alert.action_url || "/alerts", { replace: true });
      } catch (error: unknown) {
        const status = (error as { response?: { status?: number; data?: { detail?: string } } }).response?.status;
        if (status === 403 && active) {
          setDenied(true); setMessage("You do not have permission to open this notification.");
        } else if (status !== 401 && active) {
          setMessage("This notification is unavailable or has expired.");
        }
      }
    })();
    return () => { active = false; };
  }, [navigate, notificationId]);

  return <div className="mx-auto max-w-lg rounded-xl border bg-card p-8 text-center" data-testid={denied ? "notification-forbidden" : "notification-loading"}>
    <h1 className="text-xl font-semibold">{denied ? "Access denied" : "Notification"}</h1>
    <p className="mt-2 text-sm text-muted-foreground">{message}</p>
    {denied && <Button className="mt-5" onClick={() => navigate("/alerts", { replace: true })}>Back to notifications</Button>}
  </div>;
}
