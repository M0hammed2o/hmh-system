import { useState } from "react";
import { Bell, Shield, Database, Info, Layers, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/shared/PageHeader";
import client from "@/api/client";

function Section({ title, icon: Icon, children }: { title: string; icon: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <Icon className="w-4 h-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const [seedingStages, setSeedingStages] = useState(false);
  const [stagesDone, setStagesDone] = useState(false);
  const [stagesError, setStagesError] = useState("");

  const handleSeedStages = async () => {
    setSeedingStages(true);
    setStagesError("");
    try {
      const res = await client.post<{ data: unknown[]; message: string }>("/stages/seed");
      setStagesDone(true);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to seed stages.";
      setStagesError(msg);
    } finally { setSeedingStages(false); }
  };

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Settings"
        description="System configuration, alert thresholds, and account preferences."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Stages */}
        <Section title="Construction Stages" icon={Layers}>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Seed the 10 default construction stages (Foundation → Handover) if the stage list is empty.
              This runs automatically on startup, but you can re-run it here.
            </p>
            <div className="flex items-center gap-3">
              <Button size="sm" variant="outline" onClick={handleSeedStages} disabled={seedingStages}>
                {seedingStages ? "Seeding…" : "Seed Default Stages"}
              </Button>
              {stagesDone && (
                <span className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1">
                  <Check className="w-3.5 h-3.5" />Stages seeded
                </span>
              )}
            </div>
            {stagesError && <p className="text-sm text-destructive">{stagesError}</p>}
          </div>
        </Section>

        {/* Alert Thresholds */}
        <Section title="Alert Thresholds" icon={Bell}>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Low Stock Threshold (%)</Label>
              <Input type="number" defaultValue={20} min={1} max={100} className="max-w-[160px]" />
              <p className="text-xs text-muted-foreground">
                Alert fires when balance falls below this % of original planned quantity.
              </p>
            </div>
            <div className="space-y-2">
              <Label>BOQ Variance Alert (%)</Label>
              <Input type="number" defaultValue={10} min={1} max={100} className="max-w-[160px]" />
              <p className="text-xs text-muted-foreground">
                Alert fires when actual usage exceeds planned by this percentage.
              </p>
            </div>
            <div className="space-y-2">
              <Label>Pending MR Alert (days)</Label>
              <Input type="number" defaultValue={5} min={1} max={30} className="max-w-[160px]" />
              <p className="text-xs text-muted-foreground">
                Alert fires when a material request sits in SUBMITTED status for this many days.
              </p>
            </div>
            <Button size="sm" variant="outline">Save Thresholds</Button>
          </div>
        </Section>

        {/* System Info */}
        <Section title="System Information" icon={Info}>
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between py-2 border-b border-border">
              <span className="text-muted-foreground">System Version</span>
              <span className="font-mono text-xs">HMH V1.0.0</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-border">
              <span className="text-muted-foreground">Environment</span>
              <span className="font-mono text-xs">Development</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-border">
              <span className="text-muted-foreground">VAT Rate (V1)</span>
              <span className="font-mono text-xs">15% (VAT-inclusive pricing)</span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-muted-foreground">Schema Version</span>
              <span className="font-mono text-xs">hmh_v1</span>
            </div>
          </div>
        </Section>

        {/* Security */}
        <Section title="Security" icon={Shield}>
          <div className="space-y-4 text-sm">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Account Lockout</p>
                <p className="text-xs text-muted-foreground mt-0.5">Lock account after 5 failed login attempts</p>
              </div>
              <Badge className="text-xs font-mono bg-success/10 text-success border border-success/20">Enabled</Badge>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Lockout Duration</p>
                <p className="text-xs text-muted-foreground mt-0.5">Duration an account remains locked</p>
              </div>
              <span className="text-sm font-medium">30 minutes</span>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Force Password Reset</p>
                <p className="text-xs text-muted-foreground mt-0.5">New users must reset their temporary password</p>
              </div>
              <Badge className="text-xs bg-success/10 text-success border border-success/20">Enabled</Badge>
            </div>
          </div>
        </Section>

        {/* Data */}
        <Section title="Data & Storage" icon={Database}>
          <div className="space-y-3 text-sm">
            <div className="bg-muted/50 rounded-lg p-3">
              <p className="text-xs font-medium text-muted-foreground mb-1">Stock Ledger Policy</p>
              <p className="text-xs">
                Stock balances are computed from an immutable delivery ledger. Records cannot be manually edited — all changes must go through new delivery entries.
              </p>
            </div>
            <div className="bg-muted/50 rounded-lg p-3">
              <p className="text-xs font-medium text-muted-foreground mb-1">Backup</p>
              <p className="text-xs text-muted-foreground">
                Database backups are managed at the infrastructure level. Contact your system administrator for backup configuration.
              </p>
            </div>
          </div>
        </Section>
      </div>
    </div>
  );
}
