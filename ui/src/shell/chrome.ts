/**
 * Placeholder chrome: there is no production, shoot-day, or user model in
 * the schema, and /chat is deliberately unauthenticated. This constant is
 * the single source for the breadcrumb and avatar copy so it reads as
 * decorative chrome rather than a fabricated auth/production concept.
 */
export const PLACEHOLDER_CHROME = {
  breadcrumb: ["GHOST MACHINE", "DAY 14", "2026-08-12"],
  userInitials: "AR",
  userName: "A. Reyes",
  userRole: "ASSISTANT EDITOR",
} as const;
