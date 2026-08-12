export function stableWearConfirmationId(
  recommendationId: string,
  optionId: string,
  existingId?: string,
): string {
  if (existingId) {
    return existingId;
  }
  const random =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${recommendationId}:${optionId}:${random}`;
}
