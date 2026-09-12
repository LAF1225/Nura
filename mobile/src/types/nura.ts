/**
 * Nura assistant modes (PRD 0, section 34).
 *
 * Declared now so later PRDs share one vocabulary. PRD 0 deliberately attaches
 * no behaviour to these values -- nothing reads or switches on them yet.
 */
export type NuraMode = 'normal' | 'focus' | 'sleep' | 'privacy' | 'safety' | 'emergency';
