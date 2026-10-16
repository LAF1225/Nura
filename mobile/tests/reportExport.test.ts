/**
 * Downloading a report and handing it to the share sheet (PRD 7, ss33-35, 52).
 *
 * `expo-file-system` and `expo-sharing` are replaced by recording stubs, so these
 * tests exercise the real decisions -- authenticated download, app-private cache,
 * cleanup, and what happens when there is no share sheet -- without a filesystem
 * or an OS share dialog underneath.
 *
 * What is *not* claimed anywhere here: that a report PDF has ever been shared from
 * a phone. That needs a device, and the README says so.
 */
import { parseReport } from '../src/features/appointments/api';
import {
  clearExports,
  downloadReport,
  EXPORT_DIRECTORY,
  exportAndShareReport,
  shareReport,
} from '../src/features/appointments/reportExport';
import { setAuthTokenProvider } from '../src/services/api/client';
import { mockBackend, reportFixture, signInAt } from './helpers';

// `jest.mock` is hoisted above every import, so the stubs are in place before
// the module under test is loaded even though they are written below them.
const downloads: { url: string; destination: string; options: any }[] = [];
const deleted: string[] = [];
const shares: { uri: string; options: any }[] = [];
const state = {
  downloadFails: false,
  sharingAvailable: true,
  directoryExists: false,
  existingFiles: [] as string[],
};

jest.mock('expo-file-system', () => {
  class FakeDirectory {
    uri: string;
    constructor(...parts: unknown[]) {
      this.uri = parts.map((part) => String((part as any)?.uri ?? part)).join('/');
    }
    get exists() {
      return state.directoryExists;
    }
    create() {
      state.directoryExists = true;
    }
    list() {
      return state.existingFiles.map((name) => ({
        uri: `${this.uri}/${name}`,
        delete: () => deleted.push(name),
      }));
    }
  }

  class FakeFile {
    uri: string;
    constructor(...parts: unknown[]) {
      this.uri = parts.map((part) => String((part as any)?.uri ?? part)).join('/');
    }
    static downloadFileAsync = async (
      url: string,
      destination: { uri: string },
      options: unknown
    ) => {
      if (state.downloadFails) throw new Error('network');
      downloads.push({ url, destination: destination.uri, options });
      return destination;
    };
  }

  return {
    Directory: FakeDirectory,
    File: FakeFile,
    Paths: { cache: { uri: 'file:///cache' } },
  };
});

jest.mock('expo-sharing', () => ({
  isAvailableAsync: async () => state.sharingAvailable,
  shareAsync: async (uri: string, options: unknown) => {
    shares.push({ uri, options });
  },
}));

const PROFILE = 'profile-1';
const report = parseReport(reportFixture(), '/reports');

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  downloads.length = 0;
  deleted.length = 0;
  shares.length = 0;
  state.downloadFails = false;
  state.sharingAvailable = true;
  state.directoryExists = false;
  state.existingFiles = [];
  signInAt('onboarding_complete');
  // `mediaSource` needs a bearer token, which the real app registers at
  // startup from the Supabase session.
  setAuthTokenProvider(async () => 'test-token');
  backend = mockBackend();
});

afterEach(() => backend.restore());

describe('downloading', () => {
  it('fetches the authenticated path with a bearer token', async () => {
    const exported = await downloadReport(PROFILE, 'appointment-1', report);

    expect(downloads.length).toBe(1);
    const call = downloads[0]!;
    expect(call.url).toContain(
      `/api/v1/profiles/${PROFILE}/appointments/appointment-1/reports/report-1/pdf`
    );
    expect(String(call.options.headers.Authorization)).toMatch(/^Bearer /);
    expect(exported.fileName).toBe('Nura_Health_Summary_2026-09-28.pdf');
  });

  it('puts the file in app-private cache storage, not documents', () => {
    // PRD 7 section 35: a copy of something the backend still holds belongs
    // somewhere the OS may reclaim.
    expect(EXPORT_DIRECTORY).toBe('nura-reports');
  });

  it('writes under the cache directory with the safe filename', async () => {
    const exported = await downloadReport(PROFILE, 'appointment-1', report);

    expect(exported.uri).toContain('file:///cache');
    expect(exported.uri).toContain(EXPORT_DIRECTORY);
    expect(exported.uri).toContain('Nura_Health_Summary_2026-09-28.pdf');
    // Nothing medical in the name (PRD 7, section 33).
    for (const word of ['headache', 'symptom', 'cardiology', 'metformin']) {
      expect(exported.uri.toLowerCase()).not.toContain(word);
    }
  });

  it('clears earlier exports first', async () => {
    state.directoryExists = true;
    state.existingFiles = ['Nura_Health_Summary_2026-09-01.pdf'];

    await downloadReport(PROFILE, 'appointment-1', report);

    expect(deleted).toEqual(['Nura_Health_Summary_2026-09-01.pdf']);
  });

  it('creates the directory when it is not there yet', async () => {
    expect(state.directoryExists).toBe(false);
    await downloadReport(PROFILE, 'appointment-1', report);
    expect(state.directoryExists).toBe(true);
  });

  it('refuses when signed out rather than downloading nothing', async () => {
    setAuthTokenProvider(async () => null);
    await expect(downloadReport(PROFILE, 'appointment-1', report)).rejects.toThrow(
      /Sign in again/
    );
    expect(downloads).toEqual([]);
  });

  it('reports a failed download as a failure', async () => {
    // PRD 7 section 53: nothing is claimed before it happens.
    state.downloadFails = true;
    await expect(downloadReport(PROFILE, 'appointment-1', report)).rejects.toThrow(
      /could not be downloaded/
    );
  });

  it('tidying up never throws', async () => {
    state.directoryExists = false;
    await expect(clearExports()).resolves.toBeUndefined();
  });
});

describe('sharing', () => {
  it('hands the file to the platform share sheet as a PDF', async () => {
    const shared = await shareReport({
      uri: 'file:///cache/nura-reports/report.pdf',
      fileName: 'report.pdf',
    });

    expect(shared).toBe(true);
    expect(shares[0]?.uri).toBe('file:///cache/nura-reports/report.pdf');
    expect(shares[0]?.options.mimeType).toBe('application/pdf');
  });

  it('says so, rather than failing, when there is no share sheet', async () => {
    state.sharingAvailable = false;
    const shared = await shareReport({
      uri: 'file:///cache/nura-reports/report.pdf',
      fileName: 'report.pdf',
    });

    expect(shared).toBe(false);
    expect(shares).toEqual([]);
  });

  it('never sends the file anywhere itself', async () => {
    // PRD 7 section 34: the PDF is the sharing mechanism, and Nura does not
    // deliver it to a doctor.
    await shareReport({ uri: 'file:///cache/x.pdf', fileName: 'x.pdf' });
    const posts = backend.requests.filter((request) => request.method === 'POST');
    expect(posts).toEqual([]);
  });
});

describe('the whole export', () => {
  it('downloads then shares, and reports what happened', async () => {
    const outcome = await exportAndShareReport(PROFILE, 'appointment-1', report);

    expect(downloads.length).toBe(1);
    expect(shares.length).toBe(1);
    expect(outcome.shared).toBe(true);
    expect(outcome.fileName).toBe('Nura_Health_Summary_2026-09-28.pdf');
    // The share is of the file that was just downloaded (PRD 7, section 67's
    // "share uses generated file").
    expect(shares[0]?.uri).toBe(outcome.uri);
  });

  it('reports a real file even when the platform cannot share it', async () => {
    state.sharingAvailable = false;
    const outcome = await exportAndShareReport(PROFILE, 'appointment-1', report);

    expect(outcome.shared).toBe(false);
    expect(outcome.uri).toContain('Nura_Health_Summary_2026-09-28.pdf');
  });

  it('does not share anything when the download failed', async () => {
    state.downloadFails = true;
    await expect(
      exportAndShareReport(PROFILE, 'appointment-1', report)
    ).rejects.toThrow();
    expect(shares).toEqual([]);
  });
});
