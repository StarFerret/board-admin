import { createContext, useContext } from "react";

export const VisitorContext = createContext("");

export function useVisitorName() {
  return useContext(VisitorContext);
}
