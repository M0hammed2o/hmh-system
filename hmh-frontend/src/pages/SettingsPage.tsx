// TEMPORARY MOCK UNTIL BACKEND ROUTE EXISTS
import { Bell, Shield, Database, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/shared/PageHeader";

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
  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Settings"
        description="System configuration, alert thresholds, and account preferences."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
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
