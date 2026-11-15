import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merges Tailwind CSS classes using shadcn/ui's cn utility pattern
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}