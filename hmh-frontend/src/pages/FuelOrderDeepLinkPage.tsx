import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

export default function FuelOrderDeepLinkPage() {
  const { orderId } = useParams();
  const navigate = useNavigate();
  useEffect(() => navigate(`/fuel-management/orders?order=${orderId || ""}`, { replace: true }), [navigate, orderId]);
  return <p className="p-6 text-sm text-muted-foreground">Opening fuel request…</p>;
}
