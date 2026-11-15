import { useState } from "react";
import { Button } from "@/components/ui/button.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import { Input } from "@/components/ui/input.jsx";

export default function NameGate({ onDone }) {
  const [name, setName] = useState("");

  function submit(e) {
    e.preventDefault();
    const cleaned = name.trim();
    if (!cleaned) return;
    onDone(cleaned.slice(0, 40));
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">StarFerret</CardTitle>
          <CardDescription>Type your name so others on this link know who sent each message.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={submit}>
            <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" maxLength={40} />
            <Button className="w-full" type="submit">Join</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
