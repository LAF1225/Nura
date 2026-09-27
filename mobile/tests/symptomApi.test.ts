/**
 * The symptom endpoints as the app sees them (PRD 6, sections 50-53, 61 and 63).
 *
 * Responses are parsed rather than cast, so this file checks the parsing decisions
 * that would matter if a server ever sent something unexpected. Two of them are
 * safety properties rather than conveniences:
 *
 *   `urgent` defaults to **false**, and so does `worsening`. A missing or
 *   unrecognised safety field must read as "nothing to say", never as an
 *   emergency (PRD 6, sections 42 and 44).
 *
 *   A photo is described without a storage key, and a photo's bytes are reached
 *   through a URL carrying the user's own token -- never a public or signed one
 *   (PRD 6, section 63).
 */
import {
  createEntry,
  createEpisode,
  fetchEpisode,
  fetchEpisodes,
  fetchSymptomSummary,
  parseEpisode,
  parseSafety,
  parseTodaySymptoms,
  photoSource,
  recordRecurrence,
  resolveEpisode,
} from '../src/features/symptoms/api';
import { setAuthTokenProvider } from '../src/services/api/client';
import { mockBackend, symptomEntryFixture, symptomEpisodeFixture } from './helpers';

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  backend = mockBackend({ symptoms: [symptomEpisodeFixture()] });
  setAuthTokenProvider(async () => 'test-token');
});

afterEach(() => {
  backend.restore();
  setAuthTokenProvider(async () => null);
});

describe('parsing an episode', () => {
  it('reads the structured description back whole', () => {
    const episode = parseEpisode(symptomEpisodeFixture(), '/symptoms');

    expect(episode.name).toBe('Headache');
    expect(episode.bodySite).toBe('behind both eyes');
    expect(episode.status).toBe('active');
    expect(episode.firstNoticedText).toBe('this morning');
    expect(episode.latestEntry?.severity).toBe(5);
    expect(episode.latestEntry?.changeState).toBe('worsening');
    expect(episode.latestEntry?.associatedSymptoms).toEqual(['nausea']);
  });

  it('falls back safely on an unrecognised status', () => {
    const episode = parseEpisode(
      symptomEpisodeFixture({ status: 'something-new' }),
      '/symptoms'
    );
    expect(episode.status).toBe('active');
  });

  it('accepts an episode with nothing logged about it yet', () => {
    const episode = parseEpisode(
      symptomEpisodeFixture({ latest_entry: null, entries: [], entry_count: 0 }),
      '/symptoms'
    );
    expect(episode.latestEntry).toBeNull();
    expect(episode.entryCount).toBe(0);
  });

  it('keeps a recurrence’s link to the bout it follows', () => {
    const episode = parseEpisode(
      symptomEpisodeFixture({ status: 'recurring', previous_episode_id: 'episode-0' }),
      '/symptoms'
    );
    expect(episode.status).toBe('recurring');
    expect(episode.previousEpisodeId).toBe('episode-0');
  });

  it('keeps what was denied and what was uncertain', () => {
    const episode = parseEpisode(
      symptomEpisodeFixture({
        latest_entry: symptomEntryFixture({
          negated_items: ['vomiting'],
          uncertain_items: ['dizziness'],
          context_dependent_items: ['only when I stand up'],
        }),
      }),
      '/symptoms'
    );
    expect(episode.latestEntry?.negatedItems).toEqual(['vomiting']);
    expect(episode.latestEntry?.uncertainItems).toEqual(['dizziness']);
    expect(episode.latestEntry?.contextDependentItems).toEqual(['only when I stand up']);
  });

  it('never carries a storage key for a photo (PRD 6, section 63)', () => {
    const episode = parseEpisode(
      symptomEpisodeFixture({
        latest_entry: symptomEntryFixture({
          photos: [
            {
              id: 'photo-1',
              symptom_entry_id: 'entry-1',
              content_type: 'image/jpeg',
              byte_size: 2048,
              created_at: '2026-09-27T09:00:00Z',
              // Even if a server sent one, the app does not keep it.
              storage_key: 'symptom-photos/profile-1/photo-1.jpg',
            },
          ],
        }),
      }),
      '/symptoms'
    );
    const photo = episode.latestEntry?.photos[0];
    expect(photo?.contentType).toBe('image/jpeg');
    expect(JSON.stringify(photo)).not.toContain('symptom-photos');
  });
});

describe('parsing the safety block', () => {
  it('says nothing when the server sent nothing', () => {
    expect(parseSafety(null)).toEqual({
      worsening: false,
      reasons: [],
      notice: null,
      urgent: false,
    });
    expect(parseSafety(undefined).urgent).toBe(false);
  });

  it('never reads a missing field as urgent', () => {
    // The failure mode of this defaulting the other way is unacceptable.
    expect(parseSafety({}).urgent).toBe(false);
    expect(parseSafety({ urgent: 'yes' }).urgent).toBe(false);
    expect(parseSafety({ worsening: 1 }).worsening).toBe(false);
  });

  it('reads a genuine notice through', () => {
    const parsed = parseSafety({
      worsening: true,
      reasons: ['reported_worsening', 'nonsense'],
      notice: 'You have recorded this as worsening.',
      urgent: false,
    });
    expect(parsed.worsening).toBe(true);
    expect(parsed.reasons).toEqual(['reported_worsening']);
    expect(parsed.notice).toContain('worsening');
  });
});

describe('parsing the Today block', () => {
  it('is null when the account has no profile', () => {
    expect(parseTodaySymptoms(null)).toBeNull();
  });

  it('reads the counts and the most recent symptom', () => {
    const parsed = parseTodaySymptoms({
      active_count: 2,
      worsening_count: 1,
      most_recent: {
        episode_id: 'episode-1',
        name: 'Headache',
        severity: 5,
        change_state: 'worsening',
        updated_at: '2026-09-27T09:00:00Z',
      },
      has_episodes: true,
    });
    expect(parsed?.activeCount).toBe(2);
    expect(parsed?.worseningCount).toBe(1);
    expect(parsed?.mostRecent?.name).toBe('Headache');
    expect(parsed?.hasEpisodes).toBe(true);
  });

  it('handles somebody who has never logged a symptom', () => {
    const parsed = parseTodaySymptoms({
      active_count: 0,
      worsening_count: 0,
      most_recent: null,
      has_episodes: false,
    });
    expect(parsed?.mostRecent).toBeNull();
    expect(parsed?.hasEpisodes).toBe(false);
  });
});

describe('requests', () => {
  it('asks for a profile’s episodes under that profile', async () => {
    await fetchEpisodes('profile-1');
    expect(backend.requests.map((request) => request.path)).toContain(
      '/api/v1/profiles/profile-1/symptoms'
    );
  });

  it('sends the filters the screens use', async () => {
    await fetchEpisodes('profile-1', { active: true });
    await fetchEpisodes('profile-1', { status: 'resolved' });

    const paths = backend.requests.map((request) => request.path);
    expect(paths.some((path) => path.includes('active=true'))).toBe(true);
    expect(paths.some((path) => path.includes('status=resolved'))).toBe(true);
  });

  it('creates an episode and its first entry in one request', async () => {
    const episode = await createEpisode('profile-1', {
      name: 'Knee pain',
      body_site: 'left knee',
      first_noticed_date: '2026-09-26',
      first_noticed_text: 'yesterday',
      source: 'guided_app',
      first_entry: {
        client_entry_id: 'entry-abcdef12',
        source: 'guided_app',
        recorded_at: '2026-09-27T09:00:00Z',
        main_symptom: 'knee pain',
        site: 'left knee',
        onset_text: 'yesterday',
        onset_date: '2026-09-26',
        character: 'sharp',
        radiation: null,
        timing: null,
        severity: 6,
        change_state: null,
        free_text_note: null,
        associated_symptoms: [],
        exacerbating_factors: [],
        relieving_factors: [],
        negated_items: [],
        uncertain_items: [],
        context_dependent_items: [],
      },
    });

    expect(episode.name).toBe('Knee pain');
    const post = backend.requests.find(
      (request) => request.method === 'POST' && request.path.endsWith('/symptoms')
    );
    expect(post).toBeDefined();
    const body = post?.body as Record<string, unknown>;
    expect(body.source).toBe('guided_app');
    expect((body.first_entry as Record<string, unknown>).client_entry_id).toBe(
      'entry-abcdef12'
    );
  });

  it('reports whether a follow-up was created or replayed', async () => {
    const saved = await createEntry('profile-1', 'episode-1', {
      client_entry_id: 'entry-11112222',
      source: 'manual_app',
      recorded_at: '2026-09-27T12:00:00Z',
      main_symptom: null,
      site: null,
      onset_text: null,
      onset_date: null,
      character: null,
      radiation: null,
      timing: null,
      severity: 7,
      change_state: 'worsening',
      free_text_note: null,
      associated_symptoms: [],
      exacerbating_factors: [],
      relieving_factors: [],
      negated_items: [],
      uncertain_items: [],
      context_dependent_items: [],
    });

    expect(saved.created).toBe(true);
    expect(saved.entry.severity).toBe(7);
    // The server decides what to say about a worsening entry.
    expect(saved.safety.worsening).toBe(true);
    expect(saved.safety.urgent).toBe(false);
  });

  it('resolves an episode without deleting anything', async () => {
    const resolved = await resolveEpisode('profile-1', 'episode-1');
    expect(resolved.status).toBe('resolved');
    expect(resolved.resolvedAt).not.toBeNull();
  });

  it('records a recurrence as a new linked episode', async () => {
    const recurrence = await recordRecurrence('profile-1', 'episode-1', {
      body_site: null,
      first_noticed_date: null,
      first_noticed_text: 'last night',
      source: 'manual_app',
      first_entry: {
        client_entry_id: 'entry-33334444',
        source: 'manual_app',
        recorded_at: '2026-09-27T12:00:00Z',
        main_symptom: null,
        site: null,
        onset_text: 'last night',
        onset_date: null,
        character: null,
        radiation: null,
        timing: null,
        severity: 4,
        change_state: null,
        free_text_note: null,
        associated_symptoms: [],
        exacerbating_factors: [],
        relieving_factors: [],
        negated_items: [],
        uncertain_items: [],
        context_dependent_items: [],
      },
    });

    expect(recurrence.status).toBe('recurring');
    expect(recurrence.previousEpisodeId).toBe('episode-1');
    expect(recurrence.id).not.toBe('episode-1');
  });

  it('reads the summary as counts only', async () => {
    const summary = await fetchSymptomSummary('profile-1');
    expect(summary.activeCount).toBe(1);
    expect(summary.hasEpisodes).toBe(true);
    expect(Object.keys(summary).sort()).toEqual([
      'activeCount',
      'hasEpisodes',
      'recentUpdatesCount',
      'worseningCount',
    ]);
  });

  it('fetches one episode with its history', async () => {
    const episode = await fetchEpisode('profile-1', 'episode-1');
    expect(episode.entries?.length).toBe(1);
  });
});

describe('reaching a photo (PRD 6, section 63)', () => {
  it('builds a URL with the user’s own token beside it', async () => {
    const source = await photoSource('profile-1', 'episode-1', 'entry-1', 'photo-1');

    expect(source?.uri).toContain(
      '/api/v1/profiles/profile-1/symptoms/episode-1/entries/entry-1/photos/photo-1/content'
    );
    expect(source?.headers.Authorization).toBe('Bearer test-token');
    // Nothing is signed into the URL itself.
    expect(source?.uri).not.toContain('token');
    expect(source?.uri).not.toContain('signature');
  });

  it('is null when nobody is signed in, rather than an unauthenticated URL', async () => {
    setAuthTokenProvider(async () => null);
    expect(await photoSource('profile-1', 'episode-1', 'entry-1', 'photo-1')).toBeNull();
  });
});
