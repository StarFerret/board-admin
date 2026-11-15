import { useEffect, useRef } from "react";
import { io } from "socket.io-client";

export function useAgentSocket(agentId, handlers, workspaceId, visitorName) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!visitorName?.trim()) return undefined;
    const socket = io(window.location.origin, {
      transports: ["polling", "websocket"],
      reconnectionAttempts: 8,
      timeout: 20000,
    });
    socket.emit("join", {
      id: agentId || null,
      workspace: workspaceId || null,
      name: visitorName.trim(),
    });
    const events = [
      "token",
      "message",
      "tool",
      "status",
      "files",
      "agent",
      "agent_deleted",
      "workspace",
      "workspace_deleted",
      "error",
      "presence",
      "thinking",
      "goal",
      "schedules",
      "ollama_model",
      "board_name",
    ];
    for (const event of events) {
      socket.on(event, (payload) => {
        const fn = handlersRef.current[event];
        if (fn) fn(payload);
      });
    }

    return () => {
      if (agentId) socket.emit("leave", { id: agentId });
      socket.close();
    };
  }, [agentId, workspaceId, visitorName]);
}