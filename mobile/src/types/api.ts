/** Response shapes returned by the Nura backend (PRD 0, sections 15 and 29). */

/** `GET /health` -- the unversioned liveness probe. */
export interface HealthResponse {
  status: string;
  service: string;
}

/** `GET /api/v1/version` */
export interface VersionResponse {
  apiVersion: string;
  minimumAppVersion: string;
}
