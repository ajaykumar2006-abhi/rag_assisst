/**
 * Decide which documents a question should search.
 *
 * Rules (kept deliberately simple so the UI can state them plainly):
 *   - only documents that finished indexing can be searched;
 *   - an empty selection means "search everything ready";
 *   - selecting every ready document is the same request as no selection, so the
 *     narrower document-scoped route is not used for no reason;
 *   - exactly one document uses the document-scoped endpoint.
 *
 * Returning `ids: null` means "no document filter" to the API.
 */
export interface SearchScope {
  /** Document ids to send, or null to search every indexed document. */
  ids: string[] | null;
  /** Set when the question targets exactly one document. */
  single: string | null;
}

export function resolveSearchScope(
  selection: string[],
  readyIds: string[],
  allIds: string[],
): SearchScope {
  const effective = selection.filter((id) => readyIds.includes(id));
  const target = effective.length > 0 ? effective : readyIds;

  if (target.length === 0) return { ids: [], single: null };
  if (target.length === 1) return { ids: target, single: target[0]! };
  if (target.length === allIds.length) return { ids: null, single: null };
  return { ids: target, single: null };
}
