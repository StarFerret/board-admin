import { Badge } from "@/components/ui/badge.jsx";

export default function WorkState({ status }) {
  if (status === "running") {
    return (
      <Badge variant="success">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
        Working
      </Badge>
    );
  }
  if (status === "error") return <Badge variant="outline">Paused</Badge>;
  return <Badge variant="outline">Idle</Badge>;
}
