import { Button } from "@/components/ui/button.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";

export default function ShareSheet({ open, title, url, note, copied, onCopy, onClose }) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <Card
        className="w-full max-w-md shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">{title || "Share"}</CardTitle>
          <CardDescription>
            {note || "Anyone who can reach this StarFerret server can open the link."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs break-all">
            {url}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={onCopy}>
              {copied ? "Copied" : "Copy link"}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              Close
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
