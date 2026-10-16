/**
 * "You're offline" (PRD 3, sections 26 and 30; PRD 13, section 34).
 *
 * States a fact and stops. The app still works offline -- cached information
 * is shown, and a check-in is saved on the phone -- so this is not a warning,
 * an error, or a reason to block anything.
 *
 * PRD 13 generalised it. The rendering, the live region and the wording now
 * live in `DegradedModeBanner`, which can also say the two things this could
 * not: that the server is unreachable while the phone is online, and that a
 * robot is offline while the app is fine. This name stays because ten screens
 * import it and "offline" is what they mean.
 */
import { DegradedModeBanner } from '../DegradedModeBanner';

export function OfflineBanner() {
  return <DegradedModeBanner kind="offline" />;
}
