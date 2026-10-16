/**
 * Downloading a report and handing it to the share sheet (PRD 7, ss33-35, 52).
 *
 * The whole export path, in one place:
 *
 *     authenticated download -> app-private cache -> native share sheet
 *
 * Four decisions worth reading.
 *
 * **The download is authenticated, not a URL.** The file comes from the API route
 * with a bearer token attached, because there is no public or signed URL for a
 * report and PRD 7 section 52 rules both out. `reportPdfSource` hands back the
 * URL and the token together; nothing here builds either.
 *
 * **The file lands in app-private cache storage** (PRD 7, section 35). Cache
 * rather than documents: an exported PDF is a copy of something the backend still
 * holds, so the OS reclaiming it costs nothing, and a directory the system may
 * empty is the right home for a health document the user has finished with.
 *
 * **Old exports are cleaned up.** Every export removes previous files from the
 * directory first, so the phone never accumulates a folder of doctor summaries
 * (PRD 7, section 35's "cleaned up where practical").
 *
 * **Nothing is claimed before it happens.** A failed download is reported as a
 * failure. PRD 7 section 53 asks for exactly this -- no pretending an export
 * worked -- and the caller shows what went wrong rather than a share sheet with
 * nothing in it.
 *
 * **Not verified on a device.** `expo-file-system` and `expo-sharing` have no
 * implementation under Jest, so the tests cover the decisions in this file with
 * both replaced. No report PDF has been shared from a phone.
 */
import { Directory, File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';

import { ApiError } from '../../services/api/errors';
import { createLogger } from '../../utils/logger';
import { reportPdfSource } from './api';
import type { AppointmentReport } from './types';

const log = createLogger('appointments');

/** Where exports go, inside the app's own cache directory. */
export const EXPORT_DIRECTORY = 'nura-reports';

export interface ExportedReport {
  /** A `file://` URI in app-private cache storage. */
  uri: string;
  fileName: string;
}

function exportDirectory(): Directory {
  return new Directory(Paths.cache, EXPORT_DIRECTORY);
}

/**
 * Empties the export directory.
 *
 * Called before each export and after each share, so at most one report is on
 * the phone at a time. Failures are swallowed: being unable to tidy up must not
 * stop somebody exporting the document they asked for.
 */
export async function clearExports(): Promise<void> {
  try {
    const directory = exportDirectory();
    if (!directory.exists) return;
    for (const entry of directory.list()) {
      try {
        entry.delete();
      } catch {
        // Locked, or already gone.
      }
    }
  } catch {
    // Nothing to clean, or no cache directory on this platform.
  }
}

/**
 * Downloads a report's PDF into app-private cache storage.
 *
 * Throws an `ApiError` when the app is signed out or the download fails, so the
 * caller can say which happened rather than showing an empty share sheet.
 */
export async function downloadReport(
  profileId: string,
  appointmentId: string,
  report: AppointmentReport
): Promise<ExportedReport> {
  const source = await reportPdfSource(profileId, appointmentId, report.id);
  if (source === null) {
    throw new ApiError('unauthorized', 'Sign in again to export this summary.');
  }

  await clearExports();

  const directory = exportDirectory();
  if (!directory.exists) {
    directory.create({ intermediates: true });
  }

  try {
    const file = await File.downloadFileAsync(
      source.uri,
      new File(directory, report.fileName),
      { headers: source.headers, idempotent: true }
    );
    // A count, never the filename: a report's name carries a date, and the
    // fewer places it appears the better (PRD 7, section 57).
    log.info('report downloaded for export');
    return { uri: file.uri, fileName: report.fileName };
  } catch (cause) {
    log.warn('report download failed');
    throw new ApiError('unavailable', 'That summary could not be downloaded.', {
      cause,
    });
  }
}

/**
 * Hands a downloaded file to the platform's own share sheet (PRD 7, section 34).
 *
 * Where it goes from there is the user's choice: Files, email, messaging,
 * AirDrop, a printer. Nura does not send it anywhere itself, and PRD 7 section 34
 * rules out sending it to a doctor directly.
 *
 * Returns false when the platform has no share sheet, which the caller reports
 * as "saved to this phone" rather than as a failure -- the file is real either
 * way.
 */
export async function shareReport(exported: ExportedReport): Promise<boolean> {
  try {
    if (!(await Sharing.isAvailableAsync())) return false;
    await Sharing.shareAsync(exported.uri, {
      mimeType: 'application/pdf',
      UTI: 'com.adobe.pdf',
      dialogTitle: 'Share your Nura health summary',
    });
    return true;
  } catch {
    // The user dismissing the sheet arrives here on some platforms, and that is
    // not an error worth reporting as one.
    return false;
  }
}

export interface ExportOutcome {
  uri: string;
  fileName: string;
  /** False when the platform offered no share sheet; the file still exists. */
  shared: boolean;
}

/**
 * Download, then share. The one call a screen makes.
 *
 * Deliberately not automatic anywhere: PRD 7 section 13 ends its sequence at
 * "Export / Share" with no automatic export, so this runs only when somebody
 * presses the button.
 */
export async function exportAndShareReport(
  profileId: string,
  appointmentId: string,
  report: AppointmentReport
): Promise<ExportOutcome> {
  const exported = await downloadReport(profileId, appointmentId, report);
  const shared = await shareReport(exported);
  return { ...exported, shared };
}
