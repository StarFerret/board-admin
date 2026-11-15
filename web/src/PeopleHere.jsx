import { Badge } from "@/components/ui/badge.jsx";

export default function PeopleHere({ count, people = [] }) {
  const names = [...new Set(people.filter(Boolean))];
  const n = count || names.length || 0;

  return (
    <span className="group relative inline-flex">
      <Badge variant="secondary" className="cursor-default">
        {n} here
      </Badge>
      <span className="invisible absolute right-0 top-full z-30 mt-1 min-w-[9rem] rounded-md border bg-popover p-2 text-xs text-popover-foreground shadow-md group-hover:visible">
        <span className="mb-1 block font-medium text-muted-foreground">Here now</span>
        {names.length === 0 ? (
          <span className="block">Just you</span>
        ) : (
          names.map((name) => (
            <span key={name} className="block truncate py-0.5">
              {name}
            </span>
          ))
        )}
      </span>
    </span>
  );
}
