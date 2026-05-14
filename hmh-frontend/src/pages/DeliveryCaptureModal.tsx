/**
 * Delivery capture modal — photo, manual form, and signature.
 * Used inside DeliveriesPage when the site manager taps "Capture".
 */
import { useRef, useState } from "react";
import { Camera, Pen, Upload, CheckCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import client from "@/api/client";

interface Props {
  deliveryId: string;
  onClose: () => void;
  onCaptured: () => void;
}

export function DeliveryCaptureModal({ deliveryId, onClose, onCaptured }: Props) {
  const [deliveryNoteImage, setDeliveryNoteImage] = useState<File | null>(null);
  const [signatureImage, setSignatureImage] = useState<File | null>(null);
  const [receiverName, setReceiverName] = useState("");
  const [deliveryNoteNumber, setDeliveryNoteNumber] = useState("");
  const [comments, setComments] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const noteInputRef = useRef<HTMLInputElement>(null);
  const sigInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      if (deliveryNoteImage) formData.append("delivery_note_image", deliveryNoteImage);
      if (signatureImage) formData.append("signature_image", signatureImage);
      if (receiverName) formData.append("receiver_name", receiverName);
      if (deliveryNoteNumber) formData.append("supplier_delivery_note_number", deliveryNoteNumber);
      if (comments) formData.append("comments", comments);

      await client.post(`/deliveries/${deliveryId}/capture`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setDone(true);
      setTimeout(() => { onCaptured(); onClose(); }, 1200);
    } catch {
      setError("Failed to save delivery capture. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
        <div className="bg-card border border-border rounded-2xl p-8 text-center max-w-sm w-full">
          <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-3" />
          <p className="font-semibold">Delivery captured!</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-t-2xl sm:rounded-2xl w-full sm:max-w-md max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-border">
          <h2 className="text-base font-semibold">Capture Delivery</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {/* Delivery note photo */}
          <div className="space-y-2">
            <Label>Delivery Note Photo</Label>
            <input
              ref={noteInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => setDeliveryNoteImage(e.target.files?.[0] || null)}
            />
            <button
              type="button"
              onClick={() => noteInputRef.current?.click()}
              className="w-full border-2 border-dashed border-border rounded-xl p-4 flex flex-col items-center gap-2 hover:bg-muted/50 transition-colors"
            >
              {deliveryNoteImage ? (
                <>
                  <CheckCircle className="w-6 h-6 text-green-500" />
                  <span className="text-sm font-medium text-green-600 dark:text-green-400">{deliveryNoteImage.name}</span>
                </>
              ) : (
                <>
                  <Camera className="w-6 h-6 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">Take photo of delivery note</span>
                </>
              )}
            </button>
          </div>

          {/* Receiver signature */}
          <div className="space-y-2">
            <Label>Signature</Label>
            <input
              ref={sigInputRef}
              type="file"
              accept="image/*"
              capture="user"
              className="hidden"
              onChange={(e) => setSignatureImage(e.target.files?.[0] || null)}
            />
            <button
              type="button"
              onClick={() => sigInputRef.current?.click()}
              className="w-full border-2 border-dashed border-border rounded-xl p-4 flex flex-col items-center gap-2 hover:bg-muted/50 transition-colors"
            >
              {signatureImage ? (
                <>
                  <CheckCircle className="w-6 h-6 text-green-500" />
                  <span className="text-sm font-medium text-green-600 dark:text-green-400">Signature captured</span>
                </>
              ) : (
                <>
                  <Pen className="w-6 h-6 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">Capture signature photo</span>
                </>
              )}
            </button>
          </div>

          {/* Manual fields */}
          <div className="space-y-2">
            <Label>Receiver Name</Label>
            <Input
              value={receiverName}
              onChange={(e) => setReceiverName(e.target.value)}
              placeholder="Name of person receiving"
            />
          </div>

          <div className="space-y-2">
            <Label>Supplier Delivery Note Number</Label>
            <Input
              value={deliveryNoteNumber}
              onChange={(e) => setDeliveryNoteNumber(e.target.value)}
              placeholder="e.g. DN-12345"
            />
          </div>

          <div className="space-y-2">
            <Label>Comments (optional)</Label>
            <Input
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Any notes about the delivery"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading} className="flex-1">
              <Upload className="w-4 h-4 mr-1" />
              {loading ? "Saving…" : "Save Capture"}
            </Button>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
